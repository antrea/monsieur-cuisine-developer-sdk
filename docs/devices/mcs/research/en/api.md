> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Python developer API

```python
from mcs_protocol import (encode_manual, encode_operation, parse_frame,
                          decode_command, decode_telemetry, StreamParser)
from mcs_digital_twin import DigitalTwin, ModelParameters, replay

twin = DigitalTwin(seed=7, parameters=ModelParameters(noise_grams=0.1), record=True)
tx = encode_manual(speed=3, temperature=60, seconds=90)
command = decode_command(tx)
rx = twin.transact(tx)
twin.sensors(mass=200, lid_open=False)
twin.advance(2.0)
rx = twin.transact(encode_operation(opcode=0x0801))
telemetry = decode_telemetry(rx)
assert parse_frame(rx).opcode == 0x0801
assert replay(twin.recording).state.snapshot() == twin.state.snapshot()
```

| API | Contract |
|---|---|
| pack(payload, sequence=1, subtype=0, bitmap=b'OB') | envelope only, opcode must exist |
| unpack(raw), parse_frame(raw) | strict envelope dict / immutable Frame |
| decode(raw, direction='rx') | JSON-friendly fields plus raw hex; unknown data preserved |
| encode_manual(speed=0, temperature=0, seconds=0, reverse=False, sequence=1) | UI speed 0..10, temperature table, seconds 0..5940 |
| encode_operation(...) | raw level 0..20; opcode0801/02/03/05; legacy flag; see signature |
| encode_ota(subcommand, data=b'', packet_sequence=0, sequence=1) | documented offline TX only; no FE05 generator |
| encode_telemetry(Telemetry(...), sequence=1) | operational RX validation and encoding |
| decode_command / decode_telemetry | typed OB/subtype0 operation values retaining raw Frame |
| Sequence(value=0).next() | increment, wrap, skip 0x66 |
| StreamParser(max_frame=4096, timeout=1, max_errors=1024) | feed chunks, expire incomplete prefixes, finish tail |
| detect_profile(raw,direction='rx') | compatible layout list; version_detected always None |
| inspect_frame(raw,direction='rx') | byte offsets, unsigned/signed values, field labels |
| DigitalTwin.transact(bytes) | bytes or None on dropped/delayed reply; exception on unsupported input |
| DigitalTwin.advance(seconds) | fixed-grid deterministic snapshot, no sleep |
| sensors(mass=..., lid_open=..., ntc_present=..., error=..., temperature=..., button=...) | atomic validated synthetic input |
| faults(drop_next=0, corrupt_next=0, delay_seconds=0) | replaces fault configuration |
| receive_ready() | drains due virtual responses |
| interrupt() | terminal session interruption; targets stop |
| save(path), replay(recording, compare=True) | JSON recording; exact response/state comparison |
| InMemoryTransport(twin).exchange(bytes) | frame adapter, no external I/O |
| run_scenario(dict_or_path) | ScenarioResult(twin,samples,checks), .passed |


`ProtocolError(ValueError)` covers malformed envelopes/ranges/layouts; `UnsupportedCommand(ProtocolError)` covers valid but unmodeled messages. `ModelParameters` and sensors reject non-finite values and inappropriate types. Dataclasses `Frame`, `OperationCommand`, `Telemetry`, `MachineState`, `ModelParameters` expose type hints. Enums `Evidence`, `Direction`, `ErrorCode` retain uncertainty and known labels; unknown numeric error codes remain representable in Telemetry. `Frame.to_json()` and `Telemetry.to_dict()` preserve raw data. Independent SDK import does not load Tk.

Stream example: `p.feed(chunk, now=0.2)` returns complete bytes frames; `p.expire(now=1.3)` explicitly handles an expired incomplete prefix. Time is supplied by the caller and is not read from hardware. Diagnostics are a bounded deque; `finish()` returns/discards leftover bytes. The parser has a 4096-byte default cap, sufficient for 269-byte FE02, adjustable to the envelope maximum of 65536.

Scenarios have `format_version:1`, `seed`, optional `parameters`, `duration`, `sample_period`, `events` and `expect`. Event: `{at: 1.0, action: "manual", values: {speed:3}}` (actual file must be valid JSON). Actions: manual, operation, ota, hex (with hex string), sensors, faults, interrupt, ready. Equal-time inputs execute in source order before sampling. Expectations compare a final state field using eq/lt/le/gt/ge. They are data, never eval. ScenarioResult retains snapshots and recording. OTA scenario data can use the hex action for arbitrary byte payloads.

Recordings are a separate `format_version:1` object containing seed, parameters and actions `{kind,arguments,result}`. Inputs and generated responses/snapshots are compared in replay, including drained delayed frames. Recordings are experimental and versioned; use trusted resource sizes. Exact floating-point snapshots are guaranteed for repeated runs in the tested environment, not promised bit-identical across all math library implementations. Do not concurrently mutate a twin from multiple threads. A headless application controls the clock explicitly; GUI scheduling is a separate layer.


## 0.2.0 Integrated Android Connection

The existing model/API now also supports optional direct Android TCP ownership in the same Python process. Normal startup remains local and listener-free. See [Android Connection](../android-connection.md). `DigitalTwin.disarm()` removes targets and delayed old replies during session handoff; recordings replay this new action. No physical hardware adapter is implemented.
