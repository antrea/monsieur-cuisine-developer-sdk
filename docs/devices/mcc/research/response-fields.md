> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Response fields: 27-byte status frame

This table covers every byte consumed by the build 292 `PowerBoard` decoder. It is based on the reference APK and methods in ledger P01/P03 of the [research methodology](research-methodology.md#evidence-ledger). Offsets are zero-based. No real-device response is bundled; examples throughout this project are synthetic.

## Complete byte map

| Offset | Width | Type | Meaning / original getter family |
|---:|---:|---|---|
| 0 | 1 | Constant | `55` start |
| 1 | 1 | Constant | `1B`, total length 27 |
| 2 | 1 | Constant | `B1`, response kind |
| 3 | 1 | Bitfield | Motor/heater state and sensors; detailed below |
| 4 | 1 | Enum | Extended motor/heater state: 3 Steam, 4 Toast, 5 Knead; otherwise undefined |
| 5 | 1 | Enum | Raw board error code, interpreted with error flag |
| 6 | 1 | Raw unsigned byte; original getter has signed view | Target speed level |
| 7–8 | 2 | Unsigned 16-bit BE | Target RPM |
| 9–10 | 2 | Unsigned 16-bit BE | Actual RPM |
| 11 | 1 | Raw unsigned byte; original getter has signed view | Target temperature level |
| 12–13 | 2 | Unsigned 16-bit BE | Target temperature |
| 14–15 | 2 | Unsigned 16-bit BE | Actual temperature |
| 16–19 | 4 | **Signed** 32-bit BE | Weight, widened to a Java `long` after signed composition |
| 20–21 | 2 | Unsigned 16-bit BE | Powerboard-reported firmware version |
| 22 | 1 | Bitfield with priority | Scale state |
| 23 | 1 | Enum | Scale calibration step |
| 24 | 1 | Raw byte, **unknown** | Original getter named `getNotAvailable()`; no established semantics |
| 25 | 1 | Unsigned byte | `sum(frame[0:25]) & 0xff` |
| 26 | 1 | Constant | `AA` terminator |

Temperatures are presented as Celsius in the Android application. Weight is presented as grams. These application labels do not establish sensor calibration, resolution, measurement frequency or accuracy. Raw levels, target values and measured values should remain separate in downstream data models.

## Offset 3: status bits

| Bits | Mask | Meaning when set / value |
|---|---:|---|
| 0–1 | `03` | Motor/heater state enum below |
| 2 | `04` | Scale data stable |
| 3 | `08` | Clockwise; clear means counterclockwise |
| 4 | `10` | Error detected |
| 5 | `20` | Bowl temperature above target |
| 6 | `40` | Bowl NTC detected |
| 7 | `80` | Lid open |

| `status & 03` | Motor enabled | Heater enabled | Original interpretation |
|---:|---|---|---|
| 0 | No | No | Motor off, heater off |
| 1 | Yes | Yes | Motor on, heater on |
| 2 | No | Yes | Motor off, heater on |
| 3 | Yes | No | Turbo: motor on, heater off |

These are output state bits interpreted by Android. They are not independent TX opcodes. In particular, RX state 2 does not justify generating TX operation `02`; the build 292 heater-only enum serializes as `01`.

Direction is independent of motion. A stopped controller can still report a direction. Motor-enabled false alone does not establish measured RPM zero; inspect both, and require a newly received sample for any post-STOP status check.

The NTC bit has a getter in `PowerBoard`; no application consumer establishing a complete bowl-presence interlock was identified in the examined mapping. Treat it as an observed bit, not a certified software guard.

## Numeric conversion

For a two-byte unsigned big-endian field beginning at `k`:

```python
value = int.from_bytes(frame[k:k + 2], byteorder="big", signed=False)
```

Weight uses a different signedness:

```python
weight = int.from_bytes(frame[16:20], byteorder="big", signed=True)
```

For example, the synthetic bytes `FF FF FF 9C` represent **−100**, not 4,294,967,196. The signed result remains negative when widened to a larger integer type. Firmware bytes `13 3C` represent 4924 and `13 98` represent 5016; these are arithmetic examples, not captured board data. Firmware numbering does not reveal the MCU family, flash layout or cross-board compatibility.

Three original getters directly widen Java signed bytes: `getTargetSpeedLevel()` at offset 6, `getTargetTemperatureLevel()` at offset 11, and `getNotAvailable()` at offset 24. For raw values 128–255, their returned integer is the raw byte minus 256: synthetic `F4` is raw unsigned 244 and original-getter value **−12**. This differs from multibyte RPM and temperature decoding, which explicitly masks component bytes as unsigned.

The toolkit preserves canonical unsigned `.target_speed_level`, `.target_temperature_level` and `.unknown_byte_24` fields alongside `.target_speed_level_signed`, `.target_temperature_level_signed` and `.unknown_byte_24_signed` compatibility views, also included in JSON output. Out-of-range target levels remain available with semantic warnings; they do not become valid negative operating levels. Neither numeric representation explains the physical meaning of byte 24, which remains unknown.

## Actual speed buckets

`PowerBoard.getActualSpeedLevel()` derives a display level from measured RPM. It does not use a table of target RPM setpoints.

| Actual RPM | Derived level |
|---:|---:|
| ≤0 | 0 |
| 1–558 | 1 |
| 559–1008 | 2 |
| 1009–1437 | 3 |
| 1438–3359 | 4 |
| 3360–6349 | 5 |
| 6350–9309 | 6 |
| 9310–12312 | 7 |
| 12313–15315 | 8 |
| 15316–18232 | 9 |
| ≥18233 | 10 |

The RX RPM field itself is unsigned 16-bit. The ≤0 bucket describes the application helper's comparison, not support for negative measured RPM on the wire. Do not infer exact target RPM, motor gearing or safe loads from these bucket boundaries.

## Scale state and calibration

Offset 22 is decoded in this priority order:

1. If `value & 04`, report overload.
2. Otherwise, if `value & 01`, report calibration.
3. Otherwise, if `value & 02`, report normal.
4. The original getter falls back to **overload** when none matches, and on invalid input.

Consequently `07` selects overload, not normal; `03` selects calibration. Preserve the complete byte alongside the interpreted state, because remaining bits have no identified meaning. The fallback is observed Android behavior, not proof that a zero scale-state byte physically means overload.

For this last case, the toolkit exposes raw interpretation `scale_state = "not_available"` separately from `android_scale_state = "overload"`, with an explicit warning. This preserves the original fallback for comparison without assigning a physical meaning to an unrecognized bit pattern.

| Offset 23 value | Calibration-step meaning |
|---:|---|
| 0 | Initializing |
| 1 | Zero point |
| 2 | First load, 1 kg |
| 3 | Second load, 3 kg |
| 4 | Success |
| 5 | Overload |
| 7 | Failure |
| Other | Not available / unmapped |

These values document the original scale interface. They do not constitute calibration instructions, and no physical calibration was performed.

## Errors, invalid data and freshness

Keep raw board code at offset 5 distinct from the error flag and from the mapped Android error number. [Error codes](error-codes.md) documents all three. A valid checksum does not authenticate a sample or make it recent.

The original Android layer validates a cached buffer and can repeatedly read the same valid frame. Several getters return conservative/default values on invalid input; those defaults should not be treated as fresh sensor measurements. This toolkit raises structural parse errors instead of presenting an invalid frame as valid telemetry. [Timing and state](timing-and-state.md) describes stream recovery and freshness limits.
