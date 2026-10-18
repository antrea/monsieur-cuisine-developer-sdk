> **SDK 2.0 correction:** see the [build-292 OEM host-policy evidence](../../../mcc-oem-policy.md).
> Turbo starts after 100 ms, then ticks every 1 s (8 s warning, about 600 s limit);
> release/lid opening/at least 60 C stops turbo. RX reads are every 500 ms.
> Count-up stops at its speed limit; idle sleep uses 420 s plus a 30 s countdown.
> Lid/errors are app policy, not proven firmware interlocks. Calibration progression
> in the current twin is a configurable hypothesis, superseding legacy refusal.

> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Commands and software behavior

The command catalog is specific to build 292, identified by the APK hash in the [research methodology](research-methodology.md). **High static confidence** below means the mapping is explicit in the examined DEX/Smali and its decompiled representation. It does not mean the physical effect, maximum duty cycle or controller implementation was tested.

`PowerBoard.getSendPayload()[B` constructs every listed TX field. `HardwareMachineService.onStartRequested(int,int,int,int)` maps Android work mode, speed, direction and temperature into the HAL state. The nominal hardware loop later serializes its most recent state. A Binder return is not a frame acknowledgment. See [timing and state](timing-and-state.md).

## Common parameter contract

| Parameter | Serializer range | Application constraint or distinction |
|---|---|---|
| Speed | Integer level 0–10 | Not RPM; manual start/resume can raise zero to level 1 |
| Temperature | Integer level 0–19 | Lookup in [serial specification](serial-protocol-v292.md#temperature-levels) |
| Direction | TX `00` CW / `01` CCW | Android uses 1 CW / 0 CCW |
| Duration | No TX field | Android manages timers; controller runtime behavior remains separate |
| Reserved bytes | Offsets 7–10 zero | No additional semantics identified |
| Tare | Offset 4 = `A9` or `00` | Separate field, not an operation opcode |
| Calibration | Offset 12 = `00`, `E6`, `E9` | ENTER/START suppress offsets 3–11; documentation/decoding only |

The general Android limits are reverse speed ≤3, heated speed ≤3, cold clockwise speed ≤10, with a kneading-specific reverse exception to 4. Speed >6 has a 900,000 ms maximum time; other speeds have 5,940,000 ms, with further program limits. These are application checks, not electrical specifications. The low-level encoder validates field ranges and does not reproduce the entire cooking UI policy.

## STOP: `00`

**Meaning:** `MOTOR_OFF_HEATER_OFF`; Android work mode 0. `HardwareMachineService.onStopRequested()` sets operation STOP, speed zero and temperature zero, retaining direction. A later periodic send emits the resulting frame. A canonical synthetic example is in the [frame specification](serial-protocol-v292.md#checksum-and-a-synthetic-stop).

**Relevant response:** RX status low two bits zero, actual RPM offsets 9–10 equal zero, and heater flag off provide useful *status observations*. They do not correlate a sample with this request. A sample received before STOP must not confirm it.

**Limits and certainty:** High static confidence in software assignment and byte encoding. Delivery, braking delay and de-energization after a lost host process are unverified. Sending STOP immediately followed by START may leave only START visible at the periodic transmitter.

**Evidence:** `HardwareMachineService.onStopRequested()`, `PowerBoard.getSendPayload()`, `SerialUtils.send(byte[])`; ledger P01–P04.

## Standard operation: `01`

**Meaning:** `MOTOR_ON_HEATER_ON`, Android work mode 1. The command carries selected speed, direction and temperature level. The enum's name does not prove that both outputs physically remain enabled when one requested parameter is zero.

**Parameters:** Speed 0–10 and temperature 0–19 at the serializer boundary; apply the stricter Android constraints above when modeling the application. Normal manual start/resume enforces a minimum speed of 1 in most standard paths. A zero speed field alone is therefore not a stable substitute for the UI's STOP behavior.

**Relevant response:** Motor/heater status bits, target speed level at 6, requested RPM at 7–8, actual RPM at 9–10, target temperature level at 11, target degrees at 12–13 and actual degrees at 14–15.

**Limits and certainty:** High static confidence in opcode and parameters. No motor acceleration curve, exact target RPM table or heating regulation algorithm has been reconstructed.

**Evidence:** `HardwareMachineService.onStartRequested(...)`, `PowerBoard.getSendPayload()`, `CookingManager.a()`, `CookingManager.i()`; P01–P02/P05.

## Heating and the heater-only enum: also `01`

**Meaning:** The HAL declares `MOTOR_OFF_HEATER_ON`, but build 292 serializes it as **`01`, not `02`**. There is no distinct heater-only branch identified in `onStartRequested(...)`. It is an enum alias at the wire serializer, not a confirmed standalone heater-only operation exposed by the original manual UI.

**Parameters:** Common speed and temperature fields remain present. The serializer alone cannot establish which parameter combination will keep the motor physically off while heating. The toolkit therefore has no separate invented `02` operation.

**Relevant response:** RX low bits value 2 means motor off/heater on. That **response state value is not a TX opcode**. Target and actual temperature remain relevant.

**Limits and certainty:** High static confidence in alias encoding; no physical heater-only behavior is claimed. Retaining heat in an intermittent rest requires a separately justified design.

**Evidence:** `PowerBoard.I_WorkCommand`, `PowerBoard.getSendPayload()`, `HardwareMachineService.onStartRequested(...)`; P01–P02.

## Steam: `03`

**Meaning:** `STEAM`, Android work mode 3, selected by `onStartRequested(...)`.

**Parameters:** Common serializer fields apply. `Presets.steamingCookingSteps()` models a 600 s preheat and 1,200 s cooking sequence, with temperature level 17 = 120 °C. These are preset software values, not mandatory wire fields or experimentally established physical timing.

**Relevant response:** Extended state byte 4 = 3, heater/motor bits, temperatures and board error 6 (lack of water) when the error flag is set.

**Limits and certainty:** High static confidence in mapping/preset structure. Preheat detection and controller internals are not fully specified by the opcode.

**Evidence:** `HardwareMachineService.onStartRequested(...)`, `PowerBoard.getSendPayload()`, `PowerBoard.getMotorHeaterExtendedState()`, `model.Presets.steamingCookingSteps()`; P01–P02/P05.

## Toast / roasting: `04`

**Meaning:** `TOAST`, Android work mode 4; exposed as the roasting preset.

**Parameters:** The original cyclic preset has initial duration 420 s, maximum 840 s, and alternates 5 s at speed 1 with 30 s at speed 0, counterclockwise, target 130 °C. It uses the special `04` operation. The same numbers attached to standard operation would not prove equivalent controller behavior.

**Relevant response:** Extended state byte 4 = 4, motor/heater bits, RPM and temperatures.

**Limits and certainty:** High static confidence in software encoding and preset. Zero-speed phase is not proof of a measured braking interval or a generally safe repeated-start duty cycle.

**Evidence:** `model.Presets.roastingCookingUnit()`, `CookingManager.b.onTick(...)`, `HardwareMachineService.onStartRequested(...)`, `PowerBoard.getSendPayload()`; P01–P02/P05.

## Knead: `05`

**Meaning:** `KNEAD`, Android work mode 5.

**Parameters:** Common serializer ranges apply; application validation permits the kneading reverse exception to speed 4. The original cyclic list contains 15 s reverse at speed 4, 1 s rest at zero, and 104 s clockwise at speed 4, with initial overall duration 45 s and maximum 120 s. Validation can rewrite rest duration above an 85 s total: do not simplify the list to a universal 15/1/29 s physical cycle.

**Relevant response:** Extended state byte 4 = 5, direction bit and actual RPM, motor/error state.

**Limits and certainty:** High static confidence in opcode and Android sequence. `CookingManager.b()` excludes a change of direction alone for work mode 5. This special treatment and the speed exception must not be generalized to custom manual cycles.

**Evidence:** `model.Presets.kneadingCookingUnit()`, `CookingManager.i()`, `CookingManager.b()`, `PowerBoard.getSendPayload()`; P01/P05.

## Turbo: `C6`

**Meaning:** `MOTOR_ON_HEATER_OFF_TURBO_MODE`, Android work mode 2. The original UI's press path calls `start(2,10,1,0)` and uses a Handler with a 100 ms interval.

**Parameters and observed gates:** The original UI requires STOP/FINISHED, clockwise direction, actual temperature <60 °C, target temperature level <5, an enabled step and the required closed-lid condition. The observed request uses speed 10 and no heating. These conditions are application logic, not complete controller safety documentation.

**Relevant response:** Low status bits value 3 denotes motor on/heater off Turbo; also actual RPM, temperature, direction and lid/error flags.

**Limits and certainty:** High static confidence that build 292 uses `C6` for Turbo. It is not justified to call this opcode a safe single-turn pulse. That wording belongs to older documentation and is discussed in [historical comparison](historical-comparison.md).

**Evidence:** `fragment.MainFragment` Turbo press/enable paths, `HardwareMachineService.onStartRequested(...)`, `PowerBoard.getSendPayload()`; P01–P02/P05.

## System sleep: `0F`

**Meaning:** `SLEEP`, Android work mode 6, mapped through the hardware service to the serializer.

**Parameters:** The frame retains the normal field layout and range checks. No additional parameter encoding for sleep has been identified. Do not infer an MCU reset, bootloader entry or power removal from this operation.

**Relevant response:** Ordinary status fields may be observed if responses continue; no dedicated sleep acknowledgment or verified wake/reset sequence has been established.

**Limits and certainty:** High static confidence in the mapping; unverified controller implementation and physical power-state behavior.

**Evidence:** `HardwareMachineService.onStartRequested(...)`, `PowerBoard.getSendPayload()`; P01–P02.

## Tare: offset 4 = `A9`

**Meaning:** A tare request is a flag in the current TX command, not an operation. The periodic hardware path manages the request as a pulse rather than keeping it asserted indefinitely.

**Parameters:** Offset 4 is `A9` when requested and `00` otherwise. The other command fields remain meaningful unless calibration ENTER/START suppresses them.

**Relevant response:** Signed weight offsets 16–19, scale stability bit at RX 3 and scale state/calibration fields 22–23. No request-correlated tare-complete acknowledgment was identified.

**Limits and certainty:** High static confidence in byte placement and software request handling; scale accuracy, settling time and exact controller completion behavior were not measured.

**Evidence:** `HardwareMachineService.onPerformPeriodicHardwareAction()`, `PowerBoard.getSendPayload()`, `PowerBoard.getScaleWeight()`; P01–P03.

## Scale calibration: documentation only

| TX offset 12 | Enum meaning | Observed serialization |
|---:|---|---|
| `00` | EXIT / normal | Normal command fields retained |
| `E6` | ENTER | Offsets 3–11 zeroed |
| `E9` | START | Offsets 3–11 zeroed |

Relevant RX fields are scale state at 22 and calibration step at 23; their exact value maps are in [response fields](response-fields.md#scale-state-and-calibration). These are scale calibration states, not MCU flashing commands. Historical `E7` is not a build 292 emission confirmed by this serializer. No calibration session was performed. High static confidence in encoding; no physical calibration validity or completion timing is claimed. Evidence: `PowerBoard.getSendPayload()`, scale state and calibration-step getters (P01).

The public encoder deliberately omits calibration ENTER/START generation. See [safety and limitations](safety-and-limitations.md).
