# Project Todo - Omnibot 5402 Revival

## Phase 1: Fahrbar machen (Drivability)
- [x] CircuitPython Firmware auf RoboESP32 flashen
- [ ] Einkaufsliste bearbeiten und Teile beschaffen
- [ ] Motoren mit dem RoboESP32 verkabeln (inkl. Sicherungen)
- [ ] Basis-Bewegungssteuerung in CircuitPython implementieren
- [ ] Erste Fahrtests durchführen

## Phase 2: Remote Control & Advanced Features
- [ ] ESP-NOW Fernsteuerung aufbauen
- [x] Batterie beschafft (Blei-Zelle)

## Phase 2: ROS2-Navigation mit LIDAR
- [x] LDROBOT STL-19P am PC in einer Ubuntu-24.04-VM getestet (`docs/ros2-setup.md`)
- [x] Chassisgeometrie vermessen (siehe `DOCUMENTATION.md`)
- [x] Serielles Protokoll und Motorknoten-Firmware (`src/code.py`, `src/hardware.py`)
- [ ] Firmware am Board testen (`tools/serial_console.py`) - braucht USB-TTL-Adapter
- [ ] Kennlinie Duty -> m/s messen (Messläufe `g` und `r` im serial_console)
- [ ] Raspberry Pi 4 aufsetzen (Ubuntu Server 24.04 arm64)
- [ ] LIDAR montieren, Montageoffset ausmessen
- [ ] ROS2-Pakete: `omnibot_base`, `omnibot_description`, `omnibot_bringup`
- [ ] SLAM mit `rf2o` + `slam_toolbox`
- [ ] Nav2 in Betrieb nehmen

## Phase 3: Nahbereichssensorik und Encoder
- [ ] IR- oder Sonarsensoren vorne tief nachrüsten (der LIDAR sieht nichts
      unter 40 cm) und über den Range-Sensor-Layer in die Nav2-Costmap geben

- [ ] Halterungen für Gabellichtschranken konstruieren und drucken
- [ ] Zähnezahl des Abtriebszahnrads bestimmen
- [ ] Encoder auswerten (`countio.Counter`), Telemetriefelder sind vorbereitet
- [ ] Effektive Spurweite kalibrieren (Skid-Steer-Schlupf, siehe `DOCUMENTATION.md`)

## Einkaufsliste
- [ ] PPTC Sicherung (Resettable Fuse) 1A - 1.2A (für jeden Motorkanal)
- [ ] USB-TTL-Adapter 3,3V (CP2102/CH340) - für den Firmwaretest am RoboESP32,
      da UART2 auf GPIO16/17 liegt und nicht über den USB-Port des Boards geht
- [ ] Gabellichtschranken-Module mit LM393-Komparator (2 Stück, Phase 3)
- [ ] Raspberry Pi 4 + USB-Powerbank
