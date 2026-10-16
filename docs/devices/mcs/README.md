# MCS profile research

This independent profile is scoped to the historical **mc30 1.2.14.15** host application. It keeps the canonical OB operation layouts, qualified OTA frame shapes and independent raw-level/thermal model. Use the [unified documentation](../../index.md) for current commands and API.

| Topic | Research |
|---|---|
| Envelope, active operation layouts, signed fields | [Protocol](research/en/protocol.md) |
| Architecture and application paths | [Architecture](research/en/architecture.md) |
| Evidence classes, hashes and historical comparisons | [Evidence](research/en/evidence.md), [compatibility](research/en/compatibility.md) |
| OTA and firmware unknowns | [OTA](research/en/ota.md) |
| Recipe/database structure | [Recipes](research/en/recipes.md) |
| Simulator hypotheses and limits | [Digital Twin](research/en/digital-twin.md), [limitations](research/en/limitations.md) |
| Community attribution | [References](research/en/community.md) |

The complete [historical English index](research/en/index.md) preserves the original tutorials, FAQ and glossary. Historical APIs/screenshots/test counts are marked as earlier-product material. [Current validation](../../tests.md) does not inherit old success claims merely by copying documentation.

Machine descriptions: [protocol](../../../specs/mcs/protocol.json), [evidence](../../../specs/mcs/evidence.json), [historical compatibility register](../../../specs/mcs/compatibility.json). Separate fixtures include the [900 envelope-reference inputs](../../../fixtures/mcs/envelope-reference-900.json), [900 operational encoder cases](../../../fixtures/mcs/conformance-900.json), [Android RX vectors](../../../fixtures/mcs/android-rx-vectors.json) and [synthetic telemetry](../../../fixtures/mcs/telemetry.jsonl).

The envelope reference is a historical isolated serializer comparison. The second 900-case operational corpus is separately frozen software conformance data; it is not 900 additional physical or firmware tests. No field is promoted to HARDWARE_VERIFIED.

## Retained limits

MCS raw motor levels are not RPM. A checksum/layout match does not identify the installed app version. The sequence counter skips `0x66` but does not establish ACK correlation. Synthetic interlocks, torque/dynamics, timer behavior, temperature/weight saturation and OTA replies are explicit model policies. Actual MCU image, electrical UART interface, bootloader/retry/final verification, original multistage program schedules and physical duty cycles remain unknown.
