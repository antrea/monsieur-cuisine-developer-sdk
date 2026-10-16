# Glossary

| Term | Meaning in this SDK |
|---|---|
| MCC | Monsieur Cuisine Connect; this profile implements the examined MCLauncher build-292 host mapping. |
| MCS | Monsieur Cuisine Smart; this profile implements the examined mc30 1.2.14.15 host mapping. |
| Profile | One device's codec, capabilities, native synthetic model and unit translations. |
| Digital Twin | The independent software model and its owning development session; not a verified firmware replica. |
| PowerBoard | The controller-side concept modeled by the toolkit; its real MCU implementation remains unidentified here. |
| TX / RX | Bytes transmitted/received relative to the Android host. |
| Frame / envelope | A complete protocol message / its header, length, type/bitmap, sequence and checksum structure. |
| Codec | Code that validates, encodes and decodes one protocol's bytes. |
| Stream parser | Incremental framing across arbitrary chunks, with incomplete-tail and corruption diagnostics. |
| Checksum | The original additive modulo-256 error check; not a CRC, signature or authentication mechanism. |
| Opcode | A protocol command/message identifier; values and meanings remain profile-specific. |
| UI speed level | The application's requested speed selection, not automatically a physical velocity. |
| Raw motor level | MCS's native reported/requested motor quantity; no verified RPM conversion is supplied. |
| RPM | Revolutions per minute. MCC exposes synthetic measured RPM; its target table is illustrative. |
| Target / observation | Requested setpoint / reported or modeled measured state; they need not match during dynamics or stale telemetry. |
| Tare | A profile-specific scale operation establishing a new zero reference in the model. |
| NTC | The temperature-sensor presence concept decoded/injected by the profile; no electrical sensor model is asserted. |
| Virtual time | Explicit model time. Common API uses seconds; it does not advance merely because wall time passes in a headless API call. |
| Generation / epoch | Host lifecycle token identifying one model/connection session; it is not an added wire field. |
| Owner / lease | The one local or remote source allowed to issue commands to the shared twin. |
| Disarm | Host lifecycle policy removing targets and old transport state; it does not assert instantaneous physical stop. |
| ACK | A proven acknowledgement of a request. This SDK does not invent one from a write, MCC RX delivery or MCS sequence coincidence. |
| Sequence | MCS's independently incremented counter, skipping `0x66`; request/response correlation is not established. MCC has no invented sequence. |
| Replay / checkpoint | Re-executing known local inputs / stored deterministic state and queue expectations used for comparison. |
| OTA | Over-the-air update terminology; here only qualified MCS offline message shapes and synthetic replies, without firmware flashing. |
| JVM / ART | Host Java Virtual Machine / Android Runtime. A host JVM pass and genuine Android activity run are different tests. |
| CONFIRMED_IN_APK | A build-specific static host observation, not physical verification. |
| Synthetic / INFERRED | An explicit model choice or qualified inference; it must not be promoted to manufacturer behavior. |
| UNKNOWN | A fact the examined evidence does not establish. Unknown data remains visible rather than guessed. |

See [architecture](architecture.md), [protocols](protocols.md) and [evidence levels](evidence.md) for context.
