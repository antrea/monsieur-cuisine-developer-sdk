# Evidence, audit scope and provenance

The unified SDK consolidates independently implemented MCC and MCS profiles after separate baseline audits. It preserves build-specific wire facts and separates them from model hypotheses. Public source contains original implementation, factual field descriptions, explanatory prose and synthetic data. No OEM APK, decompiled method body, firmware image, proprietary recipe/media corpus, private key or authenticated device log is distributed.

## Evidence classes

| Class | What it supports |
|---|---|
| Static host observation / CONFIRMED_IN_APK | Specific serializer/getter/layout behavior in the hash-identified host build |
| Isolated offline execution | Agreement with an inspected serializer representation or independent byte fixture; no Android/MCU execution implied |
| Synthetic implementation check | Determinism, validation, queue/lifecycle behavior and chosen model dynamics |
| Historical reference | Attributed earlier research with its own stated limitations |
| INFERRED / model policy | Finite motor/thermal dynamics, interlocks, firmware identifiers, saturation and OTA reply choices |
| UNKNOWN | Physical RPM mapping where absent, firmware implementation, watchdog, bootloader/electrical details or duty cycles not established |

No item is labeled HARDWARE_VERIFIED. A model response is an observation, not a physical ACK. Cached host state and later RX do not establish a causal request match when the wire lacks that guarantee.

## MCC research identity

- Host: `de.silpion.mc2`, `1.1.28-release`, versionCode 292.
- APK SHA-256: `5e9125bb5e618e8eb989bfff8096f09cbad5e4fd3e5b08768fd624f36efc0482`.
- Anchors: `PowerBoard.getSendPayload`, `areDataCorrect`, response getters and `HardwareMachineService` command/loop paths.
- Exact fields, derived-file fingerprints, DEX code-unit callsites and representation limits remain in the [research methodology](devices/mcc/research/research-methodology.md) and [machine specification](../specs/mcc/protocol_292.json).
- Eight representative public TX vectors retain their isolated-JVM provenance. Earlier research counts of 2560 inputs / 29739 assertions describe that earlier investigation, not newly added public hardware tests.

## MCS research identity

- Host: `com.tecpal.device.mc30`, `1.2.14.15`, versionCode 10214015.
- APK SHA-256: `6ad1e58869eb4287a6f8b0fa0cb931941fe527e8e4b661f2f86fc005548518ef`.
- Anchors: `MultoSerialPortCommand`, `MCCommandSetting.pickStruct`, active `multo.structs.OperationStruct` and qualified legacy/OTA serializers.
- [Evidence register](../specs/mcs/evidence.json), [protocol](../specs/mcs/protocol.json) and [retained research](devices/mcs/research/en/evidence.md) preserve scope.
- The 900 seeded random envelope cases match the previously inspected isolated serializer inputs. The separate 900 manual/operation/OTA cases are frozen implementation conformance, not an additional 900 OEM or MCU comparisons. Two earlier private-source tests are not distributed or counted as public checks.

## Baseline audit and migration corrections

Before migration, independent local audits ran both complete Python suites, both JVM suites and available native Tk/TCP paths from verified source copies. MCC's 138 and MCS's 137 source files matched the baseline manifests. Original project trees remained read-only. The old release-audit filenames referenced by some historical documents are replaced here with actual audit scope and the [executed validation record](tests.md), rather than empty placeholder files or inherited publication claims.

Proven corrections carried into the unified implementation include:

- MCC analyzer cannot splice a command across `reset_transport`; legacy client cleanup discards pending RX; recorder/replay budgets match before mutation.
- MCS workload/timing preflight and cancellation constrain imported tasks; telemetry saturation and scale-state updates preserve wire validity; shared ownership and lifecycle replace the old independent desktop worker.
- Android uses one bounded dispatcher/client lifecycle, copied writes and generation isolation; STOP invalidates older queued starts; the demo has an explicit simulator connection policy.
- Shared lifecycle isolates model generations, clears fragments/queues and removes targets on disconnect; the common recorder captures explicit model selection and compares deterministic checkpoints.

The [test guide](tests.md) supplies reproduction commands and completed counts. A passing software audit does not claim zero remaining bugs, portability on unexecuted systems, newer-build compatibility or hardware safety. The product version is **0.1.0**, independent of both former 0.2.0 toolkit releases. This initial technical verification predates publication; subsequent hosted execution is reported separately in [compatibility](compatibility.md).

## Attribution and reproducibility

[MCC public references](devices/mcc/third-party-references.md) and [MCS community references](devices/mcs/research/en/community.md) retain revision/context/license observations. They are dated research attribution, not current availability or permission to copy third-party source. [Third-party notices](../THIRD_PARTY_NOTICES.md) cover included wrapper material and external tool terms. Researchers extending a claim should record exact build/hash, source symbol, method, expected bytes, evidence class and uncertainty, while keeping excluded proprietary material out of the source tree.
