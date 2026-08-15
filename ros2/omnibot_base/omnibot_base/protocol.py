"""Serielle Gegenstelle zum Motorknoten - ebenfalls ohne ROS-Abhaengigkeit.

Das Protokoll ist in src/code.py oben vollstaendig beschrieben. Hier steht nur
die Host-Seite davon:

    Host -> Board    V <links> <rechts> | S | P
    Board -> Host    ok | id omnibot <board> <version> | t <ms> <l> <r> <tl> <tr> <flags>

Zeilen, die nicht ins Schema passen, werden verworfen statt zu werfen. Eine
verstuemmelte Telemetriezeile darf die Odometrie nicht abreissen lassen.
"""

import serial

# Flags aus der Telemetrie, identisch zu src/code.py
FLAG_DEADMAN = 1
FLAG_DEADBAND_L = 2
FLAG_DEADBAND_R = 4
FLAG_MANUAL = 8
FLAG_REMOTE = 16

FLAG_NAMES = (
    (FLAG_DEADMAN, "totmann"),
    (FLAG_DEADBAND_L, "totband-l"),
    (FLAG_DEADBAND_R, "totband-r"),
    (FLAG_MANUAL, "handbetrieb"),
    (FLAG_REMOTE, "funk"),
)

# Der Zeitstempel des Boards laeuft nach gut vier Stunden ueber, siehe
# telemetry() in src/code.py.
MS_WRAP = 0x1000000

MAX_LINE = 64


def flag_names(flags):
    return [name for bit, name in FLAG_NAMES if flags & bit]


class Telemetry:
    """Eine ausgewertete t-Zeile."""

    __slots__ = ("ms", "duty_left", "duty_right", "ticks_left", "ticks_right", "flags")

    def __init__(self, ms, duty_left, duty_right, ticks_left, ticks_right, flags):
        self.ms = ms
        self.duty_left = duty_left
        self.duty_right = duty_right
        self.ticks_left = ticks_left
        self.ticks_right = ticks_right
        self.flags = flags

    @property
    def manual(self):
        return bool(self.flags & FLAG_MANUAL)

    @property
    def deadman(self):
        return bool(self.flags & FLAG_DEADMAN)

    @property
    def remote(self):
        return bool(self.flags & FLAG_REMOTE)


def parse_telemetry(line):
    """"t ms l r tl tr flags" -> Telemetry, oder None wenn die Zeile nicht passt."""
    parts = line.split()
    if len(parts) != 7 or parts[0] != "t":
        return None
    try:
        values = [int(p) for p in parts[1:]]
    except ValueError:
        return None
    return Telemetry(*values)


def elapsed_ms(previous, current):
    """Zeitdifferenz zweier Board-Zeitstempel, ueberlaufsicher."""
    return (current - previous) % MS_WRAP


class MotorLink:
    """Serielle Verbindung zum Motorknoten.

    Nicht blockierend: poll() holt ab, was da ist, und gibt fertige Zeilen
    zurueck. Der Aufrufer bestimmt die Taktung.
    """

    def __init__(self, port, baudrate=115200, timeout=0.0):
        self.serial = serial.Serial(port, baudrate, timeout=timeout)
        self._buffer = b""

    def close(self):
        try:
            self.stop()
        finally:
            self.serial.close()

    # ------------------------------------------------------------------ senden

    def _write(self, text):
        self.serial.write(text.encode("ascii"))

    def drive(self, duty_left, duty_right):
        self._write("V {} {}\n".format(int(duty_left), int(duty_right)))

    def stop(self):
        self._write("S\n")

    def ping(self):
        self._write("P\n")

    # ---------------------------------------------------------------- empfangen

    def poll(self):
        """Alle vollstaendigen Zeilen abholen, die inzwischen angekommen sind."""
        waiting = self.serial.in_waiting
        if waiting:
            self._buffer += self.serial.read(waiting)

        lines = []
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            try:
                text = raw.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue  # Leitungsstoerung, Zeile ist verloren
            if text:
                lines.append(text)

        # Ohne Zeilenende kommt hier nichts Brauchbares mehr - Puffer verwerfen,
        # damit ein Datenstrom ohne \n nicht den Speicher fuellt.
        if len(self._buffer) > MAX_LINE:
            self._buffer = b""
        return lines
