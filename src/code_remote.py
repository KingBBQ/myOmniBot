# code_remote.py - Fernbedienung Omnibot 5402 auf einem LOLIN S2 Mini
#
# Die Taster der Originalfernbedienung liegen alle gegen GND, die Eingaenge
# laufen mit internem Pull-Up. Gesendet wird per ESP-NOW als Broadcast, im
# **selben ASCII-Protokoll**, das auch ueber die serielle Leitung zum Motorknoten
# geht. Der Motorknoten muss dadurch keine zweite Befehlssprache koennen - die
# Zeilen landen bei ihm in derselben handle()-Funktion.
#
# Wird als /code.py auf den S2 Mini gespielt (nativer USB, CIRCUITPY-Laufwerk):
#
#     cp src/code_remote.py /run/media/$USER/CIRCUITPY/code.py
#
# Nicht mit tools/upload.py - das ist der REPL-Uploader fuer den RoboESP32,
# der kein Laufwerk hat.
#
# Gesendet wird:
#     V <links> <rechts>   20 Hz, Radsollwerte in Promille, auch V 0 0
#     M                    einmal pro Druck: Handbetrieb umschalten
#     A <n>                einmal pro Druck: Sondertaste (Sound), n = 1 oder 2
#
# Empfangen wird:
#     a <manuell> <faehrt>  Status vom Roboter, ~5 Hz - treibt die Status-LED

import time

import board
import digitalio
import espnow
import wifi

# ------------------------------------------------------------------ Verdrahtung
#
# Alle Taster gegen GND, Pull-Up im Chip. GPIO39 und GPIO40 sind beim ESP32-S2
# die JTAG-Leitungen MTCK/MTDO - als normale Eingaenge unbedenklich, solange
# kein Debugger angeklemmt ist.

PIN_VOR = 16  # Board-Aufdruck D4
PIN_ZURUECK = 18  # Board-Aufdruck D3
PIN_LINKS = 17
PIN_RECHTS = 21
PIN_MODUS = 39  # Start/Stop der Originalfernbedienung
PIN_SOUND_OBEN = 38
PIN_SOUND_UNTEN = 40

# ---------------------------------------------------------------- Fahrverhalten
#
# Wichtig: der Motorknoten wirft in code.py alles unter DEADBAND = 0.2 weg,
# weil die Motoren dort nur brummen und Blockierstrom ziehen. Das kurveninnere
# Rad darf also nie unter 0.2 rutschen. Mit SPEED 0.6 und TURN_FAHREND 0.35
# bleibt es bei 0.25 - knapp, aber sicher ueber der Schwelle.

SPEED = 0.6  # geradeaus
TURN_DREHEND = 0.5  # Drehen auf der Stelle, beide Raeder gegenlaeufig
TURN_FAHREND = 0.35  # Kurve waehrend der Fahrt

SEND_HZ = 20  # Der Motorknoten stoppt nach DEADMAN_TIMEOUT = 0.3 s
SEND_PERIOD = 1.0 / SEND_HZ

ENTPRELLZEIT = 0.05  # fuer die Tasten mit Flankenauswertung

# Ohne Statuspaket in dieser Zeit gilt die Verbindung als weg
LINK_TIMEOUT = 1.0

# Jede Aenderung der Radsollwerte auf der REPL mitschreiben. Damit laesst sich
# die Verdrahtung pruefen, bevor der Roboter ueberhaupt eingeschaltet ist:
# tio /dev/ttyACM0 aufmachen und die Tasten der Reihe nach druecken.
DEBUG = True

BROADCAST = b"\xff\xff\xff\xff\xff\xff"


def _pin(number):
    """Board-Pin zu einer GPIO-Nummer finden - wie in hardware.py."""
    for name in ("IO{}".format(number), "D{}".format(number), "GPIO{}".format(number)):
        if hasattr(board, name):
            return getattr(board, name)
    raise ValueError("GPIO {} nicht im board-Modul gefunden".format(number))


class Taste:
    """Taster gegen GND mit Pull-Up. gedrueckt() ist der Pegel, kam() die Flanke."""

    def __init__(self, number):
        self.io = digitalio.DigitalInOut(_pin(number))
        self.io.switch_to_input(pull=digitalio.Pull.UP)
        self.stand = False
        self.letzte_aenderung = 0.0

    def gedrueckt(self):
        return not self.io.value  # gegen GND: gedrueckt = LOW

    def kam(self, now):
        """True genau einmal pro Druck, entprellt."""
        jetzt_gedrueckt = self.gedrueckt()
        if jetzt_gedrueckt == self.stand:
            return False
        if now - self.letzte_aenderung < ENTPRELLZEIT:
            return False
        self.letzte_aenderung = now
        self.stand = jetzt_gedrueckt
        return jetzt_gedrueckt  # nur die fallende Flanke ist ein Druck


def mischen(vor, zurueck, links, rechts):
    """Tastenzustaende auf Radsollwerte abbilden, jeweils -1.0 .. +1.0."""
    fahrt = 0.0
    if vor and not zurueck:
        fahrt = SPEED
    elif zurueck and not vor:
        fahrt = -SPEED

    drehung = 0.0
    if links and not rechts:
        drehung = -1.0
    elif rechts and not links:
        drehung = 1.0

    if drehung == 0.0:
        return fahrt, fahrt

    if fahrt == 0.0:
        # Auf der Stelle drehen: Raeder gegenlaeufig
        return drehung * TURN_DREHEND, -drehung * TURN_DREHEND

    # Kurve: das kurvenaeussere Rad bekommt mehr, das innere weniger
    anteil = drehung * TURN_FAHREND
    links_soll = max(-1.0, min(1.0, fahrt + anteil))
    rechts_soll = max(-1.0, min(1.0, fahrt - anteil))
    return links_soll, rechts_soll


# ----------------------------------------------------------------------- Start

# ESP-NOW und eine bestehende WLAN-Verbindung vertragen sich schlecht: der
# Funkkanal haengt dann am Accesspoint, und beide Seiten muessen auf demselben
# Kanal sitzen. Ohne AP-Verbindung landen beide auf Kanal 1. Deshalb hier gar
# nicht erst verbinden - der S2 Mini hat auch keine settings.toml noetig.
wifi.radio.enabled = True
if wifi.radio.connected:
    print("WARNUNG: mit WLAN verbunden - trenne fuer ESP-NOW")
    wifi.radio.stop_station()

funk = espnow.ESPNow()
# Der Peer muss beim Senden **mitgegeben** werden. funk.send(msg) ohne zweites
# Argument scheitert mit ESP-NOW error 0x3069 (ESP_ERR_ESPNOW_NOT_FOUND), auch
# wenn der Broadcast-Peer eingetragen ist. Am Board verifiziert, CP 10.2.1.
broadcast = espnow.Peer(mac=BROADCAST)
funk.peers.append(broadcast)

tasten = {
    "vor": Taste(PIN_VOR),
    "zurueck": Taste(PIN_ZURUECK),
    "links": Taste(PIN_LINKS),
    "rechts": Taste(PIN_RECHTS),
}
taste_modus = Taste(PIN_MODUS)
taste_sound_oben = Taste(PIN_SOUND_OBEN)
taste_sound_unten = Taste(PIN_SOUND_UNTEN)

# Statusanzeige. Fehlt die LED im Board-Modul, laeuft alles ohne sie weiter.
try:
    led = digitalio.DigitalInOut(board.LED)
    led.switch_to_output(False)
except Exception as err:  # noqa - Pin belegt oder nicht vorhanden
    print("Status-LED nicht verfuegbar:", err)
    led = None


def sende(text):
    try:
        funk.send(text.encode("utf-8"), broadcast)
    except Exception as err:  # noqa - ausser Reichweite ist kein Fehlerfall
        print("Sendefehler:", err)


def status_lesen():
    """Statuspakete vom Roboter abholen. Gibt (manuell, gesehen) zurueck."""
    manuell = None
    gesehen = False
    while True:
        paket = funk.read()
        if paket is None:
            break
        gesehen = True
        try:
            zeile = str(paket.msg, "utf-8").strip()
        except Exception:  # noqa - kaputte Bytes verwerfen
            continue
        teile = zeile.split()
        if len(teile) >= 2 and teile[0] == "a":
            manuell = teile[1] == "1"
    return manuell, gesehen


print(
    "Omnibot Fernbedienung bereit - MAC:",
    ":".join("%02x" % b for b in wifi.radio.mac_address),
)

letzter_sendezeitpunkt = 0.0
letztes_statuspaket = -LINK_TIMEOUT
manuell = False
letzte_ausgabe = None

while True:
    now = time.monotonic()

    # --- Flankentasten: einmal pro Druck ein Paket
    if taste_modus.kam(now):
        sende("M\n")
        if DEBUG:
            print("Taste Start/Stop")
    if taste_sound_oben.kam(now):
        sende("A 1\n")
        if DEBUG:
            print("Taste Sound oben")
    if taste_sound_unten.kam(now):
        sende("A 2\n")
        if DEBUG:
            print("Taste Sound unten")

    # --- Fahrtasten: Pegel, mit fester Rate gesendet
    if now - letzter_sendezeitpunkt >= SEND_PERIOD:
        letzter_sendezeitpunkt = now
        links_soll, rechts_soll = mischen(
            tasten["vor"].gedrueckt(),
            tasten["zurueck"].gedrueckt(),
            tasten["links"].gedrueckt(),
            tasten["rechts"].gedrueckt(),
        )
        # Auch V 0 0 wird gesendet: das haelt die Totmannschaltung im Roboter
        # bei Laune und stoppt ihn trotzdem sofort beim Loslassen.
        sende("V {} {}\n".format(int(links_soll * 1000), int(rechts_soll * 1000)))
        if DEBUG and (links_soll, rechts_soll) != letzte_ausgabe:
            letzte_ausgabe = (links_soll, rechts_soll)
            print("V {} {}".format(int(links_soll * 1000), int(rechts_soll * 1000)))

    neuer_stand, gesehen = status_lesen()
    if gesehen:
        letztes_statuspaket = now
    if neuer_stand is not None:
        manuell = neuer_stand

    # --- Status-LED
    #   dauerhaft an  = Verbindung steht, Handbetrieb (die Tasten fahren)
    #   kurzes Blinken = Verbindung steht, aber der Companion Computer faehrt
    #   aus           = keine Verbindung zum Roboter
    if led:
        if now - letztes_statuspaket > LINK_TIMEOUT:
            led.value = False
        elif manuell:
            led.value = True
        else:
            led.value = (now % 1.0) < 0.08
