# Project Documentation: Omnibot 5402 Revival

## 1. Overview
This project focuses on the modernization of a Tomy Omnibot 5402 robot, replacing its original cassette-tape based control system with a modern microcontroller for wireless remote operation.

## 2. Hardware Specifications
### Robot: Tomy Omnibot 5402
- **Power:** 6V Lead Gel Cell battery (Recently replaced/renewed).
- **Motors:** Two DC motors for movement and steering.
- **Special Features:** Gripper, eye lights, built-in loudspeaker, and a legacy segment LCD display.

### Controller: Cytron RoboESP32
- **MCU:** ESP32 (Xtensa Dual Core), flashed with CircuitPython 10.2.1
  (board ID `ESP32 Devkit V1 with ESP32`, station MAC `8c:94:df:b9:9c:5c` —
  this is the ESP-NOW peer the handset talks to).
- **Motor Driver:** Integrated driver supporting up to 1A continuous / 1.5A peak per channel.
- **Connectivity:** Wi-Fi and Bluetooth.
- **USB bridge:** CH340 (`1a86:7523`), exposed as `/dev/ttyUSB*`. This is the
  CircuitPython **REPL** on UART0 — uploads and tracebacks only. The motor
  protocol runs on **UART2 / Grove port 1** (GPIO17 = TX2, GPIO16 = RX2), which
  is wired to the Raspberry Pi's GPIO UART, not through USB.
- **Power path:** USB and VIN are diode-OR'd, and V<sub>motor</sub> follows the
  higher source (datasheet rows 5-8). With the 6 V lead gel cell below ~5.6 V the
  motors start drawing from whatever USB host is attached — do not leave a
  powered USB cable connected during battery runs, or use a cable with VBUS cut.

### LIDAR: LDROBOT STL-19P (LD19 series)
Verified 2026-08-06 on the Ubuntu 24.04 VM with `ldlidar_stl_ros2`, driver SDK v3.0.3.

| Property | Measured value | Source |
| :--- | :--- | :--- |
| Interface | USB-UART, 230400 baud 8N1 | driver reports "Actual BaudRate reported: 230400" |
| USB chip | Silicon Labs CP2102, `10c4:ea60`, `serial == 0001` | `udevadm info` |
| Scan rate | 10.0 Hz (`scan_time` 0.09999 s) | `/scan` |
| Points per revolution | 504 (`angle_increment` 0.012467 rad = 0.714 deg) | `/scan` |
| Point rate | 5040 points/s (`time_increment` 0.0001984 s) | `/scan` |
| Angle range | 0 .. 2*pi (0-360 deg, not -180..+180) | `/scan` |
| Range | `range_min` 0.02 m, `range_max` 25.0 m | `/scan` |
| Rotation direction | Counterclockwise (driver default `laser_scan_dir`) | launch output |
| Topic / frame | `scan` / `base_laser` | driver default |

Notes:
- The 25 m `range_max` is what the driver advertises, not a usable sensing range.
  Cap this to a realistic value in the Nav2 costmap config, otherwise far-field
  noise ends up in the map.
- The stock `ld19.launch.py` publishes a **placeholder** static TF
  `base_link -> base_laser` at z = 0.18 m. This gets replaced by the real URDF
  in phase 2c.
- `serial == 0001` is generic, so the serial number is useless for matching. The
  RoboESP32 turned out to use a **CH340 (`1a86:7523`)**, not a CP2102 (verified
  2026-08-15 with `udevadm info -q property`), so VID:PID *does* separate the two
  devices and a `KERNELS==...` rule is only needed once a second CP2102 or a
  second CH340 is attached:

  ```
  SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="ttyLIDAR"
  SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="ttyREPL"
  ```

  CH340 is also exactly the chip `brltty` claims as a braille display, so
  removing `brltty` is mandatory, not precautionary.

### Chassis and drivetrain geometry
Measured 2026-08-06, see `pics/räder-unten.jpg` and `pics/getriebe.jpg`.

| Property | Value | Note |
| :--- | :--- | :--- |
| Wheel diameter | 75 mm | radius 37.5 mm |
| Wheel circumference | 235.6 mm | pi * 75 mm |
| Wheel width | 30 mm | |
| Track width (geometric) | 170 mm | wheel centre to wheel centre |
| Wheelbase | 85 mm | front to rear axle, same side |
| Chassis base plate | 290 mm long x 250 mm wide | |
| Front axle position | 160 mm from the front edge | LIDAR sits directly above it |
| Rear axle position | 245 mm from the front edge | = 45 mm from the rear edge |
| Wheel revolutions per 360 deg robot turn | 2.27 | geometric, ignores scrub |
| `base_link` height above `base_footprint` | 37.5 mm | = wheel radius |

The wheelbase-to-track ratio is 0.5, which is short. Scrub during in-place
rotation is therefore mild — expect the effective wheel separation correction to
be a few percent, not the tens of percent that long-wheelbase skid-steer
platforms need.

### Frame origin and costmap footprint
`base_link` sits on the centreline at the **midpoint between the two axles**,
at wheel-axle height — that is the point the robot actually rotates about.

    origin = (160 + 245) / 2 = 202.5 mm from the front edge

Everything below is relative to that origin, x forward, y left (ROS REP-103):

| Reference | x | y |
| :--- | ---: | ---: |
| Front edge of base plate | +0.2025 m | — |
| Rear edge of base plate | -0.0875 m | — |
| Left / right edge | — | +/-0.125 m |
| LIDAR (`base_laser`) | **+0.0425 m** | 0.0 m |

LIDAR mounting: on top of the head dome, scan plane **0.40 m above the floor**,
housing upright and **not rotated — yaw = 0**, its zero angle pointing forward
along +x. In the URDF that is `base_laser` at z = 0.40 - 0.0375 = **0.3625 m**
above `base_link`, rpy 0 0 0.

The head dome is **rigid** relative to the body, so `base_laser` is a genuine
static transform.

Confirmed layout: **both driven axles are at the rear, the swivel caster is at
the front.** The robot therefore drives caster-first. Two consequences:
- It rotates about a point 202.5 mm behind the front edge, so the head and
  front tray sweep a wide arc — watch rotation clearance in tight spots.
- A *leading* caster is less directionally stable than a trailing one. Expect a
  slight veer at the start of a forward run while the caster swings around.
  During the duty-to-speed calibration, let the caster settle before measuring
  and run each step twice.

Consequences of that height, relevant for Nav2 tuning:
- Nothing below 0.40 m is visible — thresholds, cables, shoes, toys. The robot
  will drive into them. Normal for a 2D LIDAR, but it limits where autonomous
  driving is safe.
- It looks *under* tables and only sees the legs. Good for path planning,
  bad for not hitting the tabletop with the dome.

Nav2 costmap footprint polygon:

    [[0.2025, 0.125], [0.2025, -0.125], [-0.0875, -0.125], [-0.0875, 0.125]]

Use the polygon, not a circle. The origin is far off-centre, so a circular
footprint would need a 0.238 m radius — about 5 cm of pointless inflation
compared with the 0.191 m a chassis-centred circle would need.

Note the robot rotates about a point well towards the rear. The front corners
sweep a much larger arc than the rear ones, which matters for rotation clearance
in tight spots.

**Drivetrain layout: skid steer, not a simple two-wheel differential drive.**
Four wheels in tandem pairs (two per side, front and rear), plus a swivel caster
with twin rollers in the centre. Both wheels of a side are coupled through the
gearbox, so there is one degree of freedom per side — a differential drive model
still applies, but with an important caveat:

> During in-place rotation the front and rear wheel of one side run on different
> radii and are dragged sideways across the floor. The **geometric track width of
> 170 mm is therefore the wrong value for the odometry model** — it will
> over-report rotation. The effective wheel separation is typically 10-50 % larger
> and depends on wheelbase and floor surface (carpet differs from tile).
> It cannot be measured, only calibrated: rotate the robot ten full turns in
> place and tune the parameter until reported and actual rotation agree.
> Straight-line driving is unaffected. See phase 2d.

### Open items
- [ ] Verify the LIDAR yaw once mounted: a flat wall straight ahead must appear
      straight ahead in RViz2. The assumed yaw is 0, but a housing mounted a few
      degrees off skews every map.
- [ ] Which shaft carries the encoder disc — must be clean and outside the
      gearbox grease (see below)

### Planned: wheel encoders (phase 3)

Sensor: **H2010** slotted opto-interrupter module with an LM393 comparator on
board. Gap 10 mm, aperture 1 mm. One per side.

**Not the gearbox teeth.** The original plan was to chop the beam with the final
drive gear. With a 1 mm aperture the smallest feature the sensor resolves
cleanly is 2 mm, so bar and gap each need 2 mm — a 4 mm pitch. Gear tooth
thickness at the pitch circle is roughly `1.57 * module`, so the module 0.5-0.8
gears a toy gearbox uses give 0.8-1.3 mm features. That is at or below the
aperture width: no clean square wave, and a miscount that varies with speed.
Module 1.3 or coarser would be required and does not exist in this drivetrain.
The tooth count is therefore no longer needed.

Instead: a printed encoder disc on a clean shaft. Maximum slot count for a disc
of radius r, keeping every feature at twice the aperture:

    N <= pi * r / 2 mm

| Disc radius | max slots | counts per wheel rev | resolution |
| ---: | ---: | ---: | ---: |
| 15 mm | 23 | 23 | 10.2 mm |
| 20 mm | 31 | 30 | 7.9 mm |
| 25 mm | 39 | 39 | 6.0 mm |

Chosen: **r = 20 mm, 30 slots** — 7.9 mm per count over the 235.6 mm wheel
circumference. Resolution is not the limiting error here, skid-steer slip is, so
margin to the 2 mm limit is worth more than a higher count.

Build notes:
- Power the module from **3.3 V**. The ESP32 is not 5 V tolerant.
- The LM393 supplies the hard edge with hysteresis that `countio.Counter` needs.
  A bare phototransistor output has soft transitions and gets counted several
  times per slot by the hardware pulse counter.
- Mount **outside the gearbox grease**. A fouled disc does not fail outright, it
  makes the odometry drift slowly — the worse kind of fault.
- Black filament is not automatically opaque at 940 nm. Print a test strip and
  confirm the module LED switches before designing the mount.
- **No direction information** from one interrupter per side. Direction comes
  from the commanded setpoint, which is wrong if the robot is pushed or rolls
  back on a slope. Quadrature would need two sensors a quarter pitch (1 mm)
  apart — impossible with 10 mm wide housings.

Alternatives checked, none better: TCST2103 has the same 1 mm aperture with a
narrower 3.1 mm gap; GP1A57HRJ00F is worse at a 1.8 mm slit, though it does
carry an OPIC digital output and would not need the LM393.

### Planned: low obstacle detection
The LIDAR cannot go lower than 0.40 m, so obstacles below that are invisible.
The plan is to add IR distance or sonar sensors low at the front later.

Integration path when that happens: publish them as `sensor_msgs/Range` and
feed them into the Nav2 costmap through the **`nav2_costmap_2d` range sensor
layer**, which is built for exactly this. They do not belong in the `/scan`
topic — mixing sensors of different geometry into one LaserScan breaks SLAM.
The serial protocol has room for extra telemetry fields if the sensors end up on
the motor board rather than on the Pi.

### Remote control: original Omnibot handset on a LOLIN S2 Mini
The original handset's buttons were rewired to a LOLIN S2 Mini (ESP32-S2FN4R2,
CircuitPython 10.2.1, board ID `lolin_s2_mini`, station MAC `cc:8d:a2:91:35:c2`).
All buttons switch to GND, inputs use the internal pull-up.

| Button | GPIO | Silkscreen | Sends |
| :--- | :--- | :--- | :--- |
| Forward | 16 | D4 | part of `V` |
| Backward | 18 | D3 | part of `V` |
| Left | 17 | — | part of `V` |
| Right | 21 | — | part of `V` |
| Start/Stop | 39 | — | `M` (toggle manual mode) |
| Omnibot Sound, upper | 38 | — | `A 1` (no effect yet) |
| Omnibot Sound, lower | 40 | — | `A 2` (no effect yet) |

GPIO39/40 are the ESP32-S2 JTAG lines MTCK/MTDO. Harmless as plain inputs as
long as no debugger is attached. GPIO19/20 are the native USB pins and must stay
free — claiming them kills both the REPL and the CIRCUITPY drive.

The link is **ESP-NOW broadcast**, carrying the same ASCII line protocol the
serial link uses, so the motor node needs no second command language. The robot
answers with `a <manual> <moving>` at 5 Hz, which drives the status LED on the
handset: solid = manual mode, short blink = link up but the companion computer
is driving, off = no link.

Two things that cost time to find out:
- `ESPNow.send(msg)` without an explicit peer fails with `ESP-NOW error 0x3069`
  (`ESP_ERR_ESPNOW_NOT_FOUND`) even with the broadcast peer registered. Pass the
  peer: `send(msg, peer)`. Verified on the board with CircuitPython 10.2.1.
- ESP-NOW shares the radio channel with WiFi. A board that joins an access point
  via `settings.toml` follows that AP's channel and stops hearing its peer.
  Both ends unassociated means both sit on channel 1.

Speeds are chosen around the motor node's `DEADBAND = 0.2`: straight ahead 0.6,
spin in place ±0.5, and 0.35 of steering while driving, which leaves the inner
wheel at 0.25 — just above the deadband, so it keeps turning instead of stalling.

### Wiring Map (Planned/Implemented)
| component | Pin A | Pin B | Note |
| :--- | :--- | :--- | :--- |
| Motor 1 | D12 | D13 | Left/Right Drive |
| Motor 2 | D14 | D27 | Left/Right Drive |
| Power | Vin | GND | 6V DC from Blei-Zelle |

### Control Panel (LOLIN S2 Mini)
The original Omnibot keypad runs on a separate LOLIN S2 Mini (ESP32-S2FNR2,
CircuitPython 10.2.1, board id `lolin_s2_mini`). Every button is a plain
switch to GND — the internal pull-ups do the rest, no external resistors.
Verified by durchklingeln on 2026-08-07 with `src/code_pinscan.py`.

| Button | Pin | Note |
| :--- | :--- | :--- |
| forward | IO16 | D4 |
| back | IO18 | D3 |
| left | IO17 | |
| right | IO21 | |
| start/stop | IO39 | |
| sound upper | IO38 | labelled "OmnibotSound" |
| sound lower | IO40 | labelled "OmnibotSound" |

Do not use **IO19/IO20** on this board — they carry the native USB lines that
serve the REPL and the CIRCUITPY drive. CircuitPython hides them from the
`board` module for that reason. **IO0** is the on-board BOOT button and
**IO15** drives the on-board LED; both work as inputs but are poor choices for
a panel button.

## 3. Software Stack
- **Firmware:** CircuitPython v10.2.1 (via `adafruit-circuitpython-doit_esp32_devkit_v1`).
- **Control Method:** HTTP Web Server hosted on the ESP32.
- **Communication:** Wi-Fi Station mode (connected to local WLAN).
- **Logic:** Simple digital output switching for motor direction control.

## 4. Progress & Milestones
- [x] **Hardware Identification:** Confirmed model as Omnibot 5402.
- [x] **Tooling Setup:** Installed `esptool` in a virtual environment.
- [x] **Firmware Installation:** Flashed CircuitPython 10.2.1 to the RoboESP32 via `/dev/ttyUSB0`.
- [x] **Network Configuration:** Configured `settings.toml` for automatic Wi-Fi connection.
- [x] **Initial Prototype:** Developed a web-based remote control interface (Forward, Backward, Left, Right, Stop).

## 5. Future Work & Open Issues
### Urgent/Short Term
- **Current Protection:** Install PPTC resettable fuses (1A - 1.2A) on motor channels to prevent driver burnout during stalls.
- **Testing:** Verify physical movement and calibrate directions in `code.py`.

### Medium Term
- **Remote Upgrade:** Transition from HTTP Web Server to **ESP-NOW** for lower latency and independent operation (no router needed).
- **Display Activation:** Research and attempt to drive the legacy LCD display.

## 6. Reference Files
- `TODO.md`: Current task list.
- `AGENTS.md`: Instructions for AI agents working on this repo.
- `firmware/`: Repository of used binary images.
- `specs/`: Technical datasheets (MD format).
