# Project Todo - Omnibot 5402 Revival

## Phase 1: Fahrbar machen (Drivability)
- [x] CircuitPython Firmware auf RoboESP32 flashen
- [ ] Einkaufsliste bearbeiten und Teile beschaffen
- [ ] Motoren mit dem RoboESP32 verkabeln (inkl. Sicherungen)
- [ ] Basis-Bewegungssteuerung in CircuitPython implementieren
- [ ] Erste Fahrtests durchführen

## Phase 2: Remote Control & Advanced Features
- [x] Originalfernbedienung an einen LOLIN S2 Mini verdrahtet, Belegung mit
      `src/code_pinscan.py` durchgeklingelt
- [x] ESP-NOW Fernsteuerung geschrieben: `src/code_remote.py` (Sender, laeuft
      auf dem S2 Mini) und `src/espnow_link.py` (Empfaenger im Motorknoten)
- [x] `code.py` und `espnow_link.py` auf den RoboESP32 spielen und die
      Funkstrecke zum ersten Mal gegen echte Motoren testen — fährt.
      Gemessen: 1217 Pakete am Stück ohne Aussetzer, ~20 Hz, Sollwerte
      ±600 (geradeaus) und ±500 (Drehung), also sicher über `DEADBAND`.
      Auch `M` (Start/Stop) und `A 1` kommen an. Sender-MAC der
      Fernbedienung: `cc:8d:a2:91:35:c2`
- [x] WLAN-Zugangsdaten aus der `settings.toml` des RoboESP32 entfernen,
      sonst sitzt er auf dem Kanal des Accesspoints und hoert nichts —
      auskommentiert, Board meldet beim Start jetzt `Wi-Fi: off`. Wirksam
      wird das erst nach einem **Hard**-Reset, ein Soft-Reboot liest die
      `settings.toml` nicht neu
- [x] Batterie beschafft (Blei-Zelle)

## Phase 2: ROS2-Navigation mit LIDAR
- [x] LDROBOT STL-19P am PC in einer Ubuntu-24.04-VM getestet (`docs/ros2-setup.md`)
- [x] Chassisgeometrie vermessen (siehe `DOCUMENTATION.md`)
- [x] Serielles Protokoll und Motorknoten-Firmware (`src/code.py`, `src/hardware.py`)
- [x] Firmware am Board testen (`tools/serial_console.py`) - ueber den GPIO-UART
      des Pi auf `/dev/ttyAMA0`, USB-TTL-Adapter nur noch fuer Tests ohne Pi
- [x] **Behoben: der Motorknoten hing sich im Fahrbetrieb auf.** Ursache war
      `ValueError: Invalid buffer` aus `funk.read()` in `espnow_link.py`. Der
      Ringpuffer von `espnow.ESPNow` fasst per Vorgabe nur 526 Bytes; laeuft er
      ueber oder schreibt der Empfangsinterrupt hinein waehrend gelesen wird,
      bleibt er dauerhaft inkonsistent. Ungefangen beendete das `code.py`,
      CircuitPython fiel in die REPL, UART2 verstummte - daher half nur ein
      Reset. Gefunden 16.08.2026, nachdem das Board Diagnosezeilen ueber den
      Link schickte und die Ausnahme im ROS-Log auftauchte.
      - [x] Schleifenkoerper absichern: Motoren stoppen, `# exc` ueber den Link,
            Traceback in die REPL, weiterlaufen
      - [x] `buffer_size=4096` und `_neustart()` in `espnow_link.py`
      - [ ] Im Fahrbetrieb nachweisen, dass die Neustarts greifen - kommen
            `# funk`-Zeilen ohne folgenden Telemetrieausfall, sitzt der Fix
- [x] Kennlinie Duty -> m/s messen (Messläufe `g` und `r` im serial_console)
      - [x] Geradeausfahrt vermessen (15.08.2026): `v = 2,49e-4 * (duty - 140)`,
            Hoechstgeschwindigkeit 0,212 m/s, Fit gilt ab duty 400. Tabelle und
            Konsequenzen fuer Nav2 in `DOCUMENTATION.md`
      - [x] Drehung vermessen (`r`, 15.08.2026): 2,48 rad/s bei duty 1000.
            Effektive Spurweite aus `b_eff = 2v/omega` = ~165 mm, also
            praktisch die geometrischen 170 mm - der befuerchtete
            Skid-Steer-Schlupfaufschlag tritt nicht auf
- [x] Raspberry Pi aufsetzen (Ubuntu Server 24.04 arm64, `docs/pi-setup.md`)
      Achtung: **nicht** Ubuntu 26.04 - dort gibt es nur ROS2 Lyrical, und
      Nav2/slam_toolbox sind dafuer noch nicht gebaut (Stand 08/2026)
- [ ] LIDAR montieren, Montageoffset ausmessen
- [ ] ROS2-Pakete: `omnibot_base`, `omnibot_description`, `omnibot_bringup`
      - [x] Geschrieben und angelegt unter `ros2/`, siehe `ros2/README.md`.
            Kennlinie und Spurweite stecken in `kinematics.py` und sind gegen
            die Messwerte getestet
      - [ ] Auf dem Pi bauen und starten - **noch nie kompiliert**, hier ist
            kein ROS installiert
      - [ ] Parameternamen in `ros2/omnibot_bringup/launch/lidar.launch.py`
            gegen das `ld19.launch.py` des Treibers pruefen
      - [ ] Schwenkrolle laengs vermessen (`caster_x` im URDF ist geschaetzt)
- [ ] SLAM mit `rf2o` + `slam_toolbox`
- [ ] Nav2 in Betrieb nehmen

## Phase 3: Nahbereichssensorik und Encoder
- [ ] IR- oder Sonarsensoren vorne tief nachrüsten (der LIDAR sieht nichts
      unter 40 cm) und über den Range-Sensor-Layer in die Nav2-Costmap geben

- [ ] Encoderscheibe konstruieren und drucken: r = 20 mm, 30 Schlitze
      (Auslegung und Begründung in `DOCUMENTATION.md` — die Zähne des
      Abtriebszahnrads sind zu fein für die 1-mm-Blende der H2010)
- [ ] Filament auf IR-Dichtheit prüfen: Teststreifen in die Gabel halten, die
      LED am Modul muss sicher umschalten (schwarz ist nicht automatisch dicht)
- [ ] Welle für die Scheibe festlegen — sauber, außerhalb des Getriebefetts
- [ ] Halterungen für die H2010-Schranken konstruieren und drucken
- [ ] Encoder auswerten (`countio.Counter`), Telemetriefelder sind vorbereitet
- [ ] Effektive Spurweite feinkalibrieren: zehn Umdrehungen mit laufender
      Odometrie. Grobwert steht schon (~165 mm, siehe `DOCUMENTATION.md`), die
      Korrektur wird klein - erst angehen, wenn Odometrie publiziert

## Einkaufsliste
- [x] PPTC Sicherung (Resettable Fuse) 1A - 1.2A (für jeden Motorkanal)
- [x] USB-TTL-Adapter 3,3V (CP2102/CH340) - für den Firmwaretest am RoboESP32,
      da UART2 auf GPIO16/17 liegt und nicht über den USB-Port des Boards geht
- [x] Gabellichtschranke H2010 mit LM393-Komparator (1 Stück vorhanden)
- [x] Zweite H2010 mit LM393 (eine je Seite). Kein anderer Typ nötig — die
      geprüften Alternativen sind gleich gut oder schlechter, siehe
      `DOCUMENTATION.md`
- [x] Raspberry Pi 4 + USB-Powerbank
