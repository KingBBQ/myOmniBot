# Agents Guide - MyOmniBot

Revival eines Tomy Omnibot 5402: die Kassetten-Steuerung wird durch einen
Cytron RoboESP32 mit CircuitPython 10.2.1 ersetzt.

Dokumentation und TODOs sind auf Deutsch - bitte beibehalten.

## Board & Upload (das Wichtigste)

Der RoboESP32 nutzt einen klassischen ESP32 **ohne natives USB**. Es gibt daher
**kein CIRCUITPY-Laufwerk** - der USB-Port ist nur ein UART-Bruecke auf
`/dev/ttyUSB0`. Dateien gehen ausschliesslich ueber die serielle REPL aufs Board
(genau das macht Thonnys Dateibrowser auch intern).

```bash
.venv/bin/python tools/upload.py src/code.py /code.py --run
```

`--run` loest einen Soft-Reboot aus und zeigt die Board-Ausgabe (inkl. IP-Adresse).

Der serielle Port kann nur von **einem** Programm gleichzeitig belegt werden:
Thonny muss die Verbindung trennen ("Stop/Restart" reicht nicht immer), sonst
schlaegt der Upload mit einem Timeout fehl.

## Repo-Layout

- `src/code.py` - Quelle der Wahrheit; wird als `/code.py` aufs Board gespielt.
  Nie direkt auf dem Board editieren, sonst laufen die Staende auseinander.
  Seit Phase 2 ein serieller Motorknoten, kein Webserver mehr.
- `src/hardware.py` - Pinbelegung, PWM-Frequenz und serielle Verbindung je Board.
  Der Boardwechsel RoboESP32 <-> MakerPi RP2040 aendert nur diese Datei.
- `src/boot.py` - nur fuer Boards mit nativem USB (RP2040), schaltet
  `usb_cdc.data` frei. Auf dem ESP32 unnoetig.
- `src/espnow_link.py` - ESP-NOW-Gegenstelle auf dem Roboter. Liefert die
  Pakete der Fernbedienung als Protokollzeilen an dieselbe `handle()`.
- `src/code_remote.py` - Fernbedienung auf dem LOLIN S2 Mini. Kommt als
  `/code.py` aufs CIRCUITPY-Laufwerk, nicht ueber `tools/upload.py`.
- `src/code_pinscan.py` - Pin-Scanner fuer den S2 Mini, mit dem die
  Tastenbelegung durchgeklingelt wurde. Aufgehoben fuer den naechsten Umbau.
- `src/code_webremote.py` - die Webserver-Handsteuerung aus Phase 1, als
  Rueckfallebene aufgehoben.
- `tools/upload.py` - REPL-Uploader (nutzt pyserial aus `.venv`).
- `tools/serial_console.py` - Testclient fuer den Motorknoten: fahren, pingen,
  Telemetrie mitlesen und die Kennlinie kalibrieren, alles ohne ROS.
- `docs/ros2-setup.md` - ROS2 Jazzy und LIDAR-Inbetriebnahme in der VM, Schritt
  fuer Schritt.
- `docs/pi-setup.md` - der Bordrechner: Ubuntu Server 24.04 arm64 und ROS2 Jazzy
  auf dem Raspberry Pi, udev-Regeln fuer die beiden Serial-Adapter.
- `ros2/` - die drei ROS2-Pakete (`omnibot_base`, `omnibot_description`,
  `omnibot_bringup`). Liegen im Repo, kommen per Symlink nach `~/ros2_ws/src`.
  Details in `ros2/README.md`. **Nicht mit `src/` verwechseln** - dort liegt die
  Firmware fuers Board, hier der Code fuer den Bordrechner.
- `firmware/`, `pics/` - Firmware-Images und Fotos.
- `specs/` - Datenblaetter Dritter, nur lokal vorhanden (per `.gitignore`
  ausgeschlossen). Auf einem frischen Klon fehlt der Ordner.
- `.venv` - enthaelt `esptool` und `pyserial`. Kein `requirements.txt` vorhanden.

`settings.toml` liegt nur auf dem Board (WLAN-Zugangsdaten) und ist bewusst
nicht im Repo. CircuitPython verbindet sich damit automatisch beim Start.

## Firmware-Konventionen

- Keine externen CircuitPython-Libraries. Der Webserver ist bewusst mit
  `socketpool` von Hand gebaut, damit kein `lib/`-Bundle aufs Board muss.
- Board-Pins ueber die Helferfunktion `_pin(nummer)` aufloesen - der
  `doit_esp32_devkit_v1`-Build benennt Pins je nach Version `IOxx`/`Dxx`/`GPIOxx`.
- Kalibrier-Schalter stehen als Konstanten oben in `code.py`
  (`DRIVE_MODE`, `INVERT_1`, `INVERT_2`, `SPEED`). Richtungen dort korrigieren,
  nicht in der Ansteuerungslogik.
- Umlaute in Quelltext-Kommentaren vermeiden (ae/oe/ue), sonst gibt es beim
  Uebertragen ueber die REPL Encoding-Aerger.
- ESP-NOW: `funk.send(msg)` **ohne** zweites Argument scheitert mit
  `ESP-NOW error 0x3069` (`ESP_ERR_ESPNOW_NOT_FOUND`), auch wenn der Peer in
  `funk.peers` steht. Der Peer muss mitgegeben werden: `funk.send(msg, peer)`.
  Am Board verifiziert mit CircuitPython 10.2.1 - die API-Doku legt anderes nahe.
- ESP-NOW und WLAN teilen sich den Funkkanal. Verbindet sich ein Board per
  `settings.toml` in ein WLAN, uebernimmt es den Kanal des Accesspoints und
  hoert die Gegenstelle nicht mehr. Fuer den Fahrbetrieb gehoeren die
  WLAN-Zugangsdaten deshalb aus der `settings.toml` des RoboESP32 heraus.

## Hardware-Stand (Vorsicht beim Testen)

- Motoren sind verkabelt, Phase 1 ist gefahren. Die PPTC-Sicherungen
  (1A - 1.2A pro Kanal) sind **noch nicht verbaut** - der Motortreiber vertraegt
  nur 1A Dauerlast und brennt bei blockierten Motoren durch. Deshalb nicht
  dauerhaft mit voller Leistung gegen ein Hindernis fahren.
- Antrieb: **Skid-Steer, fährt caster-first** (Schwenkrolle vorne, Antrieb hinten).
  Vorsicht beim Rotieren: Die Front schwingt weite Boegen aus.
- Der Antrieb ist Skid-Steer: vier Raeder in Tandempaaren, zwei pro Seite,
  je Seite ein Motor, dazu eine freie Schwenkrolle mittig. Das Differentialmodell
  gilt, aber die geometrische Spurweite taugt nicht fuers Odometriemodell -
  Begruendung und Kalibriervorschrift stehen in `DOCUMENTATION.md`.
- `DEADBAND = 0.2` in `code.py`: unter 20 Prozent brummen die Motoren nur und
  ziehen Blockierstrom. Solche Sollwerte werden auf 0 gesetzt. Der Host darf
  gar nicht erst dort hinein kommandieren.
- Chassisgeometrie, LIDAR-Messwerte und Pinbelegung stehen in `DOCUMENTATION.md`.

## ROS2 & Bordrechner (Pi)

- **OS:** Nur Ubuntu 24.04 arm64 verwenden. Ubuntu 26.04 vermeiden (ROS2 Jazzy /
  Nav2/slam_toolbox Pakete fehlen dort noch).
- **LIDAR:** `range_max` in der Nav2 costmap config manuell limitieren; die
  advertised 25m des Treibers sind unrealistisch und erzeugen Rauschen.
- Hardware: LIDAR Yaw ist nominal 0 (blickt nach +x), muss aber physisch
  verifiziert werden, da Skews das Mapping ruinieren.
- **Die gemessenen Fahrzahlen stehen an genau einer Stelle:**
  `ros2/omnibot_base/omnibot_base/kinematics.py`. Kennlinie, Spurweite und
  Grenzen gehoeren dort hin und nirgendwo sonst - die Tests im selben Paket
  pruefen sie gegen die tatsaechlich gefahrenen Messwerte.
- Odometrie wird aus der **Telemetrie** gebildet, nicht aus dem Sollwert. Das
  Board meldet das real angelegte Tastverhaeltnis, also schlagen Totband und
  Totmannschaltung korrekt durch.

## Firmware am Board testen

Der Motorknoten haengt beim RoboESP32 an **UART2 (GPIO17 = TX, GPIO16 = RX,
Grove-Port 1)**, nicht am USB-Port des Boards - der ist die REPL (CH340,
`1a86:7523`, `/dev/ttyUSB*`).

Am Roboter geht diese Leitung direkt an den **GPIO-UART des Raspberry Pi**
(Pin 8 = GPIO14/TXD an GPIO16, Pin 10 = GPIO15/RXD an GPIO17, Pin 6 = GND),
dort also `/dev/ttyAMA0` - siehe `docs/pi-setup.md`, Abschnitt 6. Nur zum Testen
am Schreibtisch ohne Pi braucht es einen USB-TTL-Adapter (3,3 V) an denselben
Pins:

```bash
.venv/bin/python tools/upload.py src/hardware.py /hardware.py
.venv/bin/python tools/upload.py src/code.py /code.py --run
.venv/bin/python tools/serial_console.py /dev/ttyUSB0
```

Beim MakerPi RP2040 entfaellt der Adapter: dort zusaetzlich `src/boot.py` aufs
Board spielen, einmal Reset druecken, und der Datenkanal liegt als zweites
CDC-Geraet am selben USB-Kabel.
