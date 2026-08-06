#!/usr/bin/env python3
"""Testclient fuer den Omnibot-Motorknoten - fahren und messen ohne ROS.

Damit laesst sich src/code.py komplett verifizieren, bevor irgendein ROS2-Paket
ins Spiel kommt: Handshake, Fahrbefehle, Totmannschaltung, Telemetrie. Und die
beiden Messlaeufe fuer die Kennlinienkalibrierung stecken auch drin.

    .venv/bin/python tools/serial_console.py /dev/ttyUSB0

Tasten:
    Pfeile / w a s d   fahren (vorwaerts, rueckwaerts, drehen)
    Leertaste          Stopp
    + / -              Leistung in 50er-Schritten aendern
    1 2 3 4 5          Leistung auf 200 / 400 / 600 / 800 / 1000 setzen
    g                  Messlauf geradeaus: RUN_SECONDS fahren, dann stoppen
    r                  Messlauf Drehung: RUN_SECONDS drehen, dann stoppen
    p                  Ping - das Board muss mit "id omnibot ..." antworten
    t                  Telemetrieausgabe an/aus
    q / Strg-C         beenden (sendet vorher Stopp)

Die Messlaeufe fahren eine feste Zeit statt einer festen Strecke: eine Zeit
per Software zu stoppen ist genauer, als von Hand eine Stoppuhr zu druecken.
Danach die zurueckgelegte Strecke messen und durch die Zeit teilen.
"""

import argparse
import select
import sys
import termios
import time
import tty

try:
    import serial
except ImportError:
    sys.exit(
        "pyserial fehlt. Mit dem Python aus dem venv starten:\n"
        "  .venv/bin/python tools/serial_console.py"
    )

SEND_HZ = 20  # Kommandorate, muss deutlich ueber der Totmann-Schwelle liegen
POWER_START = 600
POWER_STEP = 50
POWER_MIN = 200  # unter dem Totband in code.py hat Senden keinen Zweck
POWER_MAX = 1000

ARROWS = {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}


def read_keys():
    """Alle anstehenden Tastendruecke abholen, Escape-Sequenzen aufloesen."""
    keys = []
    while select.select([sys.stdin], [], [], 0)[0]:
        ch = sys.stdin.read(1)
        if ch != "\x1b":
            keys.append(ch)
            continue
        # Pfeiltasten kommen als ESC [ A..D - der Rest folgt unmittelbar
        rest = ""
        while len(rest) < 2 and select.select([sys.stdin], [], [], 0.002)[0]:
            rest += sys.stdin.read(1)
        keys.append(ARROWS.get(rest, "esc"))
    return keys


class Console:
    def __init__(self, port, baud, run_seconds):
        self.ser = serial.Serial(port, baud, timeout=0)
        self.run_seconds = run_seconds
        self.power = POWER_START
        self.left = 0
        self.right = 0
        self.show_telemetry = False
        self.rx = b""
        self.run_until = None
        self.status = "bereit"

    # ------------------------------------------------------------- Verbindung

    def send(self, text):
        self.ser.write(text.encode("ascii"))

    def drain(self):
        """Antworten des Boards einlesen und ausgeben."""
        waiting = self.ser.in_waiting
        if waiting:
            self.rx += self.ser.read(waiting)
        while b"\n" in self.rx:
            raw, self.rx = self.rx.split(b"\n", 1)
            line = raw.decode("utf-8", "replace").strip()
            if not line or line == "ok":
                continue
            if line.startswith("t ") and not self.show_telemetry:
                continue
            sys.stdout.write("\r\033[K<< {}\r\n".format(line))

    # ----------------------------------------------------------------- Tasten

    def set_power(self, value):
        self.power = max(POWER_MIN, min(POWER_MAX, value))
        # Aenderung soll waehrend der Fahrt sofort spuerbar sein
        if self.left or self.right:
            sign_l = 1 if self.left > 0 else -1
            sign_r = 1 if self.right > 0 else -1
            self.left = sign_l * self.power
            self.right = sign_r * self.power

    def handle_key(self, key):
        if key in ("q", "\x03"):
            return False

        if key in ("up", "w"):
            self.left = self.right = self.power
            self.status = "vorwaerts"
        elif key in ("down", "s"):
            self.left = self.right = -self.power
            self.status = "rueckwaerts"
        elif key in ("left", "a"):
            self.left, self.right = -self.power, self.power
            self.status = "links"
        elif key in ("right", "d"):
            self.left, self.right = self.power, -self.power
            self.status = "rechts"
        elif key == " ":
            self.left = self.right = 0
            self.run_until = None
            self.status = "stopp"
        elif key == "+":
            self.set_power(self.power + POWER_STEP)
        elif key == "-":
            self.set_power(self.power - POWER_STEP)
        elif key in "12345":
            self.set_power(int(key) * 200)
        elif key == "p":
            self.send("P\n")
            self.status = "ping gesendet"
        elif key == "t":
            self.show_telemetry = not self.show_telemetry
            self.status = "telemetrie " + ("an" if self.show_telemetry else "aus")
        elif key == "g":
            self.left = self.right = self.power
            self.run_until = time.monotonic() + self.run_seconds
            self.status = "messlauf geradeaus"
        elif key == "r":
            self.left, self.right = self.power, -self.power
            self.run_until = time.monotonic() + self.run_seconds
            self.status = "messlauf drehung"
        return True

    # ------------------------------------------------------------ Hauptschleife

    def line(self):
        return "\r\033[K[{:>4} promille] L={:>5} R={:>5}  {}".format(
            self.power, self.left, self.right, self.status
        )

    def run(self):
        self.send("P\n")
        period = 1.0 / SEND_HZ
        next_send = time.monotonic()

        while True:
            for key in read_keys():
                if not self.handle_key(key):
                    return

            now = time.monotonic()

            if self.run_until is not None and now >= self.run_until:
                self.left = self.right = 0
                self.run_until = None
                self.status = "messlauf fertig: {:.2f} s gefahren".format(
                    self.run_seconds
                )

            if now >= next_send:
                next_send = now + period
                self.send("V {} {}\n".format(self.left, self.right))

            self.drain()
            sys.stdout.write(self.line())
            sys.stdout.flush()
            time.sleep(0.005)

    def close(self):
        try:
            self.send("S\n")
            time.sleep(0.05)
        finally:
            self.ser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", nargs="?", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--run-seconds",
        type=float,
        default=3.0,
        help="Dauer der Messlaeufe mit g und r (Standard: 3 s)",
    )
    args = ap.parse_args()

    console = Console(args.port, args.baud, args.run_seconds)
    print(__doc__.split("Tasten:")[1].rstrip())
    print("Port: {} @ {} Baud\n".format(args.port, args.baud))

    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        console.run()
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        console.close()
        print("\nGestoppt.")


if __name__ == "__main__":
    main()
