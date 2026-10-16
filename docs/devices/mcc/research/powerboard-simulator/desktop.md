> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Native MCC Digital Twin desktop

MCC Digital Twin is the interactive component of **MCC Developer Toolkit**. The default entry point creates a native Tkinter/ttk window and a persistent synthetic board model in one Python process:

```console
python -m mcc_digital_twin
```

Use `python3` if that names Python 3.11+ on your system. No browser, HTTP service, TCP listener or serial driver is needed for the desktop. This source release contains no EXE, installer or PyInstaller bundle. The [cross-platform quick start](crossplatform-quickstart.md) explains interpreter/Tk requirements for Windows, Linux and macOS.

## Interactive workflow

1. Select a speed, direction and temperature level; start a synthetic command. Requested and measured RPM remain separate.
2. Observe finite acceleration, blade direction, measured RPM and temperature. The animation's visual speed is capped for readability; it is not a physical measurement.
3. Request STOP. The target changes immediately while measured RPM falls according to the configured synthetic deceleration.
4. Pause the virtual clock and use Step for a chosen number of milliseconds. Resume the clock for continuous preview.
5. Inject weight, lid or board-error state and response delay/loss/corruption; inspect decoded state, raw HEX and the event timeline.
6. Save a local recording, load a supported recording or run replay verification. Create a new session for a fresh model.

Physics forms configure acceleration, active/coasting deceleration, heating/cooling, ambient temperature and illustrative level-to-RPM points. Every default is a modeling choice. Lid/error fields do not claim to emulate hardware interlocks. See [fidelity](fidelity.md).

The scenario selector runs a separate deterministic experiment. Its result does not secretly replace the current interactive model. A new interactive session retains the selected physics and paused/running preference, but begins fresh synthetic state.

## Headless and reusable controller

```console
python -m mcc_digital_twin --headless
python -m mcc_digital_twin scenario intermittent --json
python -m mcc_digital_twin stress --count 1000 --seed 292 --json
```

Headless operations do not import Tkinter or require a display. `DesktopController` in `mcc_powerboard_simulator.desktop_controller` can be tested without creating a window. It owns a `RecordingSession` and exposes `start`, `stop`, `feed`, `feed_hex`, `advance`, `poll`, `set_running`, `set_sensors`, `set_faults`, `configure`, `new_session`, `save_session`, `load_session`, `replay_session`, `run_scenario` and `state`. The actual GUI loads Tk only when a window is created.

The desktop's automatic clock uses elapsed monotonic time in the same process. It does not establish embedded real-time scheduling. Recordings preserve supported model actions and expected responses/checkpoints; replay compares them against a fresh synthetic model.

## Optional integrations

The **Android Connection** tab can explicitly enable a raw loopback listener in this same process and share this window's existing model. It is disabled at normal startup. One remote client owns motor commands while GUI telemetry/fault injection stays available; desktop STOP disconnects it. Disconnect requests synthetic finite STOP and clears transport state. See [integrated connection](../android-connection.md) for ownership, limits and emulator setup.

Legacy headless TCP, the in-memory adapter and serial-like/PTY interfaces remain optional APIs with their documented compatibility behavior. See [API](api.md), [virtual serial](virtual-serial.md) and [scenarios](scenarios.md).

The Digital Twin is one component alongside decoder, packet builder, log analyzer, inspector, telemetry and test/replay workflows. Use [developer tools](../developer-tools.md) when you need a local-file tool without the GUI. No interface opens a physical appliance connection or redirects an original MCLauncher APK automatically.
