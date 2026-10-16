> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Serial protocol: MCLauncher build 292

This specification describes the serializer and decoder in **MCLauncher `1.1.28-release`, versionCode `292`**, package `de.silpion.mc2`. The reference APK SHA-256 is `5e9125bb5e618e8eb989bfff8096f09cbad5e4fd3e5b08768fd624f36efc0482`. The evidence is static Android code and isolated offline checks, not a capture from an appliance or a manufacturer firmware specification. See the [evidence ledger](research-methodology.md#evidence-ledger).

## Transport and conventions

| Property | Finding | Qualification |
|---|---|---|
| Device node | `/dev/ttyMT0` | Constructor argument in `HardwareMachineService` |
| Baud rate | 4800 | Overrides the utility's unrelated default of 921600 |
| Native mode | Raw termios; read/write descriptor | Examined JNI implementations set input/output speed |
| Complete line settings | Not fully established | Do not assert complete 8N1, stop bits, or timeout configuration |
| Electrical interface | Not established | No verified pinout, voltage, TTL/RS-232/RS-485 classification |
| Host transmit loop | Nominal 100 ms sleep | Scheduling and work add latency; not a guaranteed period |
| TX / RX length | 15 / 27 bytes | Direction is relative to the Android host |

All offsets below and in the [machine-readable description](../../../../specs/mcc/protocol_292.json) are **zero-based**. Hexadecimal bytes use two digits. Multibyte numeric fields in RX are big endian. Bytes are unsigned unless an explicit signed conversion is specified. The protocol has no identified byte escaping; `55` and `AA` may occur within fields, so delimiters alone are insufficient to frame a stream.

## Android to controller: TX

| Offset | Width | Field | Build 292 encoding |
|---:|---:|---|---|
| 0 | 1 | Start | `55` |
| 1 | 1 | Total length | `0F` = 15 |
| 2 | 1 | Message kind | `A1` |
| 3 | 1 | Operation | `00`, `01`, `03`, `04`, `05`, `0F`, `C6`; see [commands](commands.md) |
| 4 | 1 | Tare | `A9` when requested; otherwise `00` |
| 5 | 1 | Speed level | 0 through 10 |
| 6 | 1 | Temperature level | 0 through 19; lookup table below |
| 7–10 | 4 | Reserved | Written as zero by the examined serializer |
| 11 | 1 | Wire direction | `00` clockwise, `01` counterclockwise |
| 12 | 1 | Scale calibration | `00` EXIT/normal, `E6` ENTER, `E9` START |
| 13 | 1 | Checksum | Unsigned sum of offsets 0–12 modulo 256 |
| 14 | 1 | End | `AA` |

The original serializer replaces a speed outside 0–10 or temperature level outside 0–19 with zero. This toolkit's offline encoder rejects such inputs instead of silently changing them. This is an intentional API validation difference, not an additional controller restriction.

Calibration ENTER/START causes the original serializer to zero **all offsets 3–11**, including the operation, tare, speed, temperature and direction fields, before setting offset 12. Calibration is documented and decoded; the public encoder does not generate ENTER/START frames.

### Checksum and a synthetic STOP

For TX, `checksum = sum(frame[0:13]) & 0xff`. For RX, `checksum = sum(frame[0:25]) & 0xff`. The checksum byte and terminator are excluded. Addition detects many accidental changes but is not a CRC, signature, or authentication mechanism; compensating byte changes can preserve it.

```text
55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA
```

This is a **synthetic** canonical STOP, derived from the documented serializer. The initial three bytes sum to `0x105`, whose low byte is `05`. `HardwareMachineService.onStopRequested()` leaves direction unchanged: a STOP retaining counterclockwise direction may have offset 11 = `01` and checksum `06`. Do not require every STOP frame to equal the canonical example.

### Direction has three representations

| Representation | Counterclockwise | Clockwise |
|---|---:|---:|
| Android `Direction` / command interface | 0 (`LEFT`) | 1 (`RIGHT`) |
| TX offset 11 | 1 | 0 |
| RX offset 3, bit 3 | 0 | 1 |

Android also declares `NA = 2`; it is not a third physical direction. The examined service maps any Android direction other than zero to clockwise, so callers must validate input before using that interface. The toolkit accepts only its two explicit direction values.

### Temperature levels

| Level | °C | Level | °C | Level | °C | Level | °C |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0/off | 5 | 60 | 10 | 85 | 15 | 110 |
| 1 | 37 | 6 | 65 | 11 | 90 | 16 | 115 |
| 2 | 45 | 7 | 70 | 12 | 95 | 17 | 120 |
| 3 | 50 | 8 | 75 | 13 | 100 | 18 | 125 |
| 4 | 55 | 9 | 80 | 14 | 105 | 19 | 130 |

This is the Android lookup table, not permission to use an arbitrary target temperature or proof of physical accuracy. TX contains a **level**, not the degrees themselves.

## Controller to Android: RX

The envelope is `55 1B B1`, 22 data bytes, checksum at offset 25, and `AA` at offset 26. `PowerBoard.areDataCorrect()` checks non-null input, exact length, both delimiters, length byte, kind byte and checksum. The full field map is in [response fields](response-fields.md), and board-to-Android errors are in [error codes](error-codes.md).

No request identifier, sequence counter, or command-specific acknowledgment was identified in the decoded layout. A valid response is a status sample; it does not prove that a particular immediately preceding command was applied. [Timing and state](timing-and-state.md) explains the consequences for STOP verification and fragmented streams.

## Scope of a valid frame

Structural validity means that the envelope and checksum match. It does not establish plausible sensor data, supported operation semantics, current data, or safe machine behavior. Decoders should retain raw values and unknown fields even when semantic warnings apply. In particular, RX byte 24 remains unknown and must not be turned into a guessed status flag.

Continue with [command semantics](commands.md), [response fields](response-fields.md), [limitations](safety-and-limitations.md), or the [Python API](api.md).
