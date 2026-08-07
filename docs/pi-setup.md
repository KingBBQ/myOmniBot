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

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl iw net-tools
```

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
dann Sekunden nach dem Einstecken wieder. Am Roboter hängen zwei solche Adapter,
also weg damit, bevor es Rätsel aufgibt.

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

## 6. Serielle Rechte und feste Gerätenamen

```bash
sudo usermod -aG dialout $USER
```

Danach **ab- und wieder anmelden** (bei SSH: Sitzung beenden und neu verbinden),
sonst greift die Gruppe nicht. `groups` muss `dialout` zeigen.

### Die udev-Regel, jetzt wird sie ernst

In der VM hing nur der LIDAR. Am Roboter hängen **zwei** USB-Serial-Adapter am
Pi — LIDAR und RoboESP32 — und `/dev/ttyUSB0`/`ttyUSB1` tauschen beim Booten die
Plätze. Beide sind sehr wahrscheinlich CP2102 mit `10c4:ea60` und der generischen
Seriennummer `0001`, damit sind VID:PID und Seriennummer als Unterscheidung wertlos.

Also **über den physischen USB-Port binden**. Beide Geräte anstecken, dann für
jedes ermitteln, an welchem Port es hängt:

```bash
ls -l /dev/ttyUSB*
udevadm info -a -n /dev/ttyUSB0 | grep -m2 KERNELS
udevadm info -a -n /dev/ttyUSB1 | grep -m2 KERNELS
```

Der zweite `KERNELS`-Wert ist der Portpfad, etwa `1-1.2`. Notiere dir, welcher
Wert zu welchem Gerät gehört (der LIDAR dreht hörbar, wenn er Strom bekommt —
das ist die einfachste Unterscheidung; sonst ein Gerät abziehen und schauen,
welches `/dev/ttyUSB*` verschwindet).

```bash
sudo tee /etc/udev/rules.d/99-omnibot.rules >/dev/null <<'EOF'
SUBSYSTEM=="tty", KERNELS=="1-1.2", SYMLINK+="ttyLIDAR"
SUBSYSTEM=="tty", KERNELS=="1-1.3", SYMLINK+="ttyMOTOR"
EOF

sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/ttyLIDAR /dev/ttyMOTOR
```

Die Portpfade oben sind Platzhalter — trag deine gemessenen Werte ein. Und dann:
**die beiden USB-Stecker immer in dieselben Buchsen.** Klebeband und Edding sind
hier die zuverlässigste Dokumentation.

Trag die Zuordnung anschließend in `DOCUMENTATION.md` ein.

### LIDAR-Test auf dem Pi

`ld19.launch.py` hat `/dev/ttyUSB0` fest verdrahtet, der eigene Launch in
`omnibot_bringup` mit `/dev/ttyLIDAR` kommt erst in Phase 2c. Für den ersten
Test auf dem Pi genügt der mitgelieferte Launch, solange der LIDAR zufällig
`ttyUSB0` ist:

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
python3 tools/serial_console.py /dev/ttyMOTOR
python3 tools/upload.py src/code.py /code.py --run
```

Kein `.venv` nötig — anders als auf dem Manjaro-Host, wo `.venv/bin/python`
in `AGENTS.md` steht. Der Grund für den venv dort war `esptool` zum Flashen der
CircuitPython-Firmware, und das ist auf dem Pi nicht nötig.

> `upload.py` will den **REPL-Port** des RoboESP32 (USB-Buchse des Boards),
> `serial_console.py` den **Motorknoten** auf UART2 (GPIO17/16, Grove-Port 1).
> Das sind zwei verschiedene Anschlüsse am selben Board. Details in `AGENTS.md`.

---

## 8. Was danach kommt

Damit ist der Pi Bordrechner. Offen bleiben:

- **Phase 2c:** eigene Pakete `omnibot_base`, `omnibot_description`,
  `omnibot_bringup` — inklusive eines Launch, der `/dev/ttyLIDAR` und
  `/dev/ttyMOTOR` benutzt statt der Default-Pfade.
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
| LIDAR und Motorboard tauschen `/dev/ttyUSB*` | udev-Regel fehlt oder bindet an VID:PID statt an `KERNELS` |
| `colcon build` bricht ohne Fehlermeldung ab | OOM-Killer — `--parallel-workers 2` und Swap, siehe Abschnitt 2 |
| SD-Karte korrumpiert nach Fahrten | Unterspannung — `dmesg \| grep -i voltage` |
| `ros2 multicast send/receive` schweigt über Maschinen | VM hinter NAT statt Bridge, oder Router blockt Multicast |
| `Package 'demo_nodes_cpp' not found` | bei `ros-base` normal — explizit nachinstallieren, siehe Abschnitt 3 |
| `apt` findet `ros-jazzy-*` nicht | 26.04 statt 24.04 installiert — dort heißt alles `ros-lyrical-*`, siehe Abschnitt 0 |
