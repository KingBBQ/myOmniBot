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
- `tools/upload.py` - REPL-Uploader (nutzt pyserial aus `.venv`).
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

## Hardware-Stand (Vorsicht beim Testen)

- Motoren sind laut `TODO.md` **noch nicht verkabelt**, die PPTC-Sicherungen
  (1A - 1.2A pro Kanal) sind **noch nicht verbaut**. Fahrbefehle sind daher
  ungetestet - der Motortreiber vertraegt nur 1A Dauerlast und brennt bei
  blockierten Motoren durch.
- `SPEED` ist deshalb auf 0.6 gedrosselt; erst nach Einbau der Sicherungen erhoehen.
- Pinbelegung und Hardware-Details stehen in `DOCUMENTATION.md`.
- Ob der Omnibot Panzerlenkung (zwei Antriebsmotoren) oder Antrieb + Lenkmotor
  hat, ist noch nicht verifiziert - `DRIVE_MODE` deckt beide Faelle ab.
