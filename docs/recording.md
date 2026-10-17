# Recording and replay

`DigitalTwin(..., record=True)` records supported inputs, binary responses and deterministic checkpoints. Saving is explicit and local:

```python
from monsieur_cuisine_sdk import DigitalTwin, replay

twin = DigitalTwin("mcs", seed=292)
twin.start_motor(2, direction="ccw", duration=2)
twin.advance(0.2)
twin.sample()
twin.stop_motor()
twin.advance(2)
twin.save("session.json")
reconstructed = replay("session.json")
assert reconstructed.get_state() == twin.get_state()
```

```sh
mc-sdk --model mcc record --file session.json --seconds 1
mc-sdk --model mcc replay session.json
mc-sdk --model mcc telemetry session.json --input-format recording --csv telemetry.csv
```

## Unified schema

`monsieur-cuisine-recording-v1` contains explicit initial model, seed, complete initial parameters, configured action/queue limits, a synthetic marker and actions. Each action names one known operation and includes input, expected `rx_hex` and a checkpoint. Model switches are actions; replay never guesses the model from bytes.

Checkpoints retain common/profile state, selected-stream remainder and oversized-envelope quarantine counter, fault settings, pending-response bytes/due times, response counter and overflow state. Ownership/listener objects are external lifecycle metadata and are not serialized as executable callbacks. Replay reconstructs the model from its seed, initial parameters and complete action sequence; checkpoints are comparisons, not restorable memory images. Replay validates limits and supported operations before applying data to a fresh local model, then compares the expected bytes and checkpoints. A mismatch identifies its action. No network endpoint, arbitrary method name or Python code in a file is executed.

This is a deterministic regression format, not a signed or authenticated recording. An editor can alter both inputs and expectations to create a different internally consistent session. Host observation time remains separate from original wire fields. A fault-injected corrupted RX can be a legitimate expected byte result while still failing frame validation.

## Capacity and lifecycle

The common recorder caps actions at 100000 and uses an approximate 32 MB recording budget, reserving space for a terminal disarm. With the default `on_recording_full="stop"`, on capacity it removes targets, clears transport queues and records a terminal stop before rejecting further normal operations. Save the ended recording and start a new session. With `on_recording_full="continue"` (the desktop's policy) the recording is marked `"truncated": true`, the recorded prefix still replays exactly, and the simulation continues unrecorded; the desktop records every 50 ms poll, which filled an MCC trace in about three minutes before this policy. Bounded visual histories are separate from the complete action history. File replay is limited to 100 MB and 24 hours of total virtual advances; a single advance is at most 3600 seconds.

`mc-sdk record` saves and verifies an ended capacity trace, reports the reason and returns status 1 when the requested duration could not be completed. It does not discard the completed portion. The GUI/API `new_session()` retains the previous trace as `last_recording`; save it before replacing it again.

A disconnected-link fault may prevent an ordinary wire STOP from reaching the simulated board. Lifecycle disarm and connection cleanup directly remove targets as host policies. Recording includes those lifecycle operations and preserves finite coasting/cooling, so a stop request is not mislabeled as physical confirmation.

## Legacy formats

The canonical MCC helper still reads/writes `mcc-powerboard-recording-v1` with its selected-field checkpoints. Its recorder and replay now have matching configurable `max_events` budgets, default 100000, and reject before a recording operation would exceed that budget. The earlier MCS helper has its own historical format. These files are **not** the unified schema and are not silently relabeled by `mc-sdk replay`. Use the corresponding canonical legacy helper for old data; create new shared sessions through the common API. See [migration](migration.md) for import paths and known differences.
