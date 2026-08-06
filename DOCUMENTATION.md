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
