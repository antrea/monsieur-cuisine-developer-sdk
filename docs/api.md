# Python API

```python
from monsieur_cuisine_sdk import DeviceModel, DigitalTwin, replay

twin = DigitalTwin(model=DeviceModel.MCC, seed=292)
twin.start_motor(speed=2, direction="ccw", temperature=60, duration=0)
twin.advance(0.25)
frames = twin.sample()
state = twin.get_state()
print(state.actual_speed, state.speed_unit)
twin.stop_motor()
twin.advance(2)
assert replay(twin.recording).get_state() == twin.get_state()
```

Model selection is mandatory. A single owner thread creates and mutates the twin. A network adapter or GUI shares that instance instead of creating another model. Mutations from another thread fail explicitly. `get_state()` returns a frozen `TwinState` with a detached raw-state dictionary; `.to_dict()` provides JSON-compatible data. Editing the returned copy cannot change the model.

## Constructor and argument types

```python
DigitalTwin(
    model: DeviceModel | str,
    *,
    seed: int = 292,
    parameters: dict | None = None,
    record: bool = True,
    max_actions: int = 100000,
    max_pending_bytes: int = 65536,
    on_recording_full: str = "stop",
)
```

| Argument | Accepted value |
|---|---|
| `model` | `DeviceModel.MCC`, `DeviceModel.MCS`, `"mcc"` or `"mcs"`; required |
| `seed` | Integer used for deterministic synthetic behavior |
| `parameters` | Profile-specific JSON-compatible configuration or `None` for defaults |
| `record` | Boolean; enables complete bounded action recording |
| `max_actions` | Integer 2–100000; includes capacity reserved for terminal disarm |
| `max_pending_bytes` | Integer 269–1048576; maximum scheduled response bytes |
| `on_recording_full` | `"stop"` (default): a full recording requests a synthetic STOP and ends the session. `"continue"`: the recording is marked `truncated` and the simulation keeps running unrecorded (used by the desktop) |

Common speed is an integer UI level **0–10**. Direction is `"cw"` or `"ccw"`; temperature is an exact integer Celsius target from the profile table. Duration is integer seconds, with model-specific support below. Times accept finite integer/float seconds; `advance()` and fault delays are limited to 3600 seconds per call. Boolean values do not stand in for integer command fields.

## Common operations

| Operation | Behavior / return |
|---|---|
| `DigitalTwin(model, seed=292, parameters=None, record=True, ...)` | Creates one inert, explicit-profile session; no GUI, socket or device is opened |
| `start_motor(speed=2, direction='ccw', temperature=0, duration=0)` | Encodes a profile command and feeds it; returns ready RX byte frames |
| `stop_motor()` | Sends the profile STOP; retains finite model inertia and any configured link-fault effect |
| `set_temperature(celsius)` | Reissues the current command with an exact supported Celsius target: MCC keeps its operation (e.g. KNEAD), speed and direction; MCS keeps function, raw level, direction, turbo lock and the remaining countdown. Idle models heat at speed 0 |
| `tare()` | Uses the profile's documented scale operation |
| `set_sensors(**values)` | Validates a complete normalized update, then injects it; returns state |
| `set_faults(delay_seconds=0, drop_next=0, corrupt_next=0, disconnected=False)` | Replaces common response/link fault settings |
| `feed(bytes)` | Accepts arbitrarily split/concatenated TX of the selected profile; returns ready RX |
| `advance(seconds)` | Advances virtual time and delivers delayed RX; returns state |
| `sample()` | Requests synthetic telemetry and returns ready RX |
| `receive_ready()` | Drains ready queued RX without advancing time |
| `get_state()` / `capabilities` | Inspect detached state and profile metadata |
| `disarm()` | Lifecycle cleanup: removes targets and clears transport fragments/queues |
| `switch_model(model, parameters=None)` | Closes registered connection, disarms old model and starts a fresh isolated generation |
| `new_session(model=None, parameters=None)` | Starts a fresh recording/model generation; retains the completed trace as `last_recording` |
| `save(path)` / `replay(recording_or_path)` | Writes local data / validates and reconstructs a deterministic session |

`parameters` is a model-specific JSON object. MCC parameters configure illustrative RPM/rates/ambient temperature; MCS parameters configure its independent raw-level and thermal model. Obtain defaults from a profile or the recording's `parameters`; do not apply one device's configuration keys to the other. Each action can advance at most 3600 seconds; a session has a 24-hour virtual-time budget.

MCS additionally bounds completed fixed-grid physics work to one million ticks per session, so its work limit can be reached before the 24-hour clock budget. Create a new session for further independent experiments. `set_faults()` and `save()` return `None`; state-changing operations returning state or ready bytes are listed above. `disarm()` performs cleanup and returns `None`.

## State and units

| Field | MCC | MCS |
|---|---|---|
| `requested_speed` | UI level 0–10 | UI level corresponding to native raw level / 2 |
| `actual_speed`, `target_speed`, `speed_unit` | Nonnegative RPM magnitude, `rpm` | Native level magnitude/target, `raw_motor_level` |
| `actual_rpm` | Synthetic measured RPM | `None`; no conversion established |
| `requested_direction`, `actual_direction` | `cw` / `ccw` | `cw` / `ccw`, with `stopped` at zero actual level |
| `temperature`, `target_temperature` | Celsius | Celsius |
| `weight` | Signed grams field | Model grams; raw scale value/decimals retained in native research |
| `lid_open`, `ntc_present`, `error_code`, `firmware` | Profile observations / injected values | Profile observations / injected values |
| `motor_on`, `heater_on` | Native model status flags | Native modeled motion/heater demand |
| `raw` | Profile snapshot without full history | Profile snapshot without full history |

Common `time` is virtual seconds. `generation` changes when the model changes; callbacks carry that generation to reject stale sessions. The wire itself does not acquire a common timestamp or generation field.

`subscribe_rx(callback)` delivers `(raw_bytes, generation)` on the owning thread. Observers may read `get_state()`; defer mutations to the next owner-loop iteration. Reentrant mutation is rejected, and observer exceptions are isolated/diagnosed rather than contaminating a new generation.

Normalized sensor names: `weight`, `temperature`, `lid_open`, `ntc_present`, `error_code`, `firmware`. MCC integer wire fields reject fractional/out-of-range values. MCS keeps its documented finite numeric model ranges and exposes saturation metadata. Validation failure does not partly apply a batch. Error numbers retain each profile's meaning.

MCC targets must be one of `0,37,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130`. MCS additionally has a 40 °C level. MCC duration must be zero; MCS manual duration is 0–5940 seconds. Inspect capabilities for exact support instead of assuming cross-model equivalence.

## Ownership, faults and lifecycle

Remote ownership guards motor commands and model replacement. Sensor/fault injection stays available to the host. Desktop STOP disconnects and disarms remote control. Normal command `stop_motor()` can be affected by an explicitly injected disconnected-link fault; lifecycle `disarm()` removes targets directly as a simulator policy. Neither confirms physical braking.

Delay/loss/corruption faults affect telemetry, while an accepted command's effect remains. Model switching clears pending replies, fragments, ownership and fault state; no old response is delivered into the new generation. Histories/diagnostics and transport buffers are bounded. Recording limits reserve a terminal disarm action; see [recording policy](recording.md).

For raw research APIs, import `monsieur_cuisine_sdk.profiles.mcc.protocol` or `.profiles.mcs.protocol`. Canonical codec objects are also reachable through retained legacy aliases; [migration](migration.md) distinguishes those helpers from the shared owning facade.

## Errors and integration hooks

| Error | Meaning / caller response |
|---|---|
| `ValueError` | Invalid model, unsupported command value, nonfinite time, malformed input/recording or exceeded work bound; correct the input or start a fresh session |
| `OwnershipError` | A different command owner holds the session; disconnect/release it instead of issuing competing commands |
| `RecordingLimitError` | Recording capacity reached under the default `on_recording_full="stop"`; targets are disarmed with a terminal trace, so save it and call `new_session()` |
| `RuntimeError` | Access from a thread other than the creating owner; dispatch work to the owner loop |
| `OSError` | Explicit local save/load failed; choose a valid path and permissions |

`OwnershipError` and `RecordingLimitError` are exported `ValueError` subclasses. Invalid complete frames can instead be rejected with bounded stream/timeline diagnostics and no command effect; absence of RX alone is not a transport acknowledgment. `command_count` counts frames the selected model accepted; `rejected_commands` counts complete frames it refused (each also logged as a `rejected_command` timeline event); `stream.issues` lists bytes discarded by framing. After a single stray or missing byte the selected-profile framer resynchronizes at the next valid frame.

`subscribe_rx(callback)` and `before_switch(callback)` return an unsubscribe callable. The former receives `(bytes, generation)`; the latter lets an adapter close resources before a fresh profile/session is installed. A manual adapter can use `claim(owner)` and `release(owner)` with the same non-`None` identity token. Release alone does not request STOP; adapter cleanup must disarm explicitly. Ordinary applications should use the provided connection adapter rather than manage leases themselves.

`recording` is the current JSON-compatible trace; `save(path: str | pathlib.Path)` writes it explicitly. `replay(recording: dict | str | pathlib.Path, *, cancelled=None) -> DigitalTwin` reconstructs an independent twin, checks expected bytes/checkpoints and optionally polls a cancellation callable. It does not replace an existing GUI session or evaluate executable callbacks from the file.
