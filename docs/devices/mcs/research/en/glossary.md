> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Glossary

| Term | Meaning |
|---|---|
| MCS / MC3.0 / MC30 | Monsieur Cuisine Smart family identifiers in the studied app |
| MCC | Monsieur Cuisine Connect, a different architecture/protocol |
| PowerBoard | separate controller-side motor/heater/sensor board |
| envelope | framing around opcode and payload |
| L | frame size minus AA byte, unsigned16BE |
| OB | canonical bitmap bytes4F42 |
| sequence | 8-bit serializer counter; not proven ACK |
| packet sequence | separate16-bit OTA block field |
| raw level | MCS motor integer code, not measured RPM |
| NTC | temperature sensor reference in APK state interpretation |
| HMS | unsigned hours/minutes/seconds triplet |
| tare | subtract current injected mass from subsequent virtual readings |
| virtual clock | caller-controlled integer time, without sleeping |
| profile | historical layout compatibility, not version identification |
| synthetic | original test/model data, not captured firmware behavior |
| CONFIRMED_IN_APK | directly supported by static acquired software |
| INFERRED | chosen model policy or reasoned interpretation |
| UNKNOWN | evidence insufficient |
| HARDWARE_VERIFIED | authentic physical observations; none in this release |
