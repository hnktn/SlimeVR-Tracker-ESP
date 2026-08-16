# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development

Build tooling is **PlatformIO** (Arduino framework). The default environment is `BOARD_WEMOSD1MINI` (see `platformio.ini`).

```bash
# Build the default environment
pio run

# Build a specific board environment (env names match `[env:...]` in platformio.ini)
pio run -e BOARD_SLIMEVR_V1_2
pio run -e BOARD_CHEESECAKE_BLUEBERRY

# Upload firmware to the connected board
pio run -e BOARD_WEMOSD1MINI -t upload

# Open serial monitor (115200 baud, configured in platformio.ini)
pio device monitor

# Build every env declared in platformio.ini (what CI runs); writes binaries to ./build/
python ./ci/build.py

# Override board defaults at build time (JSON inlined into preprocessor.py)
SLIMEVR_OVERRIDE_DEFAULTS='{"SENSORS":[...],"BATTERY":{...},"LED":{...}}' pio run -e BOARD_WEMOSD1MINI
```

A Nix dev shell is provided (`flake.nix`) that bundles PlatformIO + Python + jsonschema; `nix develop` enters it. There is no `pio test` suite — `test/` only contains a manual `i2cscan.cpp` helper.

### Formatting

`clang-format` (version 17, config in `.clang-format`, indent = tabs/4, column = 88) is enforced in CI. Run before committing:

```bash
clang-format -i $(git ls-files 'src/*.cpp' 'src/*.h')
```

## Architecture

Firmware that turns ESP8266/ESP32 boards into IMU-based body trackers, talking to the SlimeVR Server over Wi-Fi.

### Boot flow ([src/main.cpp](src/main.cpp))

`setup()` wires up global singletons in this order: `ledManager` → `configuration` (loads from flash) → `SerialCommands` → `I2CSCAN::clearBus` (recovers stuck I2C) → `Wire.begin` → `sensorManager.setup()` (probes/instantiates IMUs) → `networkManager.setup()` (Wi-Fi + UDP/TCP to server) → `OTA::otaSetup` → `battery.Setup` → `sensorManager.postSetup()`.

`loop()` is a tight cooperative loop: SerialCommands → OTA → networkManager.update → sensorManager.update → battery.Loop → ledManager.update → optional fixed-rate sleep via `TARGET_LOOPTIME_MICROS`.

### Two-layer configuration (this is the part that bites)

Per-board pinouts and IMU settings come from **two** sources that must agree:

1. **`board-defaults.json`** — declarative per-board values (sensors, battery divider, LED pin). [`scripts/preprocessor.py`](scripts/preprocessor.py) is run as a `pre:` script by PlatformIO, validates this file against `board-defaults.schema.json`, and emits `-D` build flags (including a `SENSOR_DESC_LIST` macro that drives `SensorBuilder`). A board entry is selected via the `custom_slime_board = BOARD_xxx` option in `platformio.ini`.

2. **`src/defines.h` + [src/boards/boards_default.h](src/boards/boards_default.h)** — fallback `#define`s gated by `#ifndef`. Anything **not** emitted by the preprocessor (e.g. `PIN_IMU_SDA`, `BATTERY_SHIELD_*`, `MAX_SENSORS_COUNT`, `IMU_ROTATION` for code paths that read the macro directly) must be defined here. The preprocessor does **not** replace every macro — it only emits what's listed in `_build_board_flags`.

When adding a new board: add an `[env:BOARD_FOO]` block to `platformio.ini`, a matching entry in `board-defaults.json`, and a `BOARD == BOARD_FOO` branch in `boards_default.h` for any pins/resistors/`MAX_SENSORS_COUNT` not handled by the preprocessor.

### Sensor stack (`src/sensors/`)

- `SensorManager` owns a `vector<unique_ptr<Sensor>>`; `SensorBuilder` constructs each entry from the `SENSOR_DESC_LIST` macro emitted by the preprocessor.
- Each IMU family has its own driver: legacy DMP-based ones (`bno080sensor`, `bno055sensor`, `mpu6050sensor`, `mpu9250sensor`, `icm20948sensor`) live directly under `sensors/`, while modern gyro+accel IMUs (BMI270, ICM-42688, ICM-45686, LSM6DSV/DSO/DSR/DS3TRC, MPU-6050 SF) all funnel through the `softfusion/` framework, which pairs a register-level driver from `softfusion/drivers/` with `SoftFusionSensor` + `SensorFusion` (VQF-based) + `RuntimeCalibration` for online gyro/accel calibration.
- `SensorFusion` / `SensorFusionDMP` are the two fusion entry points; `motionprocessing/` provides VQF, rest detection, and gyro-temperature polynomial calibration.
- Hardware access is abstracted by `sensorinterface/`: I²C (Wire, PCA9547 mux), SPI, and pin expanders (MCP23X17). Drivers receive a `RegisterInterface` and don't talk to `Wire`/`SPI` directly.

### Network (`src/network/`)

`Manager` runs a UDP-based custom protocol with the SlimeVR Server (`packets.h`, `connection.cpp`). `wifiprovisioning.cpp` handles SmartConfig/serial-provisioned credentials. Feature bits live in `featureflags.h` and are negotiated with the server.

### Other modules

- `src/configuration/` — persists calibration + sensor config to LittleFS via `FSHelper`.
- `src/serial/serialcommands.cpp` — interactive console (`SET WIFI`, `GET INFO`, `REBOOT`, calibration triggers, etc.). Reads several `defines.h` macros directly, so new board configs must define them even if `board-defaults.json` would seem to cover them.
- `src/status/` — LED patterns + `StatusManager` enum used across the codebase to surface boot/error state.
- `lib/` — vendored third-party drivers (BNO080, BMI160, ICM20948, MPU6050/9250, VQF, magneto, i2cscan). Per `CONTRIBUTING.md`, new dependencies should go through `lib_deps` in `platformio.ini`, not be copied into `lib/`.
