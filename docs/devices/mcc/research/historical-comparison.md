> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Relationship to earlier MCC research

The community had already documented the MCC serial envelope, field positions and several operations before this build 292 analysis. This project credits that groundwork and checks the examined application's behavior against it. A more precise build-specific mapping is an extension, not a claim to have discovered the protocol first.

The main historical protocol source is [EliasKotlyar/Monsieur-Cuisine-Connect-Hack, protocol.md at the recorded revision](https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack/blob/1407c35ac55c6d5e706d4e9150e541c3acb8c003/informations/protocol.md). Public API/update-path context also comes from [tuxuser/monsieurcc-rs](https://github.com/tuxuser/monsieurcc-rs) and launcher patching context from [tuxuser/monsieurcc-patch](https://github.com/tuxuser/monsieurcc-patch). These are reference-only sources; their code and documents are not vendored. See [attribution and licensing observations](../third-party-references.md).

## Comparison by topic

| Topic | Historical account | Build 292 evidence and scope |
|---|---|---|
| Frame envelope | 15-byte TX, 27-byte RX; `55` start and `AA` end | Confirmed in serializer and response validation |
| Length/kind bytes | TX `0F A1`; RX `1B B1` | Confirmed in managed-code implementation |
| Checksum | Additive low byte | Exact ranges: TX 0–12 to 13; RX 0–24 to 25 |
| Direction | TX 0 clockwise, 1 counterclockwise | Confirmed; Android interface uses inverse numeric values |
| Speed/temperature levels | Speed 0–10, temperature 0–19 | Confirmed serializer ranges, zero fallback for out-of-range input, and temperature lookup table |
| Heater-only TX | Historical `02` | Examined heater-only enum serializes as **`01`**; no distinct `02` emission established |
| `C6` | Historical description says a single turn | Build 292 uses the Turbo UI/service path; physical single-turn behavior is not established |
| `04` / `05` | Earlier protocol text leaves these unclear | Build 292 maps Toast/roasting and Knead, with corresponding extended RX states |
| Scale calibration | Historical `E6`, `E7`, `E9` ideas | Examined serializer confirms EXIT `00`, ENTER `E6`, START `E9`; ENTER/START zero fields 3–11 |
| Experimental `0A` / `E7` | Examples appear in old notes | No corresponding emission confirmed in the examined serializer; omitted from toolkit encoding |
| Response interpretation | Header/checksum established in cited protocol page | Extended field map with statuses, RPM, signed weight, scale priority, firmware field and unknown byte 24 |
| Stop guarantees | Command examples establish wire values | Host latest-state sending, stale buffer reuse and missing request ACK qualify what a STOP request proves |

The differences could reflect an older application, experimental observations, a firmware variant or uncertainty in the earlier account. The present corpus does not establish which explanation applies. The absence of an opcode in build 292's serializer does not prove that every controller rejects it, and its presence in an old note does not prove that this build uses it.

## Additional supported contributions

The build-specific work traces the complete Android command/callback chain, identifies the active 4800-baud constructor argument, separates nominal 100 ms sending from the reader's 500 ms sleep and the cooking timer's 1 s tick, and records the DEX callsite of payload construction. It documents board error to Android error translation, actual-RPM display buckets and big-endian signed weight conversion.

It also distinguishes the external updater's client contract from its missing implementation, the ordinary serial firmware-number field from an update mechanism, and Android recovery/boot images from MCU payloads. No MCU image or firmware flashing procedure was identified. Those boundaries matter as much as additional decoded fields.

The current toolkit contributes original offline byte handling, streaming recovery, synthetic scenarios and independently written tests. Its in-memory behavior does not resolve the historical physical unknowns: watchdogs, braking time, electrical settings, safe load/duty cycle, interlocks or installed-artifact identity. The [evidence ledger](research-methodology.md#evidence-ledger) and [limitations](safety-and-limitations.md) state what can actually be supported.
