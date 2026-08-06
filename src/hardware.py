# hardware.py - alles, was sich zwischen den Boards unterscheidet.
#
# code.py bleibt dadurch boardunabhaengig. Ein Wechsel vom RoboESP32 auf den
# MakerPi RP2040 aendert nur diese Datei und die Konstante BOARD.
#
# Pinbelegungen laut Datenblatt:
#
#   RoboESP32 Rev 1.1
#     M1A/M1B = GPIO12/13, M2A/M2B = GPIO14/27, PWM max 20 kHz, 1 A pro Kanal
#     UART2 auf Grove-Port 1: TX = GPIO17, RX = GPIO16
#     Augen-LEDs auf GPIO21/22 (belegt damit den I2C-Port)
#
#   MakerPi RP2040
#     M1A/M1B = GP8/GP9, M2A/M2B = GP10/GP11, PWM max 20 kHz, 1 A pro Kanal
#     Datenkanal ueber natives USB (usb_cdc.data), braucht boot.py
#     Belegt laut Datenblatt: GP18 RGB-LED, GP20/21 Taster, GP22 Buzzer,
#     GP12-GP15 Servos

import board

# Aktives Board: "roboesp32" oder "makerpi2040"
BOARD = "roboesp32"

LINK_BAUDRATE = 115200

_PROFILES = {
    "roboesp32": {
        "motor_left": (12, 13),
        "motor_right": (14, 27),
        "pwm_freq": 20000,  # Datenblattgrenze, zugleich ausserhalb des Hoerbereichs
        "eye_pins": (21, 22),
        "link": "uart",
        "uart_tx": 17,
        "uart_rx": 16,
    },
    "makerpi2040": {
        "motor_left": (8, 9),
        "motor_right": (10, 11),
        "pwm_freq": 20000,
        "eye_pins": (16, 17),  # frei laut Datenblatt; bei Bedarf anpassen
        "link": "usb_cdc",
    },
}

if BOARD not in _PROFILES:
    raise ValueError("Unbekanntes BOARD: {}".format(BOARD))

_PROFILE = _PROFILES[BOARD]

MOTOR_LEFT = _PROFILE["motor_left"]
MOTOR_RIGHT = _PROFILE["motor_right"]
PWM_FREQ = _PROFILE["pwm_freq"]
EYE_PINS = _PROFILE["eye_pins"]


def pin(number):
    """Board-Pin zu einer GPIO-Nummer finden.

    Die Buildnamen unterscheiden sich: der doit_esp32_devkit_v1-Build benennt
    Pins je nach Version IOxx/Dxx/GPIOxx, der RP2040-Build GPxx.
    """
    for name in (
        "IO{}".format(number),
        "D{}".format(number),
        "GPIO{}".format(number),
        "GP{}".format(number),
    ):
        if hasattr(board, name):
            return getattr(board, name)
    raise ValueError("GPIO {} nicht im board-Modul gefunden".format(number))


def open_link():
    """Serielle Verbindung zum Companion Computer oeffnen.

    Das Ergebnis hat read(n), write(bytes) und in_waiting - beide Varianten
    verhalten sich fuer unsere Zwecke gleich.
    """
    kind = _PROFILE["link"]

    if kind == "uart":
        # UART0 ist beim klassischen ESP32 die REPL und bleibt fuer Uploads und
        # Debugausgaben reserviert. Der Companion Computer haengt an UART2.
        import busio

        return busio.UART(
            pin(_PROFILE["uart_tx"]),
            pin(_PROFILE["uart_rx"]),
            baudrate=LINK_BAUDRATE,
            timeout=0,  # nie blockieren, die Hauptschleife pollt
            receiver_buffer_size=256,
        )

    if kind == "usb_cdc":
        # Zweiter CDC-Kanal neben der REPL - wird in boot.py freigeschaltet.
        import usb_cdc

        if usb_cdc.data is None:
            raise RuntimeError("usb_cdc.data fehlt - boot.py aufs Board spielen")
        usb_cdc.data.timeout = 0
        return usb_cdc.data

    raise ValueError("Unbekannter Link-Typ: {}".format(kind))
