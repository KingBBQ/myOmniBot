"""Prueft die Kennlinie gegen die tatsaechlich gefahrenen Messwerte.

Die Zahlen in der ersten Tabelle sind gemessen, nicht gerechnet - wenn jemand
an den Konstanten dreht und diese Tests rot werden, stimmt die Kennlinie nicht
mehr mit dem Roboter ueberein.
"""

import math

import pytest

from omnibot_base import kinematics as k

SEPARATION = 0.170

# duty -> gemessene Geschwindigkeit, Messreihe vom 15.08.2026 bei 6,2 V.
# Die Stufe 200 fehlt bewusst: dort gilt der lineare Fit nicht.
GEMESSEN = [(400, 0.064), (600, 0.114), (800, 0.168), (1000, 0.212)]


@pytest.mark.parametrize("duty,expected", GEMESSEN)
def test_kennlinie_trifft_die_messwerte(duty, expected):
    assert k.speed_from_duty(duty) == pytest.approx(expected, abs=0.005)


@pytest.mark.parametrize("duty,expected", GEMESSEN)
def test_umkehrung_ist_konsistent(duty, expected):
    assert k.duty_from_speed(expected) == pytest.approx(duty, abs=20)


def test_rueckwaerts_ist_symmetrisch():
    assert k.speed_from_duty(-600) == pytest.approx(-k.speed_from_duty(600))
    assert k.duty_from_speed(-0.114) == -k.duty_from_speed(0.114)


def test_stillstand_bleibt_stillstand():
    assert k.duty_from_speed(0.0) == 0
    assert k.speed_from_duty(0) == 0.0
    # Unterhalb des Totbands meldet das Board zwar einen Wert, bewegt sich aber
    # nicht - der darf nicht als Fahrt in die Odometrie wandern.
    assert k.speed_from_duty(100) == 0.0


def test_kleine_sollwerte_werden_hochgezogen():
    """Wer Bewegung anfordert, muss Bewegung bekommen - sonst haengt Nav2."""
    duty = k.duty_from_speed(0.01)
    assert duty == k.MIN_DUTY


def test_sollwerte_werden_begrenzt():
    assert k.duty_from_speed(10.0) == k.MAX_DUTY
    assert k.duty_from_speed(-10.0) == -k.MAX_DUTY


def test_geradeaus_dreht_nicht():
    left, right = k.wheel_speeds(0.15, 0.0, SEPARATION)
    assert left == pytest.approx(right)


def test_drehung_auf_der_stelle():
    left, right = k.wheel_speeds(0.0, 1.0, SEPARATION)
    assert left == pytest.approx(-right)
    # Positives omega ist Linksdrehung (ROS REP-103), also rechtes Rad vorwaerts
    assert right > 0


def test_body_twist_ist_die_umkehrung():
    linear, angular = 0.12, 0.8
    left, right = k.wheel_speeds(linear, angular, SEPARATION)
    zurueck = k.body_twist(left, right, SEPARATION)
    assert zurueck[0] == pytest.approx(linear)
    assert zurueck[1] == pytest.approx(angular)


def test_gemessene_drehrate_passt_zur_spurweite():
    """Bei duty 1000 wurden 2,48 rad/s gemessen - das muss herauskommen."""
    speed = k.speed_from_duty(1000)
    _, angular = k.body_twist(-speed, speed, SEPARATION)
    assert angular == pytest.approx(2.48, abs=0.15)


def test_integration_geradeaus():
    x, y, theta = k.integrate(0.0, 0.0, 0.0, 0.2, 0.0, 1.0)
    assert (x, y, theta) == pytest.approx((0.2, 0.0, 0.0))


def test_integration_halbkreis():
    """Halbe Umdrehung bei 1 m/s und 1 rad/s: Kreis mit Radius 1."""
    x, y, theta = k.integrate(0.0, 0.0, 0.0, 1.0, 1.0, math.pi)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(2.0)
    assert theta == pytest.approx(math.pi)


def test_integration_auf_der_stelle_bewegt_nicht():
    x, y, theta = k.integrate(1.0, 2.0, 0.0, 0.0, 1.0, 0.5)
    assert (x, y) == pytest.approx((1.0, 2.0))
    assert theta == pytest.approx(0.5)
