> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# OTA structures and firmware research

Wire shapes below are **CONFIRMED_IN_APK**; no controller updater was run.

| Opcode | TX total / payload | RX total / payload | Shape |
|---|---|---|---|
| FE01 | 27 / 18 | 12 / 3 | TX CMD+metadata16; RX CMD+return8 |
| FE02 | 269 / 260 | 13 / 4 | TX CMD+packet-seq16BE+data256; RX CMD+packet-seq16BE |
| FE03 | 11 / 2 | 28 / 19 | TX CMD; RX CMD+return8+metadata16 |
| FE04 | 11 / 2 | 12 / 3 | TX CMD; RX CMD+return8 |
| FE05 | no documented generator | 14 / 5 | RX CMD+return8+version16BE |
| FE06 | 11 / 2 | 14 / 5 | TX CMD; RX CMD+return8+version16BE |


FE01 initializes metadata; FE02 transfers a 256-byte block (short inputs zero padded); FE03 requests information; FE04 confirms; FE05 is a result response; FE06 queries version. The APK helper named getOTATQueryVersion selects the FE05 registry but emits FE06; use actual wire opcode. Packet sequence is a separate 16-bit big-endian field, independent of the 8-bit envelope sequence.

Metadata is four opaque 4-byte blocks named fileLength, versionNumber, packetKey and crcValue. Their internal endianness, key meaning, firmware checksum algorithm, image format, bootloader, retries, recovery and final verification are **UNKNOWN**. The names are not enough to implement flashing. The toolkit serializes shapes offline and includes no device transport, firmware file loader or flasher.

The virtual board echoes metadata and packet sequence, returns synthetic byte 0 on documented return fields and virtual version1. This only tests response layout; zero is not a proven success code. It does not execute, decrypt, store or verify firmware. FE05 TX is explicitly unsupported. Errors in a real updater cannot be predicted with this model.

Static Android update chain: checker → manifest → downloader → SHA256 file comparison → privileged APK installer or Discovery SystemService/RecoverySystem for Android image. App, Android image, MCU/ESP metadata and recipe synchronization are distinct channels. A field named sha256Signature is compared as a file hash, not proof of a separate digital signature. Original firmware/update packages are not distributed. The serial FE family is separate from installing an Android APK.

The historical compatibility response listed MCU3069; this is not a measured robot version or acquired MCU image. No MCU model/ISA or original motor/heater firmware was identified. MT8167 and SPM288 describe Android-side evidence; DS28C36 identifies a security service/chip reference, not the motor MCU. A reported V2.19.1 was not acquired as an APK and is outside the supported profile. No current device-specific server query or authentication is required by this package.
