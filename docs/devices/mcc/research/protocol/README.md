> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# MCC build 292 protocol reference

This document describes the application side of the protocol used by `de.silpion.mc2`, **1.1.28-release, versionCode 292**. The reference APK has SHA-256 `5e9125bb5e618e8eb989bfff8096f09cbad5e4fd3e5b08768fd624f36efc0482`. Evidence consists of static analysis and offline software checks; no example frame is a measurement from an appliance. The [evidence ledger](../research-methodology.md#evidence-ledger) records methods, fingerprints and DEX offsets without distributing proprietary code.

All offsets are **zero-based**. TX means Android → board; RX means board → Android. The service selects `/dev/ttyMT0` at 4800 baud, with raw mode verified in the JNI wrappers. Electrical levels, pinout and complete 8N1 configuration were not established. The original transmit loop has a nominal 100 ms wait; it is not a real-time guarantee.

## TX frame: 15 bytes

| Offset | Byte | Meaning |
|---:|---:|---|
| 0 | `55` | Start |
| 1 | `0F` | Total length 15 |
| 2 | `A1` | Command type |
| 3 | variable | Operation, in the table below |
| 4 | `00` / `A9` | No tare / tare requested |
| 5 | 0–10 | Speed level, not RPM |
| 6 | 0–19 | Temperature level, not direct degrees |
| 7 | `00` | Reserved, written as zero |
| 8 | `00` | Reserved, written as zero |
| 9 | `00` | Reserved, written as zero |
| 10 | `00` | Reserved, written as zero |
| 11 | `00` / `01` | Clockwise / counterclockwise on the wire |
| 12 | `00` / `E6` / `E9` | EXIT/normal / ENTER / START scale calibration |
| 13 | variable | Unsigned sum of bytes 0–12 modulo 256 |
| 14 | `AA` | Terminator |

The original serializer replaces out-of-range speed or temperature levels with zero. The public encoder instead rejects out-of-range values, avoiding a silent input change. Structural acceptance does not mean a physically safe combination.

| Operation | Hex opcode | Evidence and limit |
|---|---:|---|
| Motor/heater STOP | `00` | The service also sets speed and temperature to zero and retains direction. This does not prove delivery or physical stopping. |
| Standard | `01` | Speed, direction and heating parameters; the enum name does not establish the electrical effect of every combination. |
| Heater-only enum | **`01`** | Alias in serializer 292, not a distinct `02` opcode. No physical heater-only combination was independently verified. |
| Steam | `03` | Steam mode |
| Toast | `04` | Toast mode |
| Knead | `05` | Knead mode |
| System sleep | `0F` | Sleep; it must not be renamed MCU reset or bootloader. |
| Turbo | `C6` | Turbo path in build 292; a safe single-turn pulse was not established. |

Tare and calibration are separate fields, not additional opcodes. For ENTER `E6` or START `E9`, the serializer zeros **all bytes 3–11**. The public encoder does not generate these calibration operations; the decoder documents their values. Historical examples `0A` and `E7` are not confirmed emissions from serializer 292.

Canonical **synthetic** STOP:

```text
55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA
```

A STOP retaining counterclockwise direction can have byte 11 = `01` and checksum `06`; it must not be rejected merely for differing from the canonical vector.

### Directions and temperature

| Representation | Counterclockwise | Clockwise |
|---|---:|---:|
| Android `Direction` | 0 | 1 |
| TX byte 11 | 1 | 0 |
| RX byte 3 bit 3 | 0 | 1 |

Android also declares NA = 2, which is not a third physical direction. The toolkit requires the two explicit directions.

Temperature levels 0–19 correspond respectively to **0/off, 37, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130 °C**. They are neither arbitrary setpoints nor measurements of thermal accuracy.

## RX frame: 27 bytes

| Offset | Format | Meaning |
|---:|---|---|
| 0 | `55` | Start |
| 1 | `1B` | Total length 27 |
| 2 | `B1` | Response type |
| 3 | Bitfield | State and sensors, in the table below |
| 4 | Enum | 3 Steam, 4 Toast, 5 Knead; others undefined |
| 5 | Byte | Raw board error code |
| 6 | Byte | Target speed level |
| 7–8 | uint16 big endian | Target RPM |
| 9–10 | uint16 big endian | Measured RPM |
| 11 | Byte | Target temperature level |
| 12–13 | uint16 big endian | Target temperature |
| 14–15 | uint16 big endian | Measured temperature |
| 16–19 | **int32 signed big endian** | Weight, presented as grams by the app |
| 20–21 | uint16 big endian | Firmware number reported by the board |
| 22 | Prioritized bitfield | Scale state |
| 23 | Enum | Scale calibration step |
| 24 | Raw byte | **Unknown meaning**, original getter `getNotAvailable()` |
| 25 | Byte | Unsigned sum of bytes 0–24 modulo 256 |
| 26 | `AA` | Terminator |

The original validator checks exact length, header, type, terminator and checksum. The modulo-256 sum is not a CRC, signature or authentication mechanism; compensating changes can preserve it.

### State byte 3

| Bit/mask | Interpretation |
|---|---|
| 0–1 / `03` | 0 motor/heater off; 1 both on; 2 motor off/heater on; 3 motor on/heater off, named Turbo |
| 2 / `04` | Scale stable |
| 3 / `08` | Clockwise direction when set |
| 4 / `10` | Error detected |
| 5 / `20` | Bowl temperature above target |
| 6 / `40` | Bowl NTC detected |
| 7 / `80` | Lid open |

RX state 2 is not TX command `02`. A motor-off bit does not mean measured RPM is zero. Presence of the NTC bit does not establish a complete hardware/software interlock chain.

### Signed, unsigned and RPM levels

Multibyte RPM/temperature/firmware fields mask their bytes as unsigned. Weight uses signed two's complement: `FF FF FF 9C` means **−100**. Firmware `13 3C` is arithmetically 4924; it is not a capture or proof of board compatibility.

The Java getters for individual bytes 6, 11 and 24 instead widen them as signed: `F4` becomes −12. The toolkit preserves raw unsigned 244 and the compatibility views `target_speed_level_signed`, `target_temperature_level_signed`, `unknown_byte_24_signed`. It does not define negative operating levels or assign meaning to byte 24.

`getActualSpeedLevel()` converts measured RPM into bins: 0 at ≤0; level 1 at 1–558; 2 at 559–1008; 3 at 1009–1437; 4 at 1438–3359; 5 at 3360–6349; 6 at 6350–9309; 7 at 9310–12312; 8 at 12313–15315; 9 at 15316–18232; 10 from 18233. These are UI bins, not the board's exact RPM targets.

### Scale and calibration

In byte 22, mask `04` overload has priority, followed by `01` calibration, then `02` normal. If none is present, the Android getter returns overload. The toolkit exposes `scale_state="not_available"` and separately `android_scale_state="overload"`, with a warning: it does not assume zero physically means overload. Other bits remain uninterpreted.

Byte 23: 0 initialization, 1 zero point, 2 first load 1 kg, 3 second load 3 kg, 4 success, 5 overload, 7 failure; others unavailable. These names document decoding rather than providing calibration instructions or firmware procedures.

## Board errors and Android codes

| Byte 5, with error flag set | Meaning | Internal Android code |
|---:|---|---:|
| 1 | Serial communication | 1 |
| 3 | Overvoltage | 2 |
| 4 | Undervoltage | 3 |
| 5 | Motor | 4 |
| 6 | Water missing | 5 |
| 7 | Motor overheating | 12 |
| 8 | Maximum runtime exceeded | 13 |
| Other | Undefined | 6 |

When the error flag is clear, the Android code associated with the board error is 0; the raw byte remains preserved. Scale overload contributes separately to Android code 7 and must not be confused with board error 7. Lid and NTC have dedicated flags. Android code NO_BOWL_DETECTED = 8 exists, but no assignment was identified in the examined sensor mapping.

## Timing, acknowledgement and limits

No per-command ACK, timestamp or sequence counter was identified in the frame. The original reader retains the latest block without receive metadata; a valid frame can be stale. Closely spaced STOP and START can be coalesced before periodic transmission. A positive Binder return does not prove a successful UART write or physical stopping.

Observed Android limits include manual reverse ≤3, heating with speed ≤3, reverse kneading exception 4, maximum duration 15 minutes above level 6 and 99 minutes otherwise, with further preset limits. Residual heat ≥60 °C and speed ≥4 involve thermal warnings. These are not certified mechanical limits or safe repeated-restart settings.

MCU firmware, watchdog, braking, interlocks, electrical model and identity of an installed APK remain unverified. The Digital Twin applies declared dynamic hypotheses; its PASS does not measure the appliance.

Related references: [specification](../serial-protocol-v292.md), [commands and evidence](../commands.md), [RX fields](../response-fields.md), [errors](../error-codes.md), [timing](../timing-and-state.md), [limits](../safety-and-limitations.md), [historical comparison](../historical-comparison.md). Machine-readable description: [protocol_292.json](../../../../../specs/mcc/protocol_292.json).
