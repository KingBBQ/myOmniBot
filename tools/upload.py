#!/usr/bin/env python3
"""Datei ueber die CircuitPython-REPL auf den RoboESP32 schieben.

Der Cytron RoboESP32 meldet sich nur als USB-Seriell-Wandler (/dev/ttyUSB0) -
es gibt kein CIRCUITPY-Laufwerk. Also wird die Datei ueber die Raw-REPL uebertragen.

    python tools/upload.py src/code.py /code.py [--port /dev/ttyUSB0] [--run]

Wichtig: Thonny (oder jedes andere Programm) muss den Port vorher freigeben.
"""

import argparse
import base64
import pathlib
import sys
import time

import serial

CHUNK = 192  # Rohbytes pro Uebertragungsblock


def read_until(port, token, timeout=5.0):
    deadline = time.monotonic() + timeout
    data = b""
    while time.monotonic() < deadline:
        data += port.read(port.in_waiting or 1)
        if token in data:
            return data
    raise TimeoutError("{!r} nicht empfangen, gelesen: {!r}".format(token, data[-200:]))


def raw_exec(port, code, timeout=10.0):
    """Ein Stueck Python in der Raw-REPL ausfuehren und die Ausgabe zurueckgeben."""
    port.write(code.encode("utf-8") + b"\x04")
    response = read_until(port, b"\x04>", timeout)
    if not response.startswith(b"OK"):
        raise RuntimeError("REPL hat die Eingabe abgelehnt: {!r}".format(response[:200]))
    body = response[2:-2]
    output, _, error = body.partition(b"\x04")
    if error.strip():
        raise RuntimeError("Fehler auf dem Board:\n" + error.decode("utf-8", "replace"))
    return output.decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target", nargs="?")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--run", action="store_true", help="danach Soft-Reboot und Ausgabe zeigen")
    args = parser.parse_args()

    source = pathlib.Path(args.source)
    target = args.target or "/" + source.name
    payload = source.read_bytes()

    port = serial.Serial(args.port, args.baud, timeout=1)
    try:
        # Laufendes code.py anhalten und in die Raw-REPL wechseln. Auf den
        # normalen Prompt warten statt fest zu schlafen: haengt das Board in
        # einem blockierenden Aufruf (der Webserver etwa steht in accept()),
        # dauert das Ctrl-C deutlich laenger als 0,3 s - und ein zu frueh
        # gesendetes Ctrl-A geht dann verloren.
        port.write(b"\x03\x03")
        # Nach dem Abbruch steht da "Press any key to enter the REPL" - ohne
        # diesen Tastendruck kommt nie ein Prompt. Am fertigen Prompt ist das
        # Newline dagegen wirkungslos, also darf es immer raus.
        time.sleep(0.3)
        port.write(b"\r\n")
        read_until(port, b">>> ", timeout=10.0)
        time.sleep(0.5)
        port.reset_input_buffer()
        port.write(b"\x01")
        # Banner und Prompt kommen zusammen an - in einem Rutsch lesen
        read_until(port, b"raw REPL; CTRL-B to exit\r\n>")

        # Ohne USB-Massenspeicher darf CircuitPython selbst schreiben - zur
        # Sicherheit trotzdem explizit beschreibbar mounten.
        try:
            raw_exec(port, "import storage\nstorage.remount('/', False)")
        except RuntimeError:
            pass  # bereits beschreibbar

        raw_exec(port, "f = open({!r}, 'wb')".format(target))
        total = 0
        for offset in range(0, len(payload), CHUNK):
            block = base64.b64encode(payload[offset : offset + CHUNK]).decode()
            raw_exec(port, "import binascii\nf.write(binascii.a2b_base64('{}'))".format(block))
            total += len(payload[offset : offset + CHUNK])
            print("\r  {} / {} Bytes".format(total, len(payload)), end="", flush=True)
        raw_exec(port, "f.close()")
        print()

        size = raw_exec(port, "import os\nprint(os.stat({!r})[6])".format(target)).strip()
        print("{} -> {} ({} Bytes auf dem Board)".format(source, target, size))
        if size != str(len(payload)):
            print("WARNUNG: Groesse weicht ab!", file=sys.stderr)
            return 1

        port.write(b"\x02")  # zurueck in die normale REPL
        time.sleep(0.2)

        if args.run:
            port.reset_input_buffer()
            port.write(b"\x04")  # Soft-Reboot -> code.py startet
            print("--- Board-Ausgabe ---")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                line = port.readline()
                if line:
                    print(line.decode("utf-8", "replace").rstrip())
    finally:
        port.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
