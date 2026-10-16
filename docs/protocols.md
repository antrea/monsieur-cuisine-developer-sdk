# Independent protocol profiles

Device selection remains explicit throughout Python, Android, framing, recordings and the desktop. A common UI does not make the two wires interchangeable.

| Property | MCC | MCS |
|---|---|---|
| Examined host build | MCLauncher 1.1.28-release / 292 | mc30 1.2.14.15 / 10214015 |
| Envelope | `55`, fixed length/type, fields, checksum, `AA` | `AA`, big-endian declared length, bitmap, subtype, sequence, payload, checksum |
| Normal command/response | TX15 / RX27 | OB TX39 (legacy TX35) / operational RX48 |
| Checksum | Sum offsets 0–12 TX, 0–24 RX, modulo 256 | Sum bytes after header through payload, excluding checksum, modulo 256 |
| Direction | Android enum inverse on TX; separate RX status bit | Native motor/direction fields; retain signed/raw interpretations |
| Speed observation | Unsigned measured RPM, display bins | Signed raw level; no verified physical RPM mapping |
| Timer | No wire duration identified | HMS timer fields; manual 0–5940 seconds |
| Firmware research | Reported version field, updater boundary unknown | Operational/OTA frame shapes; firmware validation/flashing unimplemented |
| Physical confirmation | None | None |

- [MCC research and spec index](devices/mcc/README.md), [MCC machine description](../specs/mcc/protocol_292.json).
- [MCS research and spec index](devices/mcs/README.md), [MCS machine description](../specs/mcs/protocol.json), [MCS evidence register](../specs/mcs/evidence.json).

Both specs come from build-specific static host observations plus qualified offline comparisons. Checksums are additive error checks, not CRCs or authentication. Unknown values and fields remain visible. A layout match cannot identify an appliance's installed build, controller firmware or safety behavior. UART path/baud observations are historical research; the SDK opens no physical UART.
