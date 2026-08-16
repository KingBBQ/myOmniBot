# code.py - Omnibot 5402 Motorknoten
#
# Nimmt Radsollwerte ueber eine serielle Leitung entgegen und setzt sie in PWM
# um. Mehr nicht. Die Kinematik (cmd_vel -> Radgeschwindigkeit -> Duty) liegt
# bewusst auf dem Companion Computer: dort ist sie ohne Firmware-Upload tunebar,
# und ein Boardwechsel betrifft nur hardware.py.
#
# Protokoll: ASCII, zeilenweise, 115200 Baud. Von Hand bedienbar mit
# tools/serial_console.py oder einem Terminalprogramm.
#
#   Host -> Board
#     V <links> <rechts>   Radsollwerte, jeweils -1000..1000 (Promille Duty)
#     S                    Sofortstopp
#     P                    Ping
#     M                    Handbetrieb umschalten (nur von der Fernbedienung)
#     A <n>                Sondertaste n (Sound) - noch ohne Wirkung
#
#   Board -> Host
#     ok                                            Quittung auf V und S
#     id omnibot <board> <protokollversion>         Antwort auf P
#     t <ms> <l> <r> <ticks_l> <ticks_r> <flags>    Telemetrie, 10 Hz
#     # boot <board> <reset_reason> <run_reason>    Startbericht, einmal
#     # exc <nr> <Typ>: <Text>                      abgefangene Ausnahme
#
# Dieselben Zeilen kommen ueber **zwei** Wege herein: die serielle Leitung vom
# Companion Computer und ESP-NOW von der Fernbedienung (src/code_remote.py).
# Es faehrt immer nur eine Quelle:
#
#   Handbetrieb aus (Start)  - der Companion Computer faehrt, V von der
#                              Fernbedienung wird verworfen
#   Handbetrieb an           - umgekehrt
#
# Umgeschaltet wird ausschliesslich mit der Start/Stop-Taste der Fernbedienung.
# Der Companion Computer kann sich die Kontrolle also nicht selbst zurueckholen -
# wer die Fernbedienung in der Hand hat, behaelt sie. Faellt die Fernbedienung
# aus, bleibt der Roboter im Handbetrieb stehen; das ist Absicht und sicherer,
# als ihn unerwartet wieder autonom losfahren zu lassen.
#
# S stoppt dagegen **immer**, egal aus welcher Quelle.
#
# Unbekannte oder kaputte Zeilen werden stillschweigend verworfen - eine
# verstuemmelte Zeile darf den Roboter niemals in Fahrt setzen.
#
# Kommt laenger als DEADMAN_TIMEOUT kein V, gehen die Motoren aus.

import time

import microcontroller
import pwmio
import supervisor

import hardware

PROTO_VERSION = 2  # 2: M und A dazugekommen, zweite Befehlsquelle per ESP-NOW

# Not-Aus. Bei autonomer Fahrt muss das kurz sein - die 1,5 s der alten
# Webserver-Firmware waeren hier viel zu lang. Der Host sendet mit 20 Hz,
# das sind sechs verpasste Pakete Toleranz.
DEADMAN_TIMEOUT = 0.3

TELEMETRY_PERIOD = 0.1  # 10 Hz

# Unter diesem Betrag brummen die Motoren nur, drehen aber nicht durch: ein
# Blockierzustand mit entsprechend hohem Strom. Solche Werte werden zu 0.
# Der Host muss dafuer sorgen, gar nicht erst hier hinein zu kommandieren -
# das hier ist nur der Hardwareschutz, keine Regelung.
DEADBAND = 0.2

# Kalibrierung: auf True stellen, wenn ein Motor falsch herum dreht
INVERT_LEFT = False
INVERT_RIGHT = False

# Flags in der Telemetrie
FLAG_DEADMAN = 1  # Motoren wegen Timeout gestoppt
FLAG_DEADBAND_L = 2
FLAG_DEADBAND_R = 4
FLAG_MANUAL = 8  # Fernbedienung hat das Sagen, serielle V werden verworfen
FLAG_REMOTE = 16  # Fernbedienung ist in Reichweite

# Augen: je eine rote LED mit eigenem 100-Ohm-Vorwiderstand gegen GND.
EYE_FADE_IN = 2.0
EYE_HOLD = 1.5
EYE_FADE_OUT = 2.0
EYE_PAUSE = 0.8
EYE_MAX = 1.0
EYE_PWM_FREQ = 1000  # fuer LEDs reicht 1 kHz, kein sichtbares Flimmern


# ---------------------------------------------------------------- Motorsteuerung


class Motor:
    def __init__(self, pins, inverted=False):
        self.a = pwmio.PWMOut(
            hardware.pin(pins[0]), frequency=hardware.PWM_FREQ, duty_cycle=0
        )
        self.b = pwmio.PWMOut(
            hardware.pin(pins[1]), frequency=hardware.PWM_FREQ, duty_cycle=0
        )
        self.inverted = inverted
        self.applied = 0.0

    def set(self, speed):
        """speed: -1.0 (rueckwaerts) .. 0 (aus) .. +1.0 (vorwaerts).

        Gibt True zurueck, wenn der Wert im Totband lag und verworfen wurde.
        """
        speed = max(-1.0, min(1.0, speed))
        in_deadband = 0.0 < abs(speed) < DEADBAND
        if in_deadband:
            speed = 0.0
        self.applied = speed

        out = -speed if self.inverted else speed
        duty = int(abs(out) * 65535)
        if out > 0:
            self.a.duty_cycle = duty
            self.b.duty_cycle = 0
        elif out < 0:
            self.a.duty_cycle = 0
            self.b.duty_cycle = duty
        else:  # ausrollen lassen
            self.a.duty_cycle = 0
            self.b.duty_cycle = 0
        return in_deadband


# ------------------------------------------------------------------------ Augen


class Eyes:
    """Zwei LEDs, die langsam heller werden, hell bleiben und wieder abdimmen."""

    CYCLE = EYE_FADE_IN + EYE_HOLD + EYE_FADE_OUT + EYE_PAUSE

    def __init__(self, pins):
        self.outputs = [
            pwmio.PWMOut(hardware.pin(p), frequency=EYE_PWM_FREQ, duty_cycle=0)
            for p in pins
        ]

    def level(self, value):
        value = max(0.0, min(1.0, value))
        # Gammakorrektur: das Auge sieht Helligkeit logarithmisch, ohne das
        # Quadrat wirkt die obere Haelfte des Verlaufs wie Stillstand.
        for out in self.outputs:
            out.duty_cycle = int(value * value * 65535)

    def animate(self, now):
        t = now % self.CYCLE
        if t < EYE_FADE_IN:
            self.level(EYE_MAX * t / EYE_FADE_IN)
        elif t < EYE_FADE_IN + EYE_HOLD:
            self.level(EYE_MAX)
        elif t < EYE_FADE_IN + EYE_HOLD + EYE_FADE_OUT:
            elapsed = t - EYE_FADE_IN - EYE_HOLD
            self.level(EYE_MAX * (1.0 - elapsed / EYE_FADE_OUT))
        else:
            self.level(0)


# --------------------------------------------------------------- Protokoll-IO


class LineReader:
    """Sammelt Bytes vom Link und gibt vollstaendige Zeilen zurueck."""

    # Laengere Zeilen gibt es im Protokoll nicht. Die Grenze verhindert, dass
    # ein Datenstrom ohne Zeilenende den Speicher vollaeuft.
    MAX_LINE = 64

    def __init__(self, link):
        self.link = link
        self.buf = b""

    def lines(self):
        waiting = self.link.in_waiting
        if waiting:
            data = self.link.read(waiting)
            if data:
                self.buf += data

        out = []
        while True:
            idx = self.buf.find(b"\n")
            if idx < 0:
                break
            raw = self.buf[:idx]
            self.buf = self.buf[idx + 1 :]
            try:
                out.append(str(raw, "utf-8").strip())
            except Exception:  # noqa - kaputte Bytes verwerfen, nicht abstuerzen
                pass

        if len(self.buf) > self.MAX_LINE:
            self.buf = b""  # kein Zeilenende in Sicht, nur Muell
        return out


def write(text):
    try:
        link.write(text.encode("utf-8"))
    except Exception as err:  # noqa - abgezogenes Kabel darf nicht stoppen
        print("Schreibfehler:", err)


def note(text):
    """Diagnosezeile an beide Ausgaenge.

    Ueber den Link, weil beim Fahren niemand am USB-Port haengt: nur so landet
    ein Neustart oder eine Ausnahme im ROS-Log des Companion Computers. Der
    Host verwirft unbekannte Zeilen ohnehin, das Raute-Praefix macht sie
    ausdruecklich als Diagnose kenntlich.
    """
    print(text)
    write("# {}\n".format(text))


def drive(left, right):
    """Radsollwerte anwenden, jeweils -1.0 .. +1.0."""
    global deadband_flags, moving

    dl = motor_left.set(left)
    dr = motor_right.set(right)
    deadband_flags = (FLAG_DEADBAND_L if dl else 0) | (FLAG_DEADBAND_R if dr else 0)
    moving = motor_left.applied != 0.0 or motor_right.applied != 0.0


def handle(line, source):
    """Eine Protokollzeile ausfuehren. source ist "link" oder "remote"."""
    global last_command, deadman_tripped, manual

    if not line:
        return
    kind = line[0]

    if kind == "V":
        # Nur die gerade aktive Quelle darf fahren. Die andere wird verworfen,
        # ohne die Totmannschaltung zu fuettern - sonst wuerde ein weiter
        # sendender Companion Computer den Handbetrieb am Leben halten.
        if (source == "remote") != manual:
            return
        parts = line.split()
        if len(parts) != 3:
            return
        try:
            left = int(parts[1])
            right = int(parts[2])
        except ValueError:
            return  # Unsinn im Parameter: lieber nichts tun als falsch fahren
        drive(left / 1000.0, right / 1000.0)
        last_command = time.monotonic()
        deadman_tripped = False
        if source == "link":
            write("ok\n")

    elif kind == "S":
        # Stopp gilt immer, aus jeder Quelle.
        drive(0.0, 0.0)
        last_command = time.monotonic()
        deadman_tripped = False
        if source == "link":
            write("ok\n")

    elif kind == "P":
        write("id omnibot {} {}\n".format(hardware.BOARD, PROTO_VERSION))

    elif kind == "M":
        # Betriebsart umschalten - bewusst nur von der Fernbedienung aus.
        if source != "remote":
            return
        manual = not manual
        drive(0.0, 0.0)  # Quellenwechsel nie im Fahren
        last_command = time.monotonic()
        deadman_tripped = False
        print("Handbetrieb:", "an" if manual else "aus")

    elif kind == "A":
        # Sondertasten der Fernbedienung. Der Lautsprecher des Omnibot ist noch
        # nicht angeschlossen, deshalb bleibt es vorerst bei der Ausgabe.
        parts = line.split()
        if len(parts) == 2:
            print("Sondertaste", parts[1])


def telemetry(now):
    flags = deadband_flags | (FLAG_DEADMAN if deadman_tripped else 0)
    if manual:
        flags |= FLAG_MANUAL
    if remote and remote.connected(now):
        flags |= FLAG_REMOTE
    # ms laeuft nach gut vier Stunden ueber - der Host nutzt den Wert nur, um
    # Luecken zu erkennen, nicht als absolute Zeit.
    write(
        "t {} {} {} {} {} {}\n".format(
            int(now * 1000) & 0xFFFFFF,
            int(motor_left.applied * 1000),
            int(motor_right.applied * 1000),
            ticks_left,
            ticks_right,
            flags,
        )
    )


# ----------------------------------------------------------------------- Start

link = hardware.open_link()
reader = LineReader(link)

motor_left = Motor(hardware.MOTOR_LEFT, INVERT_LEFT)
motor_right = Motor(hardware.MOTOR_RIGHT, INVERT_RIGHT)

# Fehlende oder belegte Pins duerfen den Fahrbetrieb nicht verhindern
try:
    eyes = Eyes(hardware.EYE_PINS) if hardware.EYE_PINS else None
except Exception as err:  # noqa - alles, was pwmio wirft
    print("Augen nicht verfuegbar:", err)
    eyes = None

# Platzhalter, bis die Lichtschranken verbaut sind (Phase 2d). Die Felder sind
# schon im Protokoll, damit sich das Format spaeter nicht aendern muss.
ticks_left = 0
ticks_right = 0

deadband_flags = 0
deadman_tripped = False
moving = False
manual = False  # True: die Fernbedienung faehrt, der Companion Computer nicht
last_command = time.monotonic()
last_telemetry = last_command

# Ohne Fernbedienung laeuft der Motorknoten unveraendert weiter - fehlendes
# espnow-Modul oder abgeschaltetes Funkmodul duerfen den Fahrbetrieb am
# seriellen Link nicht verhindern.
try:
    import espnow_link

    remote = espnow_link.RemoteLink()
    print("ESP-NOW bereit - MAC:", ":".join("%02x" % b for b in remote.mac))
except Exception as err:  # noqa - alles, was Import oder Funkinit wirft
    print("Fernbedienung nicht verfuegbar:", err)
    remote = None

def _grund(wert):
    """microcontroller.ResetReason.BROWNOUT -> BROWNOUT."""
    text = str(wert)
    return text[text.rfind(".") + 1 :]


print("Omnibot Motorknoten bereit - Board:", hardware.BOARD)

# Der Startbericht geht ueber den Link, damit der Companion Computer einen
# Neustart des Boards als solchen erkennt. Bleibt die Telemetrie weg und
# danach kommt diese Zeile, hat sich das Board neu gestartet - der Grund steht
# dabei. Kommt die Telemetrie ohne Startbericht wieder, war es kein Neustart.
note(
    "boot {} {} {}".format(
        hardware.BOARD,
        _grund(microcontroller.cpu.reset_reason),
        _grund(supervisor.runtime.run_reason),
    )
)

fehler = 0
funkfehler = 0

while True:
    # Der Schleifenkoerper ist abgesichert, weil eine durchschlagende Ausnahme
    # code.py beendet: CircuitPython faellt dann in die REPL, der Link
    # verstummt dauerhaft und die Motoren behalten ihren letzten Sollwert.
    # Genau das darf im Fahrbetrieb nicht passieren.
    try:
        now = time.monotonic()

        for line in reader.lines():
            handle(line, "link")

        if remote:
            for line in remote.lines():
                handle(line, "remote")
            remote.status(now, manual, moving)
            if remote.errors != funkfehler:
                funkfehler = remote.errors
                note("funk {} {}".format(funkfehler, remote.last_error))

        # Totmannschaltung: stoppen, wenn der Host sich nicht mehr meldet
        if moving and now - last_command > DEADMAN_TIMEOUT:
            drive(0.0, 0.0)
            deadman_tripped = True
            print("Timeout - gestoppt")

        if now - last_telemetry >= TELEMETRY_PERIOD:
            last_telemetry = now
            telemetry(now)

        if eyes:
            eyes.animate(now)

    except Exception as err:  # noqa - der Fahrbetrieb ueberlebt jeden Fehler
        fehler += 1
        try:
            drive(0.0, 0.0)  # erst anhalten, dann berichten
        except Exception:  # noqa
            pass
        note("exc {} {}: {}".format(fehler, type(err).__name__, err))
        try:
            import traceback

            traceback.print_exception(err)
        except Exception:  # noqa - Traceback ist Kuer, Weiterlaufen ist Pflicht
            pass
        time.sleep(0.2)  # nicht in einer Fehlerschleife heisslaufen
