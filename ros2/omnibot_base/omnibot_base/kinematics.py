"""Kinematik und Kennlinie des Omnibot - bewusst ohne ROS-Abhaengigkeit.

Alles, was hier drin steht, ist am 15.08.2026 am Roboter gemessen worden
(Messreihe und Herleitung in DOCUMENTATION.md, Abschnitte "Duty-to-speed
calibration" und "Rotation and the effective wheel separation").

Der Motorknoten auf dem ESP32 kennt keine Geschwindigkeiten, nur Promille
Tastverhaeltnis. Die Umrechnung liegt deshalb hier - so laesst sie sich
nachjustieren, ohne die Firmware anzufassen.
"""

import math

# Kennlinie der Geradeausfahrt, Fit ueber die Stufen 400..1000:
#
#     v [m/s] = MPS_PER_DUTY * (duty - DUTY_OFFSET)
#     duty    = DUTY_PER_MPS * v + DUTY_OFFSET
#
# Restfehler unter 2 Prozent. Gemessen bei 6,2 V an der Bleizelle; mit
# sinkender Spannung wandert die Kurve nach unten.
MPS_PER_DUTY = 2.49e-4
DUTY_OFFSET = 140.0
DUTY_PER_MPS = 1.0 / MPS_PER_DUTY  # = 4016

# Grenzen des sinnvoll nutzbaren Bereichs.
#
# Nach oben die Protokollgrenze. Nach unten die Grenze der Kennlinie: bei
# duty 200 kriecht der Roboter mit 0,023 m/s und liegt damit deutlich ueber
# der Extrapolation der Geraden - dort stimmt das Modell nicht mehr. Unter 400
# wird deshalb nicht kommandiert.
MAX_DUTY = 1000
MIN_DUTY = 400

# Hoechstwerte, die sich daraus ergeben - fuer die Nav2-Konfiguration.
MAX_SPEED = MPS_PER_DUTY * (MAX_DUTY - DUTY_OFFSET)  # 0,214 m/s
MIN_SPEED = MPS_PER_DUTY * (MIN_DUTY - DUTY_OFFSET)  # 0,065 m/s


def duty_from_speed(speed, min_duty=MIN_DUTY, max_duty=MAX_DUTY, zero_eps=1e-3):
    """Radgeschwindigkeit [m/s] in Promille Tastverhaeltnis umrechnen.

    Werte unterhalb von min_duty werden **hochgezogen**, nicht auf 0 gesetzt:
    wer Bewegung anfordert, soll Bewegung bekommen. Sonst wuerde eine
    Nav2-Rotationsrecovery mit kleinem omega den Roboter stehen lassen und die
    Regelung liefe ins Leere. Der Preis ist, dass der Roboter dann schneller
    faehrt als bestellt - deshalb gehoert Nav2s min_vel_x auf MIN_SPEED, damit
    dieser Fall gar nicht erst eintritt.
    """
    if abs(speed) < zero_eps:
        return 0
    duty = DUTY_PER_MPS * abs(speed) + DUTY_OFFSET
    duty = max(min_duty, min(max_duty, duty))
    return int(round(math.copysign(duty, speed)))


def speed_from_duty(duty):
    """Umkehrung: gemeldetes Tastverhaeltnis in [m/s].

    Wird auf die Telemetrie angewendet, nicht auf den Sollwert - das Board
    meldet, was es tatsaechlich anlegt (Totband, Totmannschaltung), und nur
    das gehoert in die Odometrie.
    """
    magnitude = abs(duty)
    if magnitude <= DUTY_OFFSET:
        return 0.0
    return math.copysign(MPS_PER_DUTY * (magnitude - DUTY_OFFSET), duty)


def wheel_speeds(linear, angular, separation):
    """cmd_vel -> Radgeschwindigkeiten (links, rechts) in m/s."""
    half = 0.5 * separation * angular
    return linear - half, linear + half


def body_twist(left, right, separation):
    """Radgeschwindigkeiten -> (linear, angular). Umkehrung von wheel_speeds."""
    return 0.5 * (left + right), (right - left) / separation


def integrate(x, y, theta, linear, angular, dt):
    """Ein Odometrieschritt, exakt fuer konstantes (linear, angular) ueber dt.

    Die Naeherung "geradeaus fahren, dann drehen" summiert bei 10 Hz und
    laengeren Kurvenfahrten sichtbaren Fehler auf; der geschlossene Ausdruck
    kostet nichts und vermeidet das.
    """
    if abs(angular) < 1e-6:
        return x + linear * math.cos(theta) * dt, y + linear * math.sin(theta) * dt, theta

    dtheta = angular * dt
    radius = linear / angular
    new_theta = theta + dtheta
    x += radius * (math.sin(new_theta) - math.sin(theta))
    y -= radius * (math.cos(new_theta) - math.cos(theta))
    return x, y, new_theta
