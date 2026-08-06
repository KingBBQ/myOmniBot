# Project Documentation: Omnibot 5402 Revival

## 1. Overview
This project focuses on the modernization of a Tomy Omnibot 5402 robot, replacing its original cassette-tape based control system with a modern microcontroller for wireless remote operation.

## 2. Hardware Specifications
### Robot: Tomy Omnibot 5402
- **Power:** 6V Lead Gel Cell battery (Recently replaced/renewed).
- **Motors:** Two DC motors for movement and steering.
- **Special Features:** Gripper, eye lights, built-in loudspeaker, and a legacy segment LCD display.

### Controller: Cytron RoboESP32
- **MCU:** ESP32 (Xtensa Dual Core), flashed with CircuitPython 10.2.1.
- **Motor Driver:** Integrated driver supporting up to 1A continuous / 1.5A peak per channel.
- **Connectivity:** Wi-Fi and Bluetooth.

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
- `serial == 0001` is generic, and the RoboESP32 likely uses the same CP2102
  (`10c4:ea60`). If both devices are attached at once, the udev rule must bind by
  physical USB port (`KERNELS==...`) instead of VID:PID/serial.

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

LIDAR mounting: on top of the head dome, scan plane **0.40 m above the floor**.
In the URDF that is `base_laser` z = 0.40 - 0.0375 = **0.3625 m** above
`base_link`.

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

### Still to be measured (needed for URDF and kinematics)
- [ ] **Zero-angle orientation of the LIDAR housing** — determines the yaw of
      `base_laser`. Get it from the bench test: put an object in a known
      direction and see where it shows up in RViz2. Note the stock
      `ld19.launch.py` publishes a placeholder TF at z = 0.18 m; that gets
      replaced by our URDF.
- [ ] Tooth count of the final drive gear (encoder resolution, see phase 3)

### To confirm
- [ ] **Is the head dome rigid relative to the body?** The LIDAR mounts on top
      of it. If the head can rotate, `base_laser` moves relative to `base_link`
      and the whole TF tree becomes wrong. A rotating head would have to be
      fixed in place, or fitted with an encoder — avoid the latter.
- [ ] "Front" = the caster end. The geometry above assumes the edge that is
      160 mm from the LIDAR is the robot's front, i.e. it drives caster-first
      and the driven wheels trail. If it is the other way round, x flips sign.

### Wiring Map (Planned/Implemented)
| component | Pin A | Pin B | Note |
| :--- | :--- | :--- | :--- |
| Motor 1 | D12 | D13 | Left/Right Drive |
| Motor 2 | D14 | D27 | Left/Right Drive |
| Power | Vin | GND | 6V DC from Blei-Zelle |

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
