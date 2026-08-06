# code.py - Omnibot 5402 Webserver-Fernsteuerung
# CircuitPython 10.x auf Cytron RoboESP32
#
# Keine externen Libraries noetig (kein adafruit_httpserver) - nur Bordmittel.
# WLAN-Zugangsdaten kommen aus settings.toml (CIRCUITPY_WIFI_SSID / _PASSWORD).

import os
import time

import board
import pwmio
import socketpool
import wifi

# ---------------------------------------------------------------- Konfiguration

# Pinbelegung laut DOCUMENTATION.md (GPIO-Nummern, nicht Board-Label)
MOTOR1_A, MOTOR1_B = 12, 13
MOTOR2_A, MOTOR2_B = 14, 27

# "tank"        -> Motor1 = links, Motor2 = rechts (Differentialantrieb)
# "drive_steer" -> Motor1 = Fahren (vor/zurueck), Motor2 = Lenken (links/rechts)
DRIVE_MODE = "tank"

# Kalibrierung: auf True stellen, wenn ein Motor falsch herum dreht
INVERT_1 = False
INVERT_2 = False

# Startwert der Motorleistung; im Webinterface per Schieberegler aenderbar.
# Bewusst gedrosselt - es sind noch keine PPTC-Sicherungen verbaut.
SPEED_DEFAULT = 0.6
# Unter ~20% brummen die Motoren nur, drehen aber nicht durch: das ist ein
# Blockierzustand mit entsprechend hohem Strom. Darum nach unten begrenzt.
SPEED_MIN = 0.2
TURN_RATIO = 0.85  # Lenkgeschwindigkeit relativ zur Fahrgeschwindigkeit

speed = SPEED_DEFAULT  # Laufzeitwert, wird ueber /speed gesetzt

PWM_FREQ = 20000  # 20 kHz, ausserhalb des Hoerbereichs

# Augen: je eine rote LED an einem eigenen Pin, jeweils mit eigenem 100-Ohm-
# Vorwiderstand gegen GND.
EYE_PINS = (21, 22)
EYE_FADE_IN = 2.0  # Sekunden zum Aufdimmen
EYE_HOLD = 1.5  # Sekunden hell halten
EYE_FADE_OUT = 2.0  # Sekunden zum Abdimmen
EYE_PAUSE = 0.8  # Sekunden dunkel bleiben
EYE_MAX = 1.0  # Maximalhelligkeit, 0.0 - 1.0
EYE_PWM_FREQ = 1000  # fuer LEDs reicht 1 kHz, kein sichtbares Flimmern

# Not-Aus: stoppt, wenn der Browser laenger als X Sekunden nichts mehr sendet
DEADMAN_TIMEOUT = 1.5

PORT = 80

# ---------------------------------------------------------------- Motorsteuerung


def _pin(number):
    """Board-Pin zu einer GPIO-Nummer finden (IOxx / Dxx / GPIOxx je nach Build)."""
    for name in ("IO{}".format(number), "D{}".format(number), "GPIO{}".format(number)):
        if hasattr(board, name):
            return getattr(board, name)
    raise ValueError("GPIO {} nicht im board-Modul gefunden".format(number))


class Motor:
    def __init__(self, pin_a, pin_b, inverted=False):
        self.a = pwmio.PWMOut(_pin(pin_a), frequency=PWM_FREQ, duty_cycle=0)
        self.b = pwmio.PWMOut(_pin(pin_b), frequency=PWM_FREQ, duty_cycle=0)
        self.inverted = inverted

    def set(self, speed):
        """speed: -1.0 (rueckwaerts) .. 0 (aus) .. +1.0 (vorwaerts)"""
        if self.inverted:
            speed = -speed
        speed = max(-1.0, min(1.0, speed))
        duty = int(abs(speed) * 65535)
        if speed > 0:
            self.a.duty_cycle = duty
            self.b.duty_cycle = 0
        elif speed < 0:
            self.a.duty_cycle = 0
            self.b.duty_cycle = duty
        else:  # ausrollen lassen
            self.a.duty_cycle = 0
            self.b.duty_cycle = 0


motor1 = Motor(MOTOR1_A, MOTOR1_B, INVERT_1)
motor2 = Motor(MOTOR2_A, MOTOR2_B, INVERT_2)


# ------------------------------------------------------------------------ Augen


class Eyes:
    """Zwei LEDs, die langsam heller werden, hell bleiben und wieder abdimmen."""

    CYCLE = EYE_FADE_IN + EYE_HOLD + EYE_FADE_OUT + EYE_PAUSE

    def __init__(self, pins):
        self.outputs = [
            pwmio.PWMOut(_pin(p), frequency=EYE_PWM_FREQ, duty_cycle=0) for p in pins
        ]
        self.enabled = True

    def level(self, value):
        value = max(0.0, min(1.0, value))
        # Gammakorrektur: das Auge sieht Helligkeit logarithmisch, ohne das
        # Quadrat wirkt die obere Haelfte des Verlaufs wie Stillstand.
        for out in self.outputs:
            out.duty_cycle = int(value * value * 65535)

    def animate(self, now):
        if not self.enabled:
            return
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


# Fehlende oder belegte Pins duerfen den Fahrbetrieb nicht verhindern
try:
    eyes = Eyes(EYE_PINS)
except Exception as err:  # noqa - alles, was pwmio wirft
    print("Augen nicht verfuegbar:", err)
    eyes = None


def drive(command):
    turn = speed * TURN_RATIO
    if DRIVE_MODE == "drive_steer":
        table = {
            "forward": (speed, 0),
            "backward": (-speed, 0),
            "left": (0, -turn),
            "right": (0, turn),
            "forward_left": (speed, -turn),
            "forward_right": (speed, turn),
            "stop": (0, 0),
        }
    else:  # tank
        table = {
            "forward": (speed, speed),
            "backward": (-speed, -speed),
            "left": (-turn, turn),
            "right": (turn, -turn),
            "forward_left": (turn * 0.4, speed),
            "forward_right": (speed, turn * 0.4),
            "stop": (0, 0),
        }
    m1, m2 = table.get(command, (0, 0))
    motor1.set(m1)
    motor2.set(m2)
    return command in table


# ---------------------------------------------------------------- Weboberflaeche

PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>Omnibot 5402</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family:system-ui,sans-serif; background:#15171c; color:#e8eaf0;
         display:flex; flex-direction:column; align-items:center; gap:1rem;
         padding:1.5rem 1rem; touch-action:manipulation; }
  h1 { font-size:1.2rem; letter-spacing:.08em; text-transform:uppercase;
       color:#8a93a8; margin:0; font-weight:600; }
  .pad { display:grid; grid-template-columns:repeat(3,5.5rem);
         grid-template-rows:repeat(3,5.5rem); gap:.6rem; }
  button { font-size:1.6rem; border:1px solid #333a48; border-radius:.9rem;
           background:#232833; color:#e8eaf0; cursor:pointer; -webkit-user-select:none;
           user-select:none; transition:background .08s, transform .08s; }
  button:active { background:#3b6ea5; transform:scale(.95); }
  button.stop { background:#7a2531; border-color:#a13342; font-size:1rem;
                font-weight:700; letter-spacing:.05em; }
  button.stop:active { background:#b23c4e; }
  .spacer { visibility:hidden; }
  .power { width:min(18rem,90vw); display:flex; flex-direction:column; gap:.35rem; }
  .power label { font-size:.85rem; color:#8a93a8; display:flex; justify-content:space-between; }
  .power b { color:#e8eaf0; font-variant-numeric:tabular-nums; font-weight:600; }
  input[type=range] { width:100%; height:1.8rem; accent-color:#3b6ea5; }
  #status { font-size:.85rem; color:#6f7789; min-height:1.2em; font-variant-numeric:tabular-nums; }
</style>
</head>
<body>
  <h1>Omnibot 5402</h1>
  <div class="pad">
    <button class="spacer"></button>
    <button data-cmd="forward">&#9650;</button>
    <button class="spacer"></button>
    <button data-cmd="left">&#9664;</button>
    <button class="stop" data-cmd="stop" data-hold="0">STOP</button>
    <button data-cmd="right">&#9654;</button>
    <button class="spacer"></button>
    <button data-cmd="backward">&#9660;</button>
    <button class="spacer"></button>
  </div>
  <div class="power">
    <label for="pw">Motorleistung <b><span id="pwval">{{SPEED}}</span>&thinsp;%</b></label>
    <input id="pw" type="range" min="20" max="100" step="5" value="{{SPEED}}">
  </div>
  <div id="status">bereit</div>
<script>
const status = document.getElementById('status');
let active = null, timer = null;

async function send(cmd) {
  try {
    await fetch('/cmd?c=' + cmd, { cache: 'no-store' });
    status.textContent = cmd;
  } catch (e) {
    status.textContent = 'Verbindung verloren';
  }
}

function start(cmd) {
  if (active === cmd) return;
  active = cmd;
  send(cmd);
  clearInterval(timer);
  // Totmannschaltung am Leben halten, solange der Knopf gedrueckt ist
  timer = setInterval(() => send(cmd), 500);
}

function stop() {
  active = null;
  clearInterval(timer);
  send('stop');
}

for (const b of document.querySelectorAll('button[data-cmd]')) {
  const cmd = b.dataset.cmd;
  if (b.dataset.hold === '0') { b.addEventListener('click', stop); continue; }
  const press = (e) => { e.preventDefault(); start(cmd); };
  b.addEventListener('pointerdown', press);
  b.addEventListener('pointerup', stop);
  b.addEventListener('pointerleave', stop);
  b.addEventListener('pointercancel', stop);
  b.addEventListener('contextmenu', (e) => e.preventDefault());
}

const pw = document.getElementById('pw'), pwval = document.getElementById('pwval');
let pwTimer = null;
pw.addEventListener('input', () => {
  pwval.textContent = pw.value;
  clearTimeout(pwTimer);  // nicht bei jedem Pixel senden, sonst flutet es den ESP32
  pwTimer = setTimeout(() => fetch('/speed?v=' + pw.value, { cache: 'no-store' }), 120);
});

const keys = { ArrowUp:'forward', ArrowDown:'backward', ArrowLeft:'left', ArrowRight:'right' };
// Pfeiltasten duerfen nicht fahren, waehrend der Regler den Fokus hat
addEventListener('keydown', (e) => {
  if (e.target === pw) return;
  if (keys[e.key] && !e.repeat) start(keys[e.key]);
});
addEventListener('keyup', (e) => { if (e.target !== pw && keys[e.key]) stop(); });
addEventListener('blur', stop);
</script>
</body>
</html>
"""

# ---------------------------------------------------------------- WLAN + Server


def connect():
    if wifi.radio.connected:
        return wifi.radio.ipv4_address
    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
    if not ssid:
        raise RuntimeError("CIRCUITPY_WIFI_SSID fehlt in settings.toml")
    print("Verbinde mit", ssid, "...")
    wifi.radio.connect(ssid, password)
    return wifi.radio.ipv4_address


def respond(sock, body, content_type="text/html; charset=utf-8", status="200 OK"):
    payload = body.encode("utf-8") if isinstance(body, str) else body
    header = (
        "HTTP/1.1 {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n"
    ).format(status, content_type, len(payload))
    sock.send(header.encode("utf-8"))
    # In Haeppchen senden - der ESP32-Socketpuffer ist kleiner als die Seite
    view = memoryview(payload)
    while view:
        sent = sock.send(view)
        view = view[sent:]


ip = connect()
print("Verbunden. Fernsteuerung: http://{}/".format(ip))

pool = socketpool.SocketPool(wifi.radio)
server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", PORT))
server.listen(2)
# Kurzer Timeout, damit die Augen-Animation fluessig weiterlaeuft, waehrend
# der Server auf Verbindungen wartet (ca. 50 Schritte pro Sekunde).
server.settimeout(0.02)

buf = bytearray(1024)
last_command = time.monotonic()
last_name = "stop"
moving = False

while True:
    now = time.monotonic()

    if eyes:
        eyes.animate(now)

    # Totmannschaltung: stoppen, wenn der Browser sich nicht mehr meldet
    if moving and now - last_command > DEADMAN_TIMEOUT:
        drive("stop")
        moving = False
        print("Timeout - gestoppt")

    try:
        conn, addr = server.accept()
    except OSError:
        continue  # nichts angekommen, weiter mit Animation und Timeout-Check

    try:
        conn.settimeout(1.0)
        size = conn.recv_into(buf)
        request = str(buf[:size], "utf-8")
        path = request.split(" ")[1] if " " in request else "/"

        if path.startswith("/cmd"):
            command = "stop"
            if "c=" in path:
                command = path.split("c=")[1].split("&")[0]
            if drive(command):
                last_command = time.monotonic()
                last_name = command
                moving = command != "stop"
                respond(conn, command, "text/plain")
            else:
                respond(conn, "unbekannt", "text/plain", "400 Bad Request")
        elif path.startswith("/speed"):
            if "v=" in path:
                try:
                    speed = int(path.split("v=")[1].split("&")[0]) / 100
                except ValueError:
                    pass  # Unsinn im Parameter: alten Wert behalten
            speed = max(SPEED_MIN, min(1.0, speed))
            if moving:
                drive(last_name)  # Aenderung sofort spuerbar, auch waehrend der Fahrt
                last_command = time.monotonic()
            respond(conn, str(int(speed * 100)), "text/plain")
        elif path == "/" or path.startswith("/?"):
            # Regler soll nach dem Neuladen den tatsaechlichen Wert zeigen
            respond(conn, PAGE.replace("{{SPEED}}", str(int(speed * 100))))
        else:
            respond(conn, "not found", "text/plain", "404 Not Found")
    except Exception as err:  # eine kaputte Anfrage darf den Roboter nicht lahmlegen
        print("Fehler:", err)
        drive("stop")
        moving = False
    finally:
        conn.close()
