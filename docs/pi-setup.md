# Raspberry Pi aufsetzen: Ubuntu Server 24.04 + ROS2 Jazzy

Phase 2b: der Pi wird der Bordrechner des Omnibot. Er treibt den LIDAR, spricht
über den seriellen Motorknoten mit dem RoboESP32 und fährt später SLAM und Nav2.
RViz2 bleibt auf der VM am Schreibtisch, der Pi läuft headless.

Der Ablauf ist derselbe wie in `docs/ros2-setup.md`, nur ohne GUI und mit ein
paar Pi-Eigenheiten. Wo es identisch ist, wird dorthin verwiesen statt kopiert.

---

## 0. Warum 24.04 und nicht 26.04

Geprüft am 07.08.2026 direkt gegen `packages.ros.org` (arm64):

| Repo | Distro | Pakete | `navigation2` | `slam-toolbox` |
| :--- | :--- | ---: | :---: | :---: |
| `noble` | Jazzy | 8307 | ja | ja |
| `resolute` | Lyrical Luth | 2228 | **nein** | **nein** |

Ubuntu 26.04 zieht ROS2 Lyrical Luth nach sich (LTS, 22.05.2026, EOL Mai 2031).
Die Distro ist erschienen, aber die Build-Farm ist erst zu gut einem Viertel
durch — genau Nav2 und `slam_toolbox` fehlen noch, also die beiden Pakete,
wegen derer Phase 2 existiert. In `rosdistro` sind sie für Lyrical eingetragen
(nav2 1.5.0-1, slam_toolbox 2.10.0), nur eben noch nicht gebaut.

Dazu kommt: **VM und Pi müssen dieselbe ROS-Distro fahren.** Distro-Mischbetrieb
über DDS ist nicht unterstützt, die Message-Definitionen unterscheiden sich.
Die VM läuft mit Jazzy, also läuft der Pi mit Jazzy. Support bis Mai 2029.

Wenn Lyrical später vollständig ist, ist der Umstieg ein Neuaufsetzen beider
Maschinen — kein Drama, aber nichts, was man mitten in Phase 2 macht.

---

## 1. SD-Karte flashen

Auf dem Manjaro-Host, mit `rpi-imager`:

- **Ubuntu Server 24.04.x LTS (64-bit)** — nicht Desktop, nicht 26.04.
- Vor dem Schreiben das Zahnrad (Vorkonfiguration) benutzen und setzen:
  - Hostname: `omnibot`
  - Benutzer + Passwort
  - **SSH aktivieren, Public Key hinterlegen** (`~/.ssh/id_*.pub`)
  - WLAN-Zugangsdaten **und Ländercode `DE`** — ohne Ländercode bleiben die
    5-GHz-Kanäle gesperrt und das WLAN wirkt kaputt.

> Für die Installation nach Möglichkeit **Ethernet** benutzen. ROS2 Jazzy plus
> Build-Werkzeuge sind gut 2 GB Download; über das WLAN des Pi dauert das.

Erster Boot dauert mehrere Minuten, weil `cloud-init` den Benutzer anlegt und die
Partition vergrößert. Nicht vorher nach dem Login suchen:

```bash
ssh omnibot@omnibot.local
sudo cloud-init status --wait
```

Klappt `omnibot.local` nicht, hilft die IP aus der Router-Oberfläche oder
`ping -c1 omnibot.local`. Danach `ssh-copy-id` erübrigt sich, der Key liegt schon.

---

## 2. Grundkonfiguration

### Zuerst: `noble-updates` in den apt-Quellen nachtragen

**Das Ubuntu-Server-Image für den Pi bringt `noble-updates` nicht mit.** In
`/etc/apt/sources.list.d/ubuntu.sources` stehen ab Werk nur `noble` und
`noble-security`. Das fällt lange nicht auf, weil Security-Updates trotzdem
kommen — und schlägt dann später beim ersten `-dev`-Paket zu:

```
comerr-dev : Depends: libcom-err2 (= 1.47.0-2.4~exp1ubuntu4)
             but 1.47.0-2.4~exp1ubuntu4.1 is to be installed
zlib1g-dev : Depends: zlib1g (= 1:1.3.dfsg-3.1ubuntu2)
             but 1:1.3.dfsg-3.1ubuntu2.1 is to be installed
E: Unable to correct problems, you have held broken packages.
```

Die Laufzeit-Bibliotheken sind schon auf `-updates`-Stand (`…ubuntu4.1`), aber
apt kennt die passenden `-dev`-Pakete nur in der GA-Version (`…ubuntu4`) — die
`.1`-Variante steht ausschließlich in `noble-updates`, und das Repo ist nicht
konfiguriert. Das ist **kein** kaputtes Paket und lässt sich auch nicht mit
`--fix-broken` oder `apt-get -f install` reparieren.

Prüfen und beheben, bevor irgendetwas anderes installiert wird:

```bash
grep -n '^Suites:' /etc/apt/sources.list.d/ubuntu.sources
```

Zeigt die erste Zeile nur `Suites: noble`, dann:

```bash
sudo cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak
sudo sed -i '0,/^Suites: noble$/s//Suites: noble noble-updates noble-backports/' \
  /etc/apt/sources.list.d/ubuntu.sources
```

`0,/…/` sorgt dafür, dass **nur das erste Vorkommen** ersetzt wird — die zweite
Stanza mit `Suites: noble-security` bleibt unangetastet. Ergebnis kontrollieren,
die Datei muss danach so aussehen:

```
Types: deb
URIs: http://ports.ubuntu.com/ubuntu-ports/
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://ports.ubuntu.com/ubuntu-ports/
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

Dann Indizes neu holen und gegenprüfen:

```bash
sudo apt update
apt policy comerr-dev            # muss jetzt ...ubuntu4.1 aus noble-updates zeigen
```

Steht in der Versionstabelle immer noch nur `noble/main`, hat der `sed` nicht
gegriffen — dann von Hand mit `sudo nano /etc/apt/sources.list.d/ubuntu.sources`
editieren und `sudo apt update` wiederholen.

### Grundpakete

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl iw net-tools
```

Nach dem Nachtragen von `noble-updates` zieht das erste `upgrade` deutlich mehr
Pakete als erwartet — das ist normal, das System hing bis dahin auf dem
Release-Stand plus Security.

### Locale auf UTF-8

Identisch zu Abschnitt 2 in `docs/ros2-setup.md` — ROS2 besteht darauf:

```bash
sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
locale
```

### Zeitzone und Zeitsynchronisation

```bash
sudo timedatectl set-timezone Europe/Berlin
timedatectl                      # "System clock synchronized: yes" muss dastehen
```

**Das ist nicht Kosmetik.** Der Pi hat keine batteriegepufferte Uhr. Läuft seine
Zeit gegenüber der VM auseinander, wirft TF `Lookup would require extrapolation
into the past` und SLAM steht, ohne dass irgendwas offensichtlich kaputt wäre.
`systemd-timesyncd` ist ab Werk aktiv und reicht, muss aber laufen.

### brltty entfernen

```bash
sudo apt remove -y brltty
```

`brltty` ist die Braillezeilen-Unterstützung und schnappt sich CP210x- und
CH340-Adapter als vermeintliches Anzeigegerät — dein `/dev/ttyUSB0` verschwindet
dann Sekunden nach dem Einstecken wieder. Der RoboESP32 hängt an genau so einem
CH340 (`1a86:7523`), das ist also keine Vorsichtsmaßnahme, sondern trifft dich
sicher, sobald du seinen REPL-Port an den Pi steckst.

### WLAN-Powersave abschalten

Der WLAN-Chip des Pi schläft im Leerlauf ein. Das kostet Latenz in Sprüngen von
mehreren hundert Millisekunden — die DDS-Discovery von ROS2 verliert darüber
Teilnehmer, Topics erscheinen und verschwinden. Dauerhaft abschalten:

```bash
sudo tee /etc/systemd/system/wifi-powersave-off.service >/dev/null <<'EOF'
[Unit]
Description=Disable WiFi power saving
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/iw dev wlan0 set power_save off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now wifi-powersave-off.service
iw dev wlan0 get power_save     # muss "power save: off" melden
```

### Swap für den Build

Der `colcon`-Build des LIDAR-Treibers ist klein, aber falls dein Pi 4 nur 2 GB
RAM hat, geht ihm beim Parallelbau die Luft aus:

```bash
free -h                          # RAM und vorhandenen Swap ansehen

sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Bei 4 GB oder 8 GB kannst du das überspringen und stattdessen einfach mit
weniger Parallelität bauen (Abschnitt 5).

---

## 3. ROS2 Jazzy installieren

Wortgleich zu den Abschnitten 3 und 4 in `docs/ros2-setup.md` — `$UBUNTU_CODENAME`
löst hier zu `noble` auf statt zu `noble` in der VM, es ist dieselbe Basis.

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository universe

export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F'"' '{print $4}')
echo $ROS_APT_SOURCE_VERSION      # darf nicht leer sein

curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
```

Dann die Basis — **`ros-base`, nicht `desktop`**, RViz2 hat auf dem Pi nichts zu
suchen:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ros-jazzy-ros-base ros-dev-tools
```

Und die Pakete für Phase 2:

```bash
sudo apt install -y \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox \
  ros-jazzy-teleop-twist-keyboard \
  ros-jazzy-tf2-tools \
  ros-jazzy-xacro \
  ros-jazzy-robot-state-publisher \
  ros-jazzy-joint-state-publisher \
  ros-jazzy-demo-nodes-cpp \
  ros-jazzy-demo-nodes-py \
  python3-serial
```

`demo_nodes_*` sind bei `ros-base` **nicht** dabei, anders als bei `desktop` —
deshalb hier explizit, sonst fällt die Funktionsprobe in Abschnitt 4 aus.
`python3-serial` ist pyserial für `tools/upload.py` und `tools/serial_console.py`.

`rosdep` einmalig:

```bash
sudo rosdep init
rosdep update
```

### Umgebung dauerhaft laden

```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
echo "export ROS_DOMAIN_ID=42" >> ~/.bashrc
source ~/.bashrc
```

> `ROS_DOMAIN_ID=42` — **dieselbe Zahl wie in der VM.** Steht dort schon in der
> `.bashrc`. Unterschiedliche IDs sind der häufigste Grund dafür, dass sich zwei
> ROS2-Rechner nicht sehen.

---

## 4. Funktionsprobe, zweimal

### Lokal auf dem Pi

Zwei SSH-Sitzungen:

```bash
# Terminal 1
ros2 run demo_nodes_cpp talker
# Terminal 2
ros2 run demo_nodes_py listener
```

### Über die Maschinen hinweg

Das ist der eigentliche Test. Talker auf dem Pi, Listener in der VM (oder
umgekehrt) — die Zählnachrichten müssen ankommen.

Vorher die Discovery prüfen, das ist aussagekräftiger als `ros2 topic list`:

```bash
# auf dem Pi
ros2 multicast receive
# in der VM
ros2 multicast send
```

Kommt nichts an, ist es **kein ROS-Problem, sondern das Netz**:

- Boxes hängt die VM standardmäßig hinter NAT, und da kommt DDS-Discovery nicht
  durch. Die VM muss auf Bridged Networking oder macvtap umgestellt werden
  (`virt-manager`, gleiches libvirt-Backend, dieselbe VM weiterbenutzbar).
- Pi und VM müssen im selben Subnetz sein.
- Manche Router blockieren Multicast zwischen WLAN und LAN (oft „AP Isolation"
  oder „IGMP Snooping").

Erkennungsmerkmal: lokal auf jeder Maschine funktioniert alles, über die
Maschinen hinweg nichts.

---

## 5. Workspace und LIDAR-Treiber

Wie Abschnitt 6 in `docs/ros2-setup.md`, inklusive **desselben `pthread.h`-Patches** —
auf dem Pi wird frisch geklont, der Patch ist also wieder nötig:

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/ldrobotSensorTeam/ldlidar_stl_ros2.git

cd ~/ros2_ws/src/ldlidar_stl_ros2
for f in $(grep -rl 'pthread_mutex_' --include='*.h' --include='*.cpp' .); do
  grep -q '#include <pthread.h>' "$f" || sed -i '1i #include <pthread.h>' "$f"
  echo "gepatcht: $f"
done

cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --parallel-workers 2
```

`--parallel-workers 2` statt der vier Kerne: der Pi 4 wird sonst warm und
throttelt, und bei 2 GB RAM killt der OOM-Killer einzelne Compiler-Prozesse.
Der Build dauert so ein paar Minuten länger, läuft aber durch.

```bash
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

Reihenfolge in der `.bashrc`: erst `/opt/ros/jazzy/setup.bash`, dann der Workspace.

> **Phase 2d:** `rf2o_laser_odometry` gibt es **nicht** als apt-Paket, weder für
> Jazzy noch für Lyrical. Es kommt später in denselben Workspace:
> `git clone -b ros2 https://github.com/MAPIRlab/rf2o_laser_odometry.git`

---

## 6. Serieller Anschluss zum RoboESP32

```bash
sudo usermod -aG dialout $USER
```

Danach **ab- und wieder anmelden** (bei SSH: Sitzung beenden und neu verbinden),
sonst greift die Gruppe nicht. `groups` muss `dialout` zeigen.

### Welcher Kanal überhaupt

Der RoboESP32 hat einen klassischen ESP32 **ohne natives USB**. Die USB-Buchse
des Boards ist nur eine CP2102-Brücke auf UART0, und UART0 ist bei CircuitPython
die REPL — Konsole, Tracebacks, Auto-Reload. Der Motorknoten liegt deshalb
bewusst woanders (`src/hardware.py:82`):

| Kanal | Anschluss am RoboESP32 | Wofür |
| :--- | :--- | :--- |
| REPL / UART0 | USB-Buchse des Boards | `tools/upload.py`, Fehlermeldungen |
| Motorprotokoll / UART2 | GPIO17 = TX, GPIO16 = RX, **Grove-Port 1**, 115200 8N1 | `tools/serial_console.py`, später der ROS2-Knoten |

Das Protokoll über die USB-Buchse zu fahren geht **nicht** sinnvoll: der Kanal
gehört der REPL, jede `print()`-Zeile und jeder Traceback landet mitten im
Datenstrom. Trennen ließe sich das nur mit `usb_cdc.data`, und das gibt es auf
diesem Board nicht (siehe `AGENTS.md`, Abschnitt „Firmware am Board testen").

### Standardweg: GPIO-UART des Pi, ohne Zusatzhardware

Der Pi hat einen eigenen UART auf dem 40-Pin-Header, und **beide Seiten arbeiten
mit 3,3 V** — es braucht also weder Adapter noch Pegelwandler, nur drei Drähte:

| Pi 5 (40-Pin-Header) | | RoboESP32 (Grove-Port 1) |
| :--- | :---: | :--- |
| Pin 8 — GPIO14, TXD | → | GPIO16 (RX) |
| Pin 10 — GPIO15, RXD | ← | GPIO17 (TX) |
| Pin 6 — GND | ↔ | GND |

TX auf RX kreuzen. GND ist zwingend — fehlt die gemeinsame Masse, bekommst du
nicht etwa gar nichts, sondern sporadischen Datenmüll, und das ist deutlich
schwerer zu erkennen. **3,3 V oder 5 V vom Pi nicht anschließen**, das Board hat
seine eigene Versorgung, und 5 V auf einen ESP32-Pin zerstört ihn.

Ab Werk ist der GPIO-UART unter Ubuntu Server belegt: dort hängt die serielle
Login-Konsole drauf. Solange die läuft, antwortet auf deine Protokollframes ein
Login-Prompt. Also beides umstellen:

**1. UART aktivieren** in `/boot/firmware/config.txt` — nicht `/boot/config.txt`,
das ist der alte Pfad:

```bash
sudo nano /boot/firmware/config.txt
```

Im `[all]`-Abschnitt ergänzen:

```
enable_uart=1
```

**2. Serielle Konsole abschalten.** In `/boot/firmware/cmdline.txt` den Eintrag
`console=serial0,115200` bzw. `console=ttyAMA0,115200` entfernen — die Datei ist
**eine einzige Zeile**, auf keinen Fall umbrechen. Dann den Getty deaktivieren:

```bash
sudo systemctl disable --now serial-getty@ttyAMA0.service
sudo reboot
```

Nach dem Neustart kontrollieren:

```bash
ls -l /dev/serial* /dev/ttyAMA*
dmesg | grep -i ttyAMA
python3 tools/serial_console.py /dev/ttyAMA0
```

Auf dem **Pi 5** ist der GPIO-UART `/dev/ttyAMA0`. Zwei Verwechslungen lauern
hier: `/dev/ttyAMA10` ist der separate 3-Pin-Debug-Anschluss, nicht der Header,
und die zahlreichen Pi-4-Anleitungen im Netz reden von `/dev/ttyS0` — das gilt
für den Pi 5 nicht.

115200 8N1 muss nicht eingestellt werden, das ist `LINK_BAUDRATE` in
`src/hardware.py:24` und wird von `serial_console.py` so geöffnet.

> Preis dieser Lösung: Du verlierst die serielle Konsole als Notzugang, wenn der
> Pi über Netzwerk nicht mehr erreichbar ist. Bei einem headless Roboter mit SSH
> über WLAN **und** Ethernet ist das verschmerzbar — im Zweifel kommt man immer
> noch über Monitor und Tastatur an der HDMI-Buchse ran.

### Alternative: USB-TTL-Adapter

Am Schreibtisch, ohne Pi, oder wenn du die serielle Konsole behalten willst, tut
es ein USB-TTL-Adapter (**3,3 V**, CP2102 oder CH340) an denselben Grove-Pins:
Adapter TX → GPIO16, Adapter RX → GPIO17, GND → GND, VCC bleibt frei. Das Gerät
erscheint dann als `/dev/ttyUSB*` — und damit brauchst du die udev-Regeln unten
für zwei Geräte statt für eines.

### udev-Regel für den LIDAR

Mit dem GPIO-UART hängt am Pi nur noch **ein** USB-Serial-Gerät, der LIDAR. Der
ist damit zuverlässig `/dev/ttyUSB0`, und der ganze Ärger mit vertauschten
Nummern entfällt. Ein sprechender Name ist trotzdem nützlich, sobald in Phase 2c
der eigene Launch kommt:

```bash
sudo tee /etc/udev/rules.d/99-omnibot.rules >/dev/null <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="ttyLIDAR"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="ttyREPL"
EOF

sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/ttyLIDAR
```

VID:PID reicht hier, und zwar auch dann, wenn du den REPL-Port des RoboESP32
zusätzlich ansteckst: der LIDAR ist ein **CP2102 (`10c4:ea60`)**, der RoboESP32
ein **CH340 (`1a86:7523`)** — geprüft am 15.08.2026 mit `udevadm info -q property`.
Die Seriennummern sind bei beiden generisch und taugen nicht zur Unterscheidung,
die Chips aber schon.

Erst wenn zwei Geräte **desselben** Typs stecken — etwa zusätzlich der
USB-TTL-Adapter, der auch ein CP2102 oder CH340 ist — musst du **über den
physischen USB-Port binden**:

```bash
udevadm info -a -n /dev/ttyUSB0 | grep -m2 KERNELS   # zweiter Wert, z. B. 1-1.2
```

```
SUBSYSTEM=="tty", KERNELS=="1-1.2", SYMLINK+="ttyLIDAR"
SUBSYSTEM=="tty", KERNELS=="1-1.3", SYMLINK+="ttyREPL"
```

Die Portpfade sind Platzhalter, trag deine gemessenen Werte ein — und dann
**die Stecker immer in dieselben Buchsen.** Klebeband und Edding sind hier die
zuverlässigste Dokumentation. Zuordnung anschließend in `DOCUMENTATION.md`
eintragen.

### Optional: REPL-Port zusätzlich anstecken

Ein USB-Kabel von der Buchse des RoboESP32 an den Pi ist unabhängig vom
GPIO-UART und stört nicht. Damit spielst du Firmware direkt vom Roboter aus ein,
ohne das Board abzubauen:

```bash
python3 tools/upload.py src/code.py /code.py --run
```

Nur eben: dann sind es zwei USB-Serial-Geräte, und die udev-Regel muss auf
`KERNELS` umgestellt werden.

### LIDAR-Test auf dem Pi

`ld19.launch.py` hat `/dev/ttyUSB0` fest verdrahtet, der eigene Launch in
`omnibot_bringup` mit `/dev/ttyLIDAR` kommt erst in Phase 2c. Da der LIDAR am
GPIO-UART-Aufbau das einzige USB-Serial-Gerät ist, passt der mitgelieferte
Launch für den ersten Test:

```bash
ros2 launch ldlidar_stl_ros2 ld19.launch.py
```

Kontrolle vom Pi aus (`ros2 topic hz /scan` muss ~10 Hz zeigen) **und aus der VM**:

```bash
ros2 topic hz /scan
ros2 topic echo /scan --once
```

Sieht die VM das Topic nicht, ist das Netz schuld, nicht der LIDAR — zurück zu
Abschnitt 4. Zur Sichtprüfung RViz2 in der VM starten, Fixed Frame `base_laser`,
`LaserScan`-Anzeige auf `/scan`.

---

## 7. Projekt-Repo auf den Pi

```bash
cd ~
git clone https://github.com/KingBBQ/myOmniBot.git
cd myOmniBot
```

Für Push-Zugriff einen SSH-Key auf dem Pi erzeugen und in GitHub hinterlegen;
zum reinen Lesen genügt HTTPS.

> `specs/` fehlt im frischen Klon (per `.gitignore` ausgeschlossen) — das ist so
> gewollt und stört hier nicht.

### Die Werkzeuge ohne venv

`tools/upload.py` und `tools/serial_console.py` brauchen nur pyserial, und das ist
seit Abschnitt 3 als `python3-serial` aus apt installiert. Auf dem Pi also direkt:

```bash
python3 tools/serial_console.py /dev/ttyAMA0
python3 tools/upload.py src/code.py /code.py --run
```

Kein `.venv` nötig — anders als auf dem Manjaro-Host, wo `.venv/bin/python`
in `AGENTS.md` steht. Der Grund für den venv dort war `esptool` zum Flashen der
CircuitPython-Firmware, und das ist auf dem Pi nicht nötig.

> `serial_console.py` will den **Motorknoten** auf UART2 (GPIO17/16, Grove-Port 1)
> — am Pi also `/dev/ttyAMA0`. `upload.py` will den **REPL-Port** (USB-Buchse des
> Boards), also `/dev/ttyUSB*` bzw. `/dev/ttyREPL`. Das sind zwei verschiedene
> Anschlüsse am selben Board, siehe Abschnitt 6 und `AGENTS.md`.

---

## 8. Was danach kommt

Damit ist der Pi Bordrechner. Offen bleiben:

- **Phase 2c:** eigene Pakete `omnibot_base`, `omnibot_description`,
  `omnibot_bringup` — inklusive eines Launch, der `/dev/ttyLIDAR` und
  `/dev/ttyAMA0` benutzt statt der Default-Pfade.
- **Autostart:** eine systemd-Unit, die den Bringup beim Booten startet. Erst
  sinnvoll, wenn der Bringup steht — vorher nervt es nur beim Debuggen.
- **Stromversorgung:** die USB-Powerbank aus der Einkaufsliste. Der Pi 4 zieht
  unter Last mit LIDAR gut 1 A; bricht die Spannung ein, korrumpiert das die
  SD-Karte. `dmesg | grep -i voltage` zeigt Unterspannungswarnungen.

---

## Stolperfallen in Kurzform

Die allgemeinen ROS2-Fallen stehen in `docs/ros2-setup.md`. Hier nur, was
Pi-spezifisch dazukommt:

| Symptom | Ursache |
| :--- | :--- |
| `omnibot.local` nicht erreichbar | erster Boot noch nicht durch — `cloud-init status --wait`, oder mDNS im Netz aus |
| `/dev/ttyUSB0` verschwindet nach Sekunden | `brltty` — `sudo apt remove brltty` |
| Topics erscheinen und verschwinden über WLAN | WLAN-Powersave aktiv, siehe Abschnitt 2 |
| `Lookup would require extrapolation into the past` | Uhren von Pi und VM auseinander — `timedatectl` auf beiden |
| Mehrere `/dev/ttyUSB*` tauschen die Plätze | udev-Regel fehlt oder bindet an VID:PID statt an `KERNELS`, siehe Abschnitt 6 |
| Auf `/dev/ttyAMA0` kommt ein Login-Prompt statt Protokoll | serielle Konsole noch aktiv — `console=` aus `cmdline.txt` raus, `serial-getty@ttyAMA0` deaktivieren |
| `/dev/ttyAMA0` fehlt nach dem Reboot | `enable_uart=1` fehlt in `/boot/firmware/config.txt` (nicht `/boot/config.txt`) |
| Motorknoten antwortet gar nicht über GPIO-UART | TX/RX nicht gekreuzt, oder GND vergessen — bei fehlender Masse kommt Datenmüll statt Stille |
| Anleitung im Netz spricht von `/dev/ttyS0` | gilt für Pi 4; am Pi 5 heißt der GPIO-UART `/dev/ttyAMA0` (`ttyAMA10` ist der Debug-Header) |
| `colcon build` bricht ohne Fehlermeldung ab | OOM-Killer — `--parallel-workers 2` und Swap, siehe Abschnitt 2 |
| SD-Karte korrumpiert nach Fahrten | Unterspannung — `dmesg \| grep -i voltage` |
| `ros2 multicast send/receive` schweigt über Maschinen | VM hinter NAT statt Bridge, oder Router blockt Multicast |
| `Package 'demo_nodes_cpp' not found` | bei `ros-base` normal — explizit nachinstallieren, siehe Abschnitt 3 |
| `apt` findet `ros-jazzy-*` nicht | 26.04 statt 24.04 installiert — dort heißt alles `ros-lyrical-*`, siehe Abschnitt 0 |
| `-dev`-Paket will `libfoo (= X)`, aber `X.1 is to be installed` | `noble-updates` fehlt in `ubuntu.sources`, siehe Abschnitt 2 — **nicht** mit `apt -f install` reparierbar |
