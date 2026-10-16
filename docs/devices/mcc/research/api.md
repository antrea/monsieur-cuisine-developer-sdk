> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Python API and examples

Python 3.11+, standard library only. This page covers the offline `mcc_protocol` modules, which neither open a device nor contact a network. The principal dynamic [Digital Twin API](powerboard-simulator/api.md) is separate and its native GUI requires Tcl/Tk. Optional developer transport modules start only by explicit request. The API is experimental at version 0.1.0.

## Encoding and decoding

```python
from mcc_protocol.codec import Direction, Operation, decode_frame, encode_tx

raw = encode_tx(Operation.STANDARD, speed=2,
                direction=Direction.COUNTER_CLOCKWISE)
frame = decode_frame(raw)
print(frame.to_dict())
```

`encode_tx(operation=Operation.STOP, *, speed=0, temperature_level=0, direction=Direction.CLOCKWISE, tare=False) -> bytes` produces a synthetic 15-byte TX. Integer ranges: speed 0..10, temperature level 0..19, Android direction 0..1; boolean values are rejected for integer fields. `tare` must be a bool. Operations must belong to `Operation`. Unknown operations and active calibration generation are unavailable. Range validation is stricter than the original zero-substituting serializer. No physical safety policy is implied by accepting a combination of fields.

`Direction.COUNTER_CLOCKWISE == 0`, `CLOCKWISE == 1` are Android values; TX byte 11 is their inverse. `Operation` contains STOP 0, STANDARD 1, STEAM 3, TOAST 4, KNEAD 5, SLEEP 15, TURBO 198. The original heater-only enum aliases STANDARD/01; no distinct opcode 2 or independently verified heater-only physical parameter combination is established.

`decode_frame(raw: bytes | str) -> TxFrame | RxFrame` accepts bytes or one hexadecimal frame. The returned frozen record has `.kind`, `.raw`, `.warnings` and `.to_dict()`. JSON-compatible dictionaries retain raw hexadecimal bytes and unknown semantic values. RX exposes requested/measured fields, all eight status bits, `.actual_speed_level`, `.android_error_code`, `.scale_state`, `.android_scale_state`, `.unknown_byte_24` and `.unknown_byte_24_signed`. The signed view documents Java byte widening, without assigning a meaning to byte 24.

`target_speed_level_signed` and `target_temperature_level_signed` additionally expose the original Java byte-widening result at RX6/11; canonical raw fields remain unsigned. `scale_state` describes recognized bits; flags with no recognized bit yield `not_available`. The original Android fallback is separately exposed as `android_scale_state == "overload"`, with a warning. Priority is overload (mask 4), calibration (mask 1), normal (mask 2). See the [RX specification](response-fields.md) for every field and unit.

`parse_hex(text) -> bytes` accepts compact hex or ASCII whitespace, with no prefixes, commas or comments. `checksum(data) -> int` sums bytes modulo 256. `actual_speed_level(rpm) -> int` applies the observed application bins, not a measured controller setpoint curve. `TEMPERATURE_LEVELS` contains the 20 application values in degrees Celsius.

Malformed framing raises `FrameError`, a `ValueError` subclass with `.code`. Semantic anomalies instead produce warnings. Catch `FrameError` when reading untrusted local input. Never equate structural validity with a physically safe setting.

## Incremental parser

```python
from mcc_protocol.codec import encode_tx
from mcc_protocol.stream import StreamParser

raw = encode_tx()
parser = StreamParser()
assert parser.feed(raw[:4]) == []
frames = parser.feed(raw[4:] + raw)
assert len(frames) == 2
parser.finish()
```

`feed(chunk: bytes) -> list[TxFrame | RxFrame]` supports arbitrary byte boundaries, mixed frame types and concatenation. Noise, wrong types, bad checksums and malformed envelopes are discarded until a structurally valid frame is found. `.issues` holds `StreamIssue` records with code, message, stream offset, discard count, preview and `.to_dict()`. Additive checksums can accidentally match noise; this parser cannot authenticate data.

`.remainder` returns an unfinished candidate; `.buffered_bytes` and `.discarded_bytes` report counts. At most 26 incomplete bytes are retained between calls. The diagnostic list grows with errors; long-running callers should consume and clear it themselves. `finish()` raises `FrameError(code="truncated")` when a candidate remains. That exception exposes `.raw`, `.bytes_remaining`, `.expected_size`, `.missing_bytes`. It does not discard the candidate: more bytes may still be fed. Empty input is allowed at parser level; CLI validation rejects an empty file.

## Virtual controller and communication

`VirtualController(...)` is a mutable dataclass in `mcc_protocol.simulator`. `.apply_tx(raw)` applies a known, valid TX in memory; `.response()` serializes all RX fields; `.snapshot()` returns JSON-compatible state. `.set_sensors(**changes)` atomically validates injected values such as `actual_rpm`, `actual_temperature`, signed `weight`, `lid_open`, `error_code` and unknown byte 24. An error code sets the error flag unless supplied explicitly.

Commands change illustrative RPM targets instantly. STOP/SLEEP sets simulated motion and heating to zero; actual temperature remains a sensor value. This is a software hypothesis, not a firmware model. The controller does not emulate lid/error interlocks. Calibration commands are rejected. Constructor fields and method docstrings enumerate the complete synthetic state.

`MemoryLink(controller=None)` has `.now_ms`, `.log`, `.send(raw, *, delay_ms=0, drop=False, corrupt=False)` and `.sample(...)`. TX is applied immediately. Fault options affect the generated RX only: delay queues it, drop removes it, corruption flips one checksum bit. No periodic messages occur implicitly.

`.advance(delta_ms)` moves virtual time and returns ready `ReceivedFrame` records; `.receive_ready()` drains ready records without advancing. Each record has `.raw`, `.generated_ms`, `.received_ms`, `.sequence`, `.to_dict()`. Sequence counts local deliveries; neither it nor the timestamps are protocol fields or command acknowledgements. A delayed snapshot may arrive after a newer generated one.

## Intermittent software experiment

`IntermittentConfig(spin_ms, rest_ms, total_ms, speed, direction=COUNTER_CLOCKWISE, stop_timeout_ms=2000, max_sample_age_ms=1500)` validates positive integer virtual durations. It applies observed application duration limits and reverse-speed limits, without certifying the mechanical suitability of repeated starts.

`IntermittentProgram(config, send)` accepts a memory callback `send(bytes)`. Methods are `.receive(raw, now_ms, *, received_ms=None, sequence=None)`, `.start(now_ms)`, `.tick(now_ms)`, `.stop(now_ms)`. Call these in order with monotonic nonnegative virtual milliseconds, and deliver every received frame separately. Callbacks must be serialized and must not synchronously call back into the program.

Start requires a fresh stationary RX with lid closed and no detected fault/heating. The cycle is SPIN → WAIT_STOP → REST. REST begins only after a new local delivery after STOP reports zero RPM/motor off before the timeout. The absolute total deadline takes priority. Faults latch immediately; stale input, corruption, unexpected motion/heating and write-callback failures terminate the session. FINISHED, STOPPED and FAULT cannot automatically rearm. A new object is required for a deliberate new session.

This local observation cannot prove physical STOP or correlate RX to a particular TX. A newly received old snapshot cannot be identified on the wire. Host sequence metadata prevents only local replay. See [timing and limitations](timing-and-state.md).

`run_demo()` and `run_intermittent_demo()` return deterministic JSON-compatible scenario logs. CLI `demo` and `simulate` expose them. The intermittent scenario finishes at 12,000 virtual ms. [decode_frames.py](../../../../examples/headless.py) and [simulate_fault.py](../../../../examples/headless.py) run from any working directory using only this source tree.
