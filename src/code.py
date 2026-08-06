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
#
#   Board -> Host
#     ok                                            Quittung auf V und S
#     id omnibot <board> <protokollversion>         Antwort auf P
#     t <ms> <l> <r> <ticks_l> <ticks_r> <flags>    Telemetrie, 10 Hz
#
# Unbekannte oder kaputte Zeilen werden stillschweigend verworfen - eine
# verstuemmelte Zeile darf den Roboter niemals in Fahrt setzen.
#
# Kommt laenger als DEADMAN_TIMEOUT kein V, gehen die Motoren aus.

import time

import pwmio

import hardware

PROTO_VERSION = 1

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


def drive(left, right):
    """Radsollwerte anwenden, jeweils -1.0 .. +1.0."""
    global deadband_flags, moving

    dl = motor_left.set(left)
    dr = motor_right.set(right)
    deadband_flags = (FLAG_DEADBAND_L if dl else 0) | (FLAG_DEADBAND_R if dr else 0)
    moving = motor_left.applied != 0.0 or motor_right.applied != 0.0


def handle(line):
    global last_command, deadman_tripped

    if not line:
        return
    kind = line[0]

    if kind == "V":
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
        write("ok\n")

    elif kind == "S":
        drive(0.0, 0.0)
        last_command = time.monotonic()
        deadman_tripped = False
        write("ok\n")

    elif kind == "P":
        write("id omnibot {} {}\n".format(hardware.BOARD, PROTO_VERSION))


def telemetry(now):
    flags = deadband_flags | (FLAG_DEADMAN if deadman_tripped else 0)
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
last_command = time.monotonic()
last_telemetry = last_command

print("Omnibot Motorknoten bereit - Board:", hardware.BOARD)

while True:
    now = time.monotonic()

    for line in reader.lines():
        handle(line)

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
