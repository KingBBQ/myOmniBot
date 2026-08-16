# espnow_link.py - ESP-NOW-Gegenstelle auf dem Roboter
#
# Nimmt die Pakete der Fernbedienung (src/code_remote.py) entgegen und gibt sie
# als Protokollzeilen heraus - dieselben Zeilen, die auch ueber die serielle
# Leitung kommen. code.py verarbeitet beide Quellen mit derselben handle().
#
# Rueckkanal: sobald sich eine Fernbedienung gemeldet hat, wird ihre MAC als
# Peer eingetragen und sie bekommt ~5 Hz ein Statuspaket. Nur damit kann die
# Fernbedienung anzeigen, ob sie ueberhaupt gehoert wird.
#
# Der Kanal ist der Haken an ESP-NOW: beide Seiten muessen auf demselben
# WLAN-Kanal sitzen. Ohne Verbindung zu einem Accesspoint ist das bei beiden
# Kanal 1. Verbindet sich der Roboter dagegen per settings.toml ins WLAN,
# uebernimmt er den Kanal des Accesspoints und hoert die Fernbedienung nicht
# mehr. Deshalb wird eine bestehende Station hier getrennt - und deshalb
# gehoeren die WLAN-Zugangsdaten fuer den Fahrbetrieb aus settings.toml raus.

import time

MAX_LINE = 64

STATUS_PERIOD = 0.2  # 5 Hz


class RemoteLink:
    """ESP-NOW-Empfaenger. Wirft beim Anlegen, wenn kein Funk verfuegbar ist."""

    def __init__(self, allowed_mac=None):
        import espnow
        import wifi

        wifi.radio.enabled = True
        if wifi.radio.connected:
            # Trennen ist nur die Notbremse: der Funkkanal bleibt unter Umstaenden
            # trotzdem der des Accesspoints, und dann hoert das Board die
            # Fernbedienung nicht. Sauber wird es erst ohne Zugangsdaten.
            print("ESP-NOW: WLAN-Verbindung wird getrennt.")
            print("ESP-NOW: WLAN-Zugangsdaten gehoeren aus der settings.toml -")
            print("ESP-NOW: sonst sitzt das Board auf dem Kanal des Accesspoints.")
            wifi.radio.stop_station()

        self._espnow = espnow
        self.funk = espnow.ESPNow()
        self.allowed_mac = allowed_mac  # None = jede Fernbedienung wird akzeptiert
        self.peer = None
        self.peer_mac = None
        self.last_packet = 0.0
        self._last_status = 0.0
        self.mac = bytes(wifi.radio.mac_address)
        self.errors = 0
        self.last_error = None

    def lines(self):
        """Alle anstehenden Pakete abholen und als Protokollzeilen zurueckgeben."""
        out = []
        while True:
            try:
                paket = self.funk.read()
            except Exception as err:  # noqa - Funkfehler stoppt den Antrieb nicht
                # Ein Fehler beim Lesen darf den Fahrbetrieb am seriellen Link
                # nicht mitreissen. Gezaehlt wird trotzdem: haeufen sich die
                # Fehler, ist der Funk der Ausloeser und nicht der Antrieb.
                self.errors += 1
                self.last_error = "{}: {}".format(type(err).__name__, err)
                break
            if paket is None:
                break

            if self.allowed_mac is not None and bytes(paket.mac) != self.allowed_mac:
                continue  # fremder Sender

            self.last_packet = time.monotonic()
            self._remember(paket.mac)

            for roh in paket.msg.split(b"\n"):
                if not roh or len(roh) > MAX_LINE:
                    continue
                try:
                    out.append(str(roh, "utf-8").strip())
                except Exception:  # noqa - kaputte Bytes verwerfen, nicht abstuerzen
                    pass
        return out

    def _remember(self, mac):
        """Absender als Peer eintragen, damit der Rueckkanal funktioniert."""
        mac = bytes(mac)
        if self.peer_mac == mac:
            return
        try:
            if self.peer is not None:
                self.funk.peers.remove(self.peer)
            self.peer = self._espnow.Peer(mac=mac)
            self.funk.peers.append(self.peer)
            self.peer_mac = mac
            print("ESP-NOW: Fernbedienung", ":".join("%02x" % b for b in mac))
        except Exception as err:  # noqa - Peerliste voll o.ae.
            print("ESP-NOW: Peer nicht eintragbar:", err)
            self.peer = None
            self.peer_mac = None

    def connected(self, now, timeout=1.0):
        return self.peer_mac is not None and now - self.last_packet < timeout

    def status(self, now, manuell, faehrt):
        """Statuspaket senden, hoechstens alle STATUS_PERIOD Sekunden."""
        if self.peer is None or now - self._last_status < STATUS_PERIOD:
            return
        self._last_status = now
        try:
            self.funk.send(
                "a {} {}\n".format(1 if manuell else 0, 1 if faehrt else 0).encode(
                    "utf-8"
                ),
                self.peer,
            )
        except Exception:  # noqa - ausser Reichweite ist kein Fehlerfall
            pass
