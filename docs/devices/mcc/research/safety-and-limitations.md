> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Safety boundaries and limits of the evidence

MCC Protocol Toolkit decodes local data, constructs offline test frames and runs synthetic in-memory simulations. The native Digital Twin desktop starts no network service. Optional loopback TCP and virtual serial interfaces are developer tools connected only to the synthetic model. There is no physical serial-port opener, ADB integration, installer or flasher. The research did not contact the robot. Static facts about build 292 and deterministic software tests do **not** certify a motor, heater or physical interlock.

## What is established and what remains open

| Topic | Established by the examined material | Remaining uncertainty |
|---|---|---|
| Artifact identity | A specific public APK is hash-identified and versioned | Byte-for-byte identity with any installed device build |
| TX/RX format | Serializer/decoder layouts, sum checksums and mappings | Unrecognized firmware variants or unsupported controller behaviors |
| Command delivery | Android assigns command state and periodically writes frames | No identified per-command ACK or delivery guarantee |
| Telemetry | Validity checks and field conversions | No original receive age/generation; cached samples can be reused |
| Closely spaced STOP/START | Both requests can update the same current state | A distinct STOP frame or braking interval is not guaranteed |
| Serial writes | Write/flush with logged `IOException` | Complete error propagation to cooking UI is absent in the examined path |
| MCU firmware | No payload or flasher identified in the examined corpus | MCU model, code, watchdog, bootloader, flash layout and hidden/encrypted copies |
| Physical stopping | Motor-enabled and RPM telemetry exist | Braking delay, latency and safe reversal dead time |
| Repeated starts | Android can schedule cyclic configurations | Allowable mechanical/thermal duty cycle, minimum rest and safe load |
| Interlocks | Lid/NTC bits, errors and UI callbacks are visible | Electrical/hardware interlock implementation and failure behavior |
| UART setup | Device node, baud, raw configuration | Complete line settings, voltage, pinout and electrical classification |
| Updater | Client Binder interface and state names | Missing updater implementation, install checks and rollback |

“No MCU firmware identified” is a bounded research result. It is deliberately weaker than “the APK cannot contain any firmware” or “the board cannot be updated.” See [MCUpdater and firmware](mcupdater-and-firmware.md).

## Application limits worth preserving

The original Android validation restricts heated operation to speed 3, manual reverse operation to speed 3, and cold clockwise operation to speed 10. Kneading has a specific reverse exception to 4. High speed with actual temperature ≥60 °C triggers thermal-warning logic. Speeds above 6 have a maximum duration of 15 minutes; lower speeds have 99 minutes, with tighter preset limits. Heating off does not mean that the bowl is cold.

Turbo is gated by state, temperature, direction, step permissions and lid conditions. The original lid-open callback requests pause/stop, but the reviewed PLAY path requests start before the subsequent UI check. This ordering is a reason to validate preconditions before each simulated start; it is not permission to bypass the original machine's protections.

The presence of an Android constant such as `NO_BOWL_DETECTED` does not prove it is assigned in the examined sensor mapping. The bowl NTC bit has a getter without a demonstrated complete application interlock chain. Physical safeguards may be implemented elsewhere; their absence or sufficiency is not inferred.

## What the simulator proves

Tests can show that a byte decoder handles signed weight correctly, that a checksum rejects particular mutations, or that a session model refuses a restart after a synthetic lid event. They can also expose scheduling bugs, stale-frame acceptance and failure to latch events. Those are useful software properties.

The simulator's motor/temperature changes are chosen state transitions. They are not measured acceleration, braking, thermal capacity, load behavior or a controller watchdog. A synthetic STOP followed by zero RPM is not evidence about an appliance's ability to stop safely. The simulated firmware number is a fixture, not a detected board identity.

The additive checksum does not authenticate a frame or firmware. Valid input may still contain implausible or unsupported field values. Structural parse success and semantic warnings remain separate, and unknown fields remain raw.

## Scope of this release

No functions disable interlocks, expand hardware limits, implement unknown opcodes or enter scale calibration. Calibration states are documented and decoded only. The low-level offline encoder validates the supported field ranges; it is not a full reimplementation of Android UI safety policy. The intermittent model adds explicit software guards for its own synthetic scenarios.

Any future physical integration would require separate evidence for the installed build, transport freshness, stop observations, error propagation, safe loads, interlocks, controller loss-of-link behavior and a validated recovery route. Those requirements have not been satisfied by this release and no installation procedure is provided.

For the provenance behind these limits see [research methodology](research-methodology.md); for the original timing mechanisms see [timing and state](timing-and-state.md).
