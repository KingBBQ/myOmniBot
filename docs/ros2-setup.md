# ROS2-Setup: Ubuntu 24.04 VM + LIDAR-Test

Anleitung für Phase 2a-0: ROS2 Jazzy von Hand installieren und das LDROBOT
STL-19P am Schreibtisch testen — noch ohne Roboter, ohne Raspberry Pi.

Derselbe Ablauf wird später auf dem Pi nochmal gebraucht (Abschnitt 9).

---

## 1. VM in GNOME Boxes

- **Ubuntu 24.04 LTS Desktop** (nicht Server — RViz2 soll in der VM laufen)
- **4 GB RAM, 4 vCPUs, 30 GB Platte** als Minimum. Weniger macht `colcon build` zäh.
- Nach der Installation in der VM:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y openssh-server git
```

Mit dem SSH-Server kannst du aus einem Terminal auf dem Manjaro-Host in die VM
arbeiten, statt im Boxes-Fenster zu tippen — Copy/Paste funktioniert dann normal.
IP der VM: `ip addr show`.

### USB-Passthrough für das LIDAR

Boxes: Zahnrad-Menü der VM → **Geräte & Freigaben** → USB-Gerät durchreichen.
Der USB-Adapter des STL-19P taucht dort als CP210x- oder CH340-Serial-Adapter auf.

> **Das muss nach jedem Aus- und Wiedereinstecken des Kabels erneut aktiviert
> werden.** Wenn dich das nervt: `virt-manager` läuft auf demselben
> libvirt-Backend wie Boxes, hat echtes Host-Device-Passthrough und du kannst
> dieselbe VM damit weiterbenutzen — kein Neuaufsetzen nötig.

Prüfen, ob das Gerät angekommen ist:

```bash
lsusb
ls -l /dev/ttyUSB*
```

---

## 2. Locale auf UTF-8

ROS2 besteht auf einer UTF-8-Locale. Offizieller Ablauf:

```bash
locale                                    # aktuellen Stand ansehen

sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

locale                                    # kontrollieren
```

`de_DE.UTF-8` täte es auch — entscheidend ist nur UTF-8. Der Einheitlichkeit mit
der Doku halber hier `en_US.UTF-8`.

---

## 3. ROS2-Paketquelle einbinden

Zuerst das `universe`-Repository:

```bash
sudo apt install software-properties-common
sudo add-apt-repository universe
```

Dann die ROS2-Quelle. Das läuft inzwischen über ein eigenes `.deb`, das Schlüssel
und Sourcelist mitbringt und sich selbst per apt aktuell hält:

```bash
sudo apt update && sudo apt install curl -y

export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F'"' '{print $4}')

curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"

sudo dpkg -i /tmp/ros2-apt-source.deb
```

Kontrolle: `echo $ROS_APT_SOURCE_VERSION` darf nicht leer sein. Wenn doch, hat der
GitHub-API-Abruf nicht geklappt (Rate-Limit) — dann die Versionsnummer manuell von
den Releases in `ros-infrastructure/ros-apt-source` holen und einsetzen.

> Ältere Anleitungen im Netz zeigen stattdessen `ros-archive-keyring.gpg` plus
> eine handgeschriebene `/etc/apt/sources.list.d/ros2.list`. Das funktioniert noch,
> ist aber der abgelöste Weg — nicht mischen.

---

## 4. ROS2 Jazzy installieren

```bash
sudo apt update
sudo apt upgrade
sudo apt install ros-jazzy-desktop
```

`desktop` statt `ros-base`, weil RViz2, die Demo-Nodes und die Tutorials mit
drinstecken — genau das, was du zum Kennenlernen brauchst. Auf dem Pi wird später
`ros-jazzy-ros-base` genommen (kein GUI nötig).

**Kontrolle, dass wirklich die Desktop-Variante drin ist:**

```bash
ros2 pkg list | wc -l
```

Bei `desktop` sind das grob 350–400 Pakete, bei `ros-base` nur 100–130. Kommt die
kleine Zahl, wurde versehentlich `ros-base` installiert — dann fehlen RViz2, rqt
und die Demo-Nodes aus Abschnitt 5. Nachinstallieren mit
`sudo apt install ros-jazzy-desktop`.

Dann die Entwicklungswerkzeuge. `ros-dev-tools` bringt `colcon`, `rosdep` und
`vcstool` in einem Rutsch mit — die sind **nicht** Teil von `ros-jazzy-desktop`:

```bash
sudo apt install ros-dev-tools
```

Und die Pakete, die wir in dieser Phase noch brauchen:

```bash
sudo apt install -y \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox \
  ros-jazzy-teleop-twist-keyboard \
  ros-jazzy-tf2-tools \
  ros-jazzy-xacro \
  ros-jazzy-robot-state-publisher \
  python3-serial
```

`rosdep` einmalig initialisieren:

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

`ROS_DOMAIN_ID` trennt dein Netz von fremden ROS2-Systemen. **Die Zahl muss später
auf dem Pi identisch sein**, sonst sehen sich die Nodes nicht. 42 ist frei gewählt,
gültig ist 0–101.

---

## 5. Funktionsprobe

Bevor irgendwas mit Hardware passiert — zwei Terminals:

```bash
# Terminal 1
ros2 run demo_nodes_cpp talker

# Terminal 2
ros2 run demo_nodes_py listener
```

Der Listener muss die Zählnachrichten des Talkers ausgeben. Läuft das nicht, ist
die Installation kaputt und alles Weitere ist Zeitverschwendung.

> **`Package 'demo_nodes_cpp' not found`**, obwohl `ros2` selbst funktioniert?
> Dann ist ROS installiert, aber nicht die Desktop-Variante. Siehe die Kontrolle
> in Abschnitt 4 — Abhilfe:
> `sudo apt install -y ros-jazzy-demo-nodes-cpp ros-jazzy-demo-nodes-py`
> (oder gleich `ros-jazzy-desktop`). Danach ein **neues** Terminal öffnen.

Noch zwei nützliche Kommandos zum Ausprobieren:

```bash
ros2 topic list
ros2 topic echo /chatter
ros2 node list
```

RViz2 einmal starten, um zu sehen, ob die Grafik in der VM mitspielt:

```bash
rviz2
```

Falls es abstürzt oder schwarz bleibt: Boxes hat keine echte 3D-Beschleunigung,
RViz2 rendert dann über llvmpipe in Software. Erzwingen mit:

```bash
export LIBGL_ALWAYS_SOFTWARE=1
rviz2
```

Träge, aber benutzbar.

---

## 6. Workspace anlegen und LIDAR-Treiber bauen

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/ldrobotSensorTeam/ldlidar_stl_ros2.git

cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
```

### Nötiger Patch: fehlendes `#include <pthread.h>`

**Vor** dem ersten Build. Der Treiber ruft `pthread_mutex_init()` und Verwandte auf,
ohne `<pthread.h>` einzubinden. Auf älteren Toolchains kam der Header transitiv
über andere Includes mit, auf Ubuntu 24.04 mit GCC 13/14 nicht mehr — der Build
scheitert sonst mit `'pthread_mutex_init' was not declared in this scope`.

```bash
cd ~/ros2_ws/src/ldlidar_stl_ros2

for f in $(grep -rl 'pthread_mutex_' --include='*.h' --include='*.cpp' .); do
  grep -q '#include <pthread.h>' "$f" || sed -i '1i #include <pthread.h>' "$f"
  echo "gepatcht: $f"
done
```

Idempotent — mehrfaches Ausführen schadet nicht. **Der Patch wird auf dem Pi noch
einmal gebraucht**, weil dort frisch geklont wird.

Sollten weitere Fehler derselben Bauart auftauchen (`'uint8_t' was not declared`
→ `<cstdint>`, `'memcpy' was not declared` → `<cstring>`), ist es dasselbe Muster:
den passenden Header oben in die betroffene Datei einfügen.

### Bauen

```bash
cd ~/ros2_ws
colcon build --symlink-install
```

Der erste Build dauert in der VM ein paar Minuten. Danach:

```bash
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

> **Reihenfolge merken:** immer erst `/opt/ros/jazzy/setup.bash`, dann der
> Workspace. Genau so stehen die beiden Zeilen jetzt in der `.bashrc`.

Beim Bauen wirst du Warnungen sehen (`SetuptoolsDeprecationWarning` o.ä.) — die
sind normal. Nur `Failed` oder `Aborted` sind ein Problem.

---

## 7. Serielle Rechte und LIDAR-Test

Damit du ohne `sudo` an den Port kommst:

```bash
sudo usermod -aG dialout $USER
```

**Danach ab- und wieder anmelden** (oder die VM neu starten) — sonst greift die
Gruppenmitgliedschaft nicht. Prüfen mit `groups`, da muss `dialout` auftauchen.

> Das README des LIDAR-Treibers empfiehlt `sudo chmod 777 /dev/ttyUSB0`. Nicht
> machen — das ist nach jedem Neustecken weg und gibt jedem Prozess Vollzugriff.
> Die `dialout`-Gruppe ist der saubere Weg.

LIDAR anschließen (in Boxes durchreichen, siehe Abschnitt 1) und prüfen:

```bash
ls -l /dev/ttyUSB*
```

Dann starten:

```bash
ros2 launch ldlidar_stl_ros2 ld19.launch.py
```

`ld19` ist das richtige Profil — das STL-19P ist die Modellbezeichnung der
LD19-Baureihe. Der Launch nutzt per Default `/dev/ttyUSB0` bei **230400 Baud**,
publiziert auf dem Topic `scan` mit `frame_id: base_laser`.

In einem zweiten Terminal kontrollieren:

```bash
ros2 topic hz /scan          # ~10 Hz erwartet
ros2 topic echo /scan --once # einmal die Rohdaten ansehen
```

Und die Sichtprüfung — der Treiber bringt einen fertigen RViz2-Launch mit:

```bash
ros2 launch ldlidar_stl_ros2 viewer_ld19.launch.py
```

Falls du RViz2 von Hand startest: **Fixed Frame** auf `base_laser` stellen und
eine `LaserScan`-Anzeige auf dem Topic `/scan` hinzufügen, sonst siehst du nichts.

---

## 8. Was du bei diesem Test notieren sollst

Das hier brauchen wir in Phase 2c fürs URDF, also gleich mitschreiben:

1. **Wandabstände gegen den Zollstock gegenprüfen** — LIDAR auf den Tisch, ein
   bis zwei bekannte Abstände messen und mit RViz2 vergleichen. Wenn das um 10 %
   danebenliegt, stimmt was nicht.
2. **Drehrichtung**: dreht das Gerät im oder gegen den Uhrzeigersinn?
   (Parameter `laser_scan_dir`, Default `True` = gegen den Uhrzeigersinn.)
3. **Wo liegt der Nullwinkel** am Gehäuse? Gegenstand an eine definierte Stelle
   legen und schauen, wo er in RViz2 auftaucht. Davon hängt ab, wie das LIDAR
   später im URDF gedreht eingehängt wird.
4. **VID:PID des USB-Adapters** für die spätere udev-Regel:

```bash
lsusb
udevadm info -a -n /dev/ttyUSB0 | grep -E 'idVendor|idProduct|serial' | head
```

Trag die Ergebnisse in `DOCUMENTATION.md` ein.

---

## 9. Später: feste Gerätenamen und der Pi

### udev-Regel (wird nötig, sobald zwei Serial-Geräte dranhängen)

Am Roboter hängen LIDAR **und** Motorboard am Pi. Dann sind `/dev/ttyUSB0` und
`/dev/ttyUSB1` nicht mehr verlässlich — die tauschen beim Booten die Plätze.
Datei `/etc/udev/rules.d/99-omnibot.rules` anlegen; für unser STL-19P gemessen:

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", ATTRS{serial}=="0001", SYMLINK+="ttyLIDAR"
```

Aktivieren:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/ttyLIDAR
```

> **Achtung, Kollisionsgefahr:** `10c4:ea60` ist ein Silicon-Labs-CP2102, und der
> RoboESP32 benutzt sehr wahrscheinlich denselben Chip. `serial == 0001` ist
> zudem generisch. Wenn beide Geräte dieselbe Kennung melden, hilft weder VID:PID
> noch Seriennummer — dann muss über den **physischen USB-Port** gebunden werden:
>
> ```bash
> udevadm info -a -n /dev/ttyUSB0 | grep -m2 KERNELS
> ```
>
> und die Regel mit `KERNELS=="1-1.2"` (o.ä.) statt `ATTRS{serial}` schreiben.
> Funktioniert zuverlässig, solange immer derselbe Port benutzt wird.

Der `ld19.launch.py` des Treibers hat `/dev/ttyUSB0` fest verdrahtet. Für den
Dauerbetrieb bekommt der Roboter in Phase 2c einen eigenen Launch in
`omnibot_bringup`, der `/dev/ttyLIDAR` setzt. Für diesen ersten Test genügt der
mitgelieferte Launch.

### Auf dem Raspberry Pi

Gleicher Ablauf wie oben, mit drei Unterschieden:

- **Ubuntu Server 24.04 LTS arm64** statt Desktop
- `ros-jazzy-ros-base` statt `ros-jazzy-desktop` (RViz2 läuft in der VM, nicht auf
  dem Pi)
- Abschnitte 1 und 5 (VM, RViz2) entfallen

### Netzwerk zwischen VM und Pi

Boxes hängt die VM standardmäßig hinter NAT. **Die DDS-Discovery von ROS2 kommt da
nicht durch** — du siehst dann vom Pi aus keine Topics und umgekehrt. Wenn es so
weit ist, muss die VM auf Bridged Networking umgestellt werden (`virt-manager`,
Netzwerkquelle → Bridge oder macvtap).

Erkennungsmerkmal: `ros2 topic list` zeigt lokal alles, aber über die Maschinen
hinweg nichts. Das ist dann kein ROS-Problem, sondern das Netzwerk.

---

## Stolperfallen in Kurzform

| Symptom | Ursache |
| :--- | :--- |
| `ros2: command not found` | `source /opt/ros/jazzy/setup.bash` fehlt |
| `Package '...' not found`, aber `ros2` läuft | `ros-base` statt `ros-jazzy-desktop` installiert |
| `AMENT_PREFIX_PATH` ist leer | gar nichts gesourct — `.bashrc`-Zeile prüfen |
| `Permission denied: /dev/ttyUSB0` | nicht in Gruppe `dialout`, oder nach `usermod` nicht neu angemeldet |
| `/dev/ttyUSB*` existiert nicht | USB in Boxes nicht (mehr) durchgereicht |
| `/scan` bleibt leer | falscher Port oder falsche Baudrate (muss 230400 sein) |
| RViz2 zeigt nichts | Fixed Frame nicht auf `base_laser` gesetzt |
| RViz2 stürzt ab | keine 3D-Beschleunigung → `LIBGL_ALWAYS_SOFTWARE=1` |
| Nodes finden sich nicht | unterschiedliche `ROS_DOMAIN_ID`, oder NAT statt Bridge |
| `ROS_APT_SOURCE_VERSION` leer | GitHub-API-Rate-Limit, Version manuell eintragen |
| `'pthread_mutex_init' was not declared` | fehlendes `#include <pthread.h>` im Treiber, siehe Abschnitt 6 |
| `Open open error, Permission denied` | nicht in Gruppe `dialout` — `newgrp dialout` als Sofortlösung |
| `/dev/ttyUSB0` verschwindet nach Sekunden | `brltty` schnappt sich CP210x/CH340 → `sudo apt remove brltty` |
