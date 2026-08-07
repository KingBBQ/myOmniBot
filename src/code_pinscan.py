"""Pin-Scanner fuer den LOLIN S2 Mini.

Schaltet alle nutzbaren IO-Pins auf Eingang mit Pullup und meldet laufend,
welcher Pin gerade gegen GND gezogen wird. Gedacht zum Durchklingeln frisch
angeloeteter Taster, bevor die Belegung in `hardware.py` festgeschrieben wird.

Ausgabe laeuft ueber die serielle REPL:
    .venv/bin/python tools/serial_console.py   oder   tio /dev/ttyACM0
"""

import time

import board
import digitalio
import microcontroller

# Das native USB des ESP32-S2 haengt an GPIO19/20. Wer die als GPIO belegt,
# kappt REPL und CIRCUITPY-Laufwerk - dann hilft nur noch der Bootloader
# (Taste 0 halten, RST tippen, 0 loslassen).
GESPERRT = ("IO19", "IO20")

# Am 2026-08-07 durchgeklingelte Belegung des Omnibot-Bedienfelds. Pins ohne
# Eintrag meldet der Scanner als "frei" - so faellt eine Fehlverdrahtung auf.
TASTER = {
    "IO16": "vorne",
    "IO18": "hinten",
    "IO17": "links",
    "IO21": "rechts",
    "IO39": "start/stop",
    "IO38": "Sound oben",
    "IO40": "Sound unten",
}

ENTPRELLUNG = 0.02  # Sekunden bis zur Bestaetigungsmessung
TAKT = 0.01  # Abtastpause je Runde


def _nummer(name):
    """IO7 -> 7, fuer die Sortierung. Namen ohne Ziffern wandern ans Ende."""
    ziffern = "".join(z for z in name if z.isdigit())
    return int(ziffern) if ziffern else 999


def pins_sammeln():
    """Alle Pins aus dem board-Modul, Aliase je Pin zusammengefasst.

    board.IO7, board.D7 und board.A7 koennen dasselbe Pin-Objekt sein - ohne
    Zusammenfassen wuerde derselbe Taster dreifach gemeldet.
    """
    nach_pin = {}
    for name in dir(board):
        if name.startswith("_"):
            continue
        try:
            wert = getattr(board, name)
        except Exception:
            continue
        if isinstance(wert, microcontroller.Pin):
            nach_pin.setdefault(wert, []).append(name)
    return nach_pin


def eingaenge_anlegen(nach_pin):
    """Jeden Pin als Eingang mit Pullup belegen. Liefert (aktive, uebersprungen)."""
    aktive = []
    uebersprungen = []

    for pin, namen in nach_pin.items():
        namen = sorted(namen)
        haupt = namen[0]
        for name in namen:
            if name.startswith("IO"):
                haupt = name
                break

        if any(name in GESPERRT for name in namen):
            uebersprungen.append((haupt, "USB-Datenleitung"))
            continue

        try:
            io = digitalio.DigitalInOut(pin)
        except Exception as fehler:
            # Belegte Pins (Flash, PSRAM, ...) melden sich hier.
            uebersprungen.append((haupt, str(fehler) or "bereits belegt"))
            continue

        try:
            io.switch_to_input(pull=digitalio.Pull.UP)
        except Exception as fehler:
            io.deinit()
            uebersprungen.append((haupt, str(fehler) or "kein Pullup moeglich"))
            continue

        aktive.append((haupt, namen, io))

    aktive.sort(key=lambda eintrag: _nummer(eintrag[0]))
    uebersprungen.sort(key=lambda eintrag: _nummer(eintrag[0]))
    return aktive, uebersprungen


def beschriftung(haupt, namen):
    if haupt in TASTER:
        return "%-6s %s" % (haupt, TASTER[haupt])
    weitere = [name for name in namen if name != haupt]
    if weitere:
        return "%-6s frei (%s)" % (haupt, ", ".join(weitere))
    return "%-6s frei" % haupt


def bestaetigt(io, erwartet):
    """Nachmessen, damit Prellen keinen Fehlalarm ausloest."""
    time.sleep(ENTPRELLUNG)
    return (not io.value) == erwartet


nach_pin = pins_sammeln()
aktive, uebersprungen = eingaenge_anlegen(nach_pin)

print()
print("Pin-Scan auf %s" % board.board_id)
print("%d Pins auf Eingang + Pullup." % len(aktive))

belegt = [(haupt, namen) for haupt, namen, _ in aktive if haupt in TASTER]
frei = [haupt for haupt, _, _ in aktive if haupt not in TASTER]

print("Bedienfeld:")
for haupt, namen in belegt:
    print("   %s" % beschriftung(haupt, namen))

fehlend = [haupt for haupt in TASTER if haupt not in dict(belegt)]
if fehlend:
    print("   FEHLT im board-Modul: %s" % ", ".join(sorted(fehlend)))

print("frei: %s" % ", ".join(frei))

if uebersprungen:
    print("uebersprungen:")
    for haupt, grund in uebersprungen:
        print("   %-6s %s" % (haupt, grund))

# Pullups brauchen einen Moment, bis die Leitung wirklich oben ist.
time.sleep(0.1)

zustand = {}
for haupt, namen, io in aktive:
    zustand[haupt] = not io.value

klemmt = [haupt for haupt, gedrueckt in zustand.items() if gedrueckt]
if klemmt:
    print()
    print("Achtung, schon beim Start auf LOW: %s" % ", ".join(klemmt))
    print("Entweder haengt dort ein gedrueckter Taster, oder der Pin ist fest")
    print("nach GND verdrahtet und taugt so nicht als Tastereingang.")

print()
print("--- bereit, Taster druecken (Strg-C beendet) ---")

start = time.monotonic()
while True:
    # Erst alle Pins zuegig durchlesen, damit eine Runde kurz bleibt. Nur wo
    # sich etwas geaendert hat, kostet die Bestaetigungsmessung Zeit.
    for haupt, namen, io in aktive:
        gemessen = not io.value
        if gemessen == zustand[haupt]:
            continue
        if not bestaetigt(io, gemessen):
            continue
        zustand[haupt] = gemessen
        print(
            "[%7.2fs] %s %s"
            % (
                time.monotonic() - start,
                "GEDRUECKT  " if gemessen else "losgelassen",
                beschriftung(haupt, namen),
            )
        )
    time.sleep(TAKT)
