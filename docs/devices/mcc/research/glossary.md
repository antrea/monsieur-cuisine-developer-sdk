> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Glossary

| Term | Meaning in this project |
|---|---|
| ACK | Acknowledgment correlated to a request. None was identified for an individual UART command. A valid status sample is not automatically an ACK. |
| Android direction | Interface values 0 counterclockwise / 1 clockwise; distinct from the wire encoding. |
| APK | Android application package. The examined launcher APK is not distributed with the toolkit. |
| Artifact | A specific input file identified by hash, not just a product/version label. |
| Baud | Serial symbol rate. Build 292 selects 4800; this does not establish voltage or complete line settings. |
| BE / big endian | Most significant byte first in a multibyte number. |
| Binder | Android IPC used between app/service processes and external OEM components. Transaction numbers are not serial opcodes. |
| Board code | Raw error byte reported at RX offset 5, distinct from the Android internal error code. |
| Calibration | Scale calibration states documented in this protocol; not MCU firmware programming. |
| CCW / CW | Counterclockwise / clockwise. |
| Checksum | Here, unsigned byte sum modulo 256. It is not a cryptographic signature or a firmware-verification scheme. |
| Code unit | A DEX instruction addressing unit. A method-relative code-unit offset is not an APK byte offset or Java line number. |
| CookingStep / CookingUnit | Android step/sequence models. `CookingUnit` contains a cyclic step list and overall time. |
| DEX | Android executable bytecode container; the reference APK has one `classes.dex`. |
| Firmware number | An unsigned value read from RX offsets 20–21; not the APK version or custom Android build label. |
| Freshness | Evidence about when a frame was actually received. Re-reading an unchanged cached byte array does not create freshness. |
| Generation | Locally assigned event/sample counter for distinguishing observations; none was identified as a wire field. |
| greenDAO | Persistence library used by the launcher; its `Recipes` database schema version is 9. |
| HAL | Hardware abstraction layer. `PowerBoard` holds/encodes command state and decodes response state. |
| Interlock | A constraint preventing unsafe actuation. Visible UI checks do not prove the hardware implementation or full failure behavior. |
| IPC | Interprocess communication; Binder in the examined Android paths. |
| JNI | Java Native Interface; used here for serial descriptor and termios operations. |
| Latch | Preserve a fault/event until handled or session termination, so a later normal sample cannot erase it. |
| MCC | Silvercrest Monsieur Cuisine Connect, the subject of this build-specific research. Not an assertion of compatibility with other Monsieur Cuisine models. |
| MCLauncher | The `de.silpion.mc2` application examined as build 292. |
| MCU | Microcontroller. The powerboard MCU model, firmware image and watchdog were not identified. |
| MCUpdater | External Android package `de.silpion.mcupdater`; its client interface, not its full application, was examined. |
| Monotonic clock | Elapsed-time clock unaffected by wall-clock corrections; suitable for deadlines, but not a real-time scheduling guarantee. |
| NTC | Negative-temperature-coefficient thermistor. The protocol exposes a bowl-NTC detection bit. |
| Opcode | Operation value at TX offset 3. Tare and calibration occupy separate fields. |
| Powerboard | Board beyond the Android UART boundary that reports motor/heater/sensor state. |
| Raw field | A byte/value preserved without substituting a speculative interpretation. RX byte 24 remains raw and unknown. |
| RX / TX | Receive/transmit from the Android host's perspective: RX 27 bytes, TX 15 bytes. |
| Serializer | Converts current command state to the TX byte representation. |
| Signed weight | RX weight is a two's-complement 32-bit big-endian number; negative values are preserved. |
| Smali | Human-readable representation of DEX instructions used to check misleading decompiled Java. |
| Synthetic | Constructed for a test or simulator; not captured or measured on a robot. |
| UART | Serial transport used by the application. Its node name does not establish the electrical standard or pinout. |
| Watchdog | Mechanism reacting to missing activity/data. The controller's behavior was not established by the APK. |
| Wire direction | TX offset 11 uses 0 clockwise / 1 counterclockwise; RX status bit 3 instead sets 1 for clockwise. |

Start with the [documentation index](index.md) or the [serial specification](serial-protocol-v292.md).
