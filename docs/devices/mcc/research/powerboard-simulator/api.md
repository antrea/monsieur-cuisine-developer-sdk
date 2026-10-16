> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# MCC Digital Twin API

The component is also called **MCC PowerBoard Simulator** within MCC Developer Toolkit. It uses Python 3.11+ and the shared original `mcc_protocol` codec. `python -m mcc_digital_twin` opens the native Tkinter/ttk desktop without network listeners; `--headless` executes a JSON demonstration without importing Tk. Core model/scenario calls use memory and explicit virtual time. The GUI's optional **Android Connection** enables a loopback listener in the same process; the older headless server API remains available separately. There is no hardware transport or firmware emulator.

## Native desktop controller

The [desktop](desktop.md) uses `mcc_powerboard_simulator.desktop_controller.DesktopController(config=None)`, a headless-testable controller owning a `RecordingSession`. Its mutation methods include `start`, `stop`, `feed`, `feed_hex`, `advance`, `set_sensors`, `set_faults`, `configure` and `new_session`. `poll(elapsed_ms)` advances when running; `set_running(bool)` pauses/resumes. `save_session`, `load_session`, `replay_session`, `run_scenario` and `state` support local development workflows. Tk is imported only when constructing the actual window through `mcc_powerboard_simulator.desktop.launch()`; module import starts no GUI or server.

Optional serial-style and POSIX PTY APIs are documented separately in [virtual serial](virtual-serial.md). They are not started by the native desktop.

The [integrated Android Connection API](../android-connection.md#python-embedding-api) adds RX observers, source-level command ownership and `reset_transport()` without replacing existing local APIs. Remote ownership guards local command/session replacement; sensor/fault controls remain usable. The optional GUI bridge and legacy server have explicitly different disconnect policies.

## Persistent model and virtual time

```python
from mcc_protocol.codec import Direction, Operation, decode_frame, encode_tx
from mcc_powerboard_simulator.model import PhysicsConfig, PowerBoardModel

model = PowerBoardModel(PhysicsConfig(acceleration_rpm_s=4000.0))
initial_rx = model.feed(encode_tx(Operation.STANDARD, speed=3,
                                direction=Direction.COUNTER_CLOCKWISE))
assert decode_frame(initial_rx[0]).actual_rpm == 0
model.advance(100)
assert model.snapshot()["telemetry"]["actual_rpm"] == 400
model.feed(encode_tx(Operation.STOP))
assert model.snapshot()["telemetry"]["actual_rpm"] == 400
model.advance(100)
assert model.snapshot()["telemetry"]["actual_rpm"] == 0
```

State persists between commands and time steps. The rates and resulting RPM in this example are **synthetic defaults**, not appliance measurements.

`PhysicsConfig` is a frozen dataclass:

| Field | Default | Interpretation in this model |
|---|---:|---|
| `acceleration_rpm_s` | 4000.0 | Increase in signed velocity magnitude per virtual second |
| `deceleration_rpm_s` | 6000.0 | Active slowing/STOP/reversal rate |
| `coast_deceleration_rpm_s` | 1000.0 | Chosen slowing rate for SLEEP; hypothetical |
| `heating_c_s` | 1.0 | Linear synthetic temperature increase rate |
| `cooling_c_s` | 0.1 | Linear synthetic cooling/ambient approach rate |
| `ambient_c` | 20.0 | Synthetic ambient temperature |
| `speed_rpm` | `(0,200,700,1200,2000,4500,7500,10500,13500,16500,19000)` | Illustrative requested-RPM points for levels 0–10 |

`PowerBoardModel(config=None)` exposes:

| Member | Behavior |
|---|---|
| `.feed(data: bytes) -> list[bytes]` | Incremental TX stream input; schedules one current RX for each accepted command and returns ready responses |
| `.advance(delta_ms: int) -> list[bytes]` | Advance nonnegative virtual milliseconds, integrate chosen dynamics and return queued responses now due |
| `.sample() -> list[bytes]` | Schedule a current RX and drain ready responses; does not advance time |
| `.snapshot() -> dict` | Inspect state without scheduling RX or advancing time |
| `.set_sensors(**changes)` | Validate/inject synthetic measurements/status; no implicit firmware interlocks |
| `.set_faults(delay_ms=0, drop_every=0, corrupt_every=0, disconnected=False)` | Replace response-fault settings; zero disables each frequency |
| `.configure(**changes)` | Atomically replace physics coefficients, retaining state/time; JSON speed lists are normalized to tuples |
| `.disconnect()` / `.reconnect()` | Change the virtual link flag, preserving requested targets |
| `.reset_input()` | Discard an incomplete input fragment at a development client boundary |
| `.reset_transport()` | Discard incomplete input and queued RX, retaining physics state/time |
| `.now_ms`, `.connected`, `.controller`, `.config`, `.log`, `.faults` | Current virtual clock, link/state/configuration and original model events |

`.snapshot()` includes `synthetic`, `now_ms`, `connected`, signed float `velocity_rpm`, float `temperature_c`, Android `requested_direction`, `controller`, `physics`, decoded `telemetry`, `rx_hex`, `faults`, `queued_responses` and `input_remainder_bytes`. Positive velocity is clockwise and negative is counterclockwise. RX carries unsigned RPM magnitude and a separate direction bit. Sensor values are rounded into the protocol's integer fields.

Rejected framing/unknown/calibration/semantic-invalid input is logged and does not actuate the model. Partial input is retained until complete. Accepted TX changes targets immediately; measured RPM evolves only when time advances. Responses delayed by a fault retain their earlier captured state. Response faults do not undo an accepted command.

The model is not internally thread-safe. Serialize access yourself or use the locking server/adapter. Do not mutate `.controller` directly when using synchronized components or recording: use the facade's methods so physics and event accounting remain consistent.

## In-memory application seam

```python
from mcc_powerboard_simulator.mock import MockPowerBoardAdapter

port = MockPowerBoardAdapter()
port.start(speed=2)
port.advance(250)
moving = port.snapshot()
port.stop()
port.advance(250)
stopped = port.snapshot()
assert stopped["telemetry"]["actual_rpm"] == 0
```

`MockPowerBoardAdapter(model=None)` offers `.start(speed, direction=Direction.COUNTER_CLOCKWISE, temperature_level=0, operation=Operation.STANDARD)`, `.stop()`, `.feed(raw)`, `.advance(delta_ms)` and `.sample()`, each returning a list of synthetic RX bytes. `.snapshot()` returns a dictionary. `.set_sensors`, `.set_faults` and `.configure` return no value. `.model` and `.model_lock` are available for explicitly coordinated access.

This is a development seam for source you control, not a drop-in proprietary Binder interface. Application logic above an injected port can keep its domain operations, while a development adapter supplies synthetic state. An existing MCLauncher APK cannot use this endpoint merely because the protocol bytes match: its compiled serial/Binder transport would still need an authorized integration change. No such binary patch is supplied.

The [Kotlin example](../../../../../examples/headless.py) illustrates that source-level interface and constructor injection. Its small mock stores requests and injected UI sensors; it does not encode RX or model physical RPM. It has not been compiled/tested as an Android application in this release.

## Raw loopback TCP

```python
from mcc_powerboard_simulator.server import PowerBoardTCPServer

with PowerBoardTCPServer(port=0) as server:
    host, port = server.address
    assert host == "127.0.0.1"
    server.advance(100)  # explicit virtual time; no automatic API clock
    state = server.snapshot()
```

`PowerBoardTCPServer(model=None, *, port=0)` exposes `.start() -> self`, `.close()`, `.address`, `.running`, `.client_connected`, `.model` and `.model_lock`. It is a context manager, and a closed instance cannot restart. `.feed`, `.advance` and `.sample` return RX lists and forward ready RX to the currently connected client. `.set_sensors`, `.set_faults`, `.configure` and `.snapshot` serialize model access under the same reentrant lock.

One active raw client is supported; additional connections are closed. TCP transports the ordinary 15-byte TX/27-byte RX format, allowing arbitrary byte fragmentation and concatenation. There is no extra clock opcode, JSON wrapper or ACK field. Call `.advance()` through the local API to change virtual time. The `serve` CLI additionally supplies a monotonic-clock-driven preview and nominal 100 ms status sampling unless `--manual-clock` is selected.

TCP disconnect closes the development socket and resets partial parser input; it does **not** invent a board watchdog or automatic motor STOP. The chosen virtual target can remain active. Closing a socket is therefore not a substitute for requesting and observing a simulated stop.

## Synthetic sensor and fault controls

Use the native desktop controls or Python methods such as `model.set_sensors(error_code=5)` and `model.set_faults(drop_every=3)`. Embedding code can call the corresponding locked `server.set_sensors(...)`, `server.set_faults(...)` and `server.sample()` methods. These are local simulation controls, not extra wire commands.

No HTTP API or browser frontend is included. The [client self-test](../../../../../examples/headless.py) uses an in-process sensor callback and raw TCP bytes to exercise the full start/acceleration/rotation/STOP/error cycle. External client mode observes motion and telemetry only; fault injection is not available through an invented protocol opcode.

## Recording and deterministic replay

`RecordingSession(config=None)` accepts an optional `PhysicsConfig` and creates a fresh persistent `PowerBoardModel`, giving replay a known initial state. It records `.feed`, `.advance`, `.sample`, `.set_sensors`, `.set_faults`, `.configure` and `.reset_input` calls along with responses/checkpoints. `.snapshot()` inspects the current state; `.to_dict()` provides a JSON-compatible recording and `.save(path)` writes it to a local file. `.model` exposes the wrapped model for inspection. Use the recording facade rather than directly mutating that underlying model/controller if the operation must be replayed.

Version 0.2.0 also records `.reset_transport()` at integrated connection boundaries. Previous recording-v1 files remain readable; readers older than 0.2.0 cannot interpret this new operation. Connection metadata is visual diagnostics rather than a recipe for reopening sockets during replay.

`replay_recording(recording_dict)` validates supported recorded operations, re-executes them against a new synthetic model and compares RX bytes and state checkpoints. Its result includes `PASS`, `status`, `events`, `matched`, `mismatches` and `final_state`. A matching replay proves determinism for the recorded software inputs/configuration; it does not prove hardware fidelity.

```console
python -m mcc_powerboard_simulator record --file session.json
python -m mcc_powerboard_simulator replay --file session.json
python -m mcc_powerboard_simulator serve --record-file interactive-session.json
```

`record` creates a deterministic synthetic full-cycle session. `serve --record-file` preserves a development run on clean shutdown. Replay uses local JSON, not executable callbacks or network targets. See [fidelity](fidelity.md) and [scenarios](scenarios.md) for the scientific scope.
