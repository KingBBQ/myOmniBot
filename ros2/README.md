# ROS2-Pakete des Omnibot 5402

Drei Pakete, bewusst klein geschnitten:

| Paket | Aufgabe |
| :--- | :--- |
| `omnibot_base` | Bruecke zum Motorknoten: `/cmd_vel` rein, `/odom` und TF raus |
| `omnibot_description` | URDF/xacro, Masse aus `DOCUMENTATION.md` |
| `omnibot_bringup` | Startet alles zusammen, plus LIDAR |

Sie liegen hier im Repo und **nicht** in `~/ros2_ws/src`, damit sie versioniert
sind. In den Workspace kommen sie per Symlink - colcon findet Pakete rekursiv,
ein Link auf das ganze Verzeichnis reicht:

Auf dem Pi liegt der Klon in `~/myOmniBot`, auf dem Entwicklungsrechner in
`~/src/myOmniBot` - der Link muss aufs richtige Ziel zeigen, ein toter Link
wird von colcon kommentarlos uebergangen:

```bash
ln -s ~/myOmniBot/ros2 ~/ros2_ws/src/omnibot
cd ~/ros2_ws
colcon build --symlink-install --packages-select \
    omnibot_base omnibot_description omnibot_bringup
source install/setup.bash
```

Auf dem Pi 5 ohne Swap-Not baut das in unter einer Minute; `--parallel-workers 2`
braucht es hier nicht, die Pakete sind winzig.

## Starten

```bash
ros2 launch omnibot_bringup bringup.launch.py
```

Danach steht der TF-Baum `odom -> base_footprint -> base_link -> base_laser`,
`/scan` kommt mit 10 Hz und der Roboter faehrt auf `/cmd_vel`.

Nuetzliche Argumente:

```bash
# ohne LIDAR, nur Fahrbetrieb pruefen
ros2 launch omnibot_bringup bringup.launch.py use_lidar:=false

# USB-TTL-Adapter statt GPIO-UART (Schreibtischtest ohne Pi-Verkabelung)
ros2 launch omnibot_bringup bringup.launch.py motor_port:=/dev/ttyUSB0
```

Von Hand fahren:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard \
    --ros-args -p speed:=0.15 -p turn:=1.0
```

Die Grenzen sind mit Absicht so gesetzt: gemessen sind 0,212 m/s und 2,48 rad/s.

## Was der Motorknoten macht - und was nicht

Er rechnet `cmd_vel` ueber die gemessene Kennlinie in Promille Tastverhaeltnis
um und schickt das mit 20 Hz ans Board. Die Odometrie entsteht **aus der
Telemetrie**, also aus dem Tastverhaeltnis, das das Board tatsaechlich anlegt -
nicht aus dem Sollwert. So schlagen Totband und Totmannschaltung korrekt durch.

Was er nicht macht: regeln. Es gibt keine Encoder, die Odometrie ist reine
Koppelnavigation und driftet. Die Kovarianzen sind deshalb bewusst pessimistisch
gesetzt, damit SLAM dem LIDAR mehr glaubt als dem Rechenweg. Fuer eine Karte
braucht es zusaetzlich `rf2o` auf `/scan`.

Zwei Dinge, die man beim Debuggen wissen muss:

- **Handbetrieb.** Druecken auf Start/Stop an der Fernbedienung uebergibt ihr die
  Kontrolle, `/cmd_vel` wird dann verworfen. Der Knoten meldet das als Warnung
  und auf `~/manual_mode`. Zurueck geht es nur ueber dieselbe Taste.
- **Stiller Boardhaenger.** Bleibt die Telemetrie laenger als `telemetry_timeout`
  aus, meldet der Knoten einen Fehler. Das ist der offene Bug aus `TODO.md` -
  dann hilft nur ein Reset am ESP32.

## Kalibrierung nachziehen

Alle gemessenen Zahlen stehen an genau einer Stelle:
`omnibot_base/omnibot_base/kinematics.py`. Die Tests in
`omnibot_base/test/test_kinematics.py` pruefen die Kennlinie gegen die
tatsaechlich gefahrenen Messwerte - wer an den Konstanten dreht, sieht dort
sofort, ob das Modell noch zum Roboter passt.

```bash
cd ~/ros2_ws && colcon test --packages-select omnibot_base
colcon test-result --verbose
```
