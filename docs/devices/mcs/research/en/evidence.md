> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Evidence register and reproducibility

[Machine-readable register](../../../../../specs/mcs/evidence.json) records APK fingerprint, source symbols, baseline codec hash, test provenance and limitations. It contains no proprietary method body or private filesystem location. [Protocol JSON](../../../../../specs/mcs/protocol.json) and FieldSpec tables are compared by tests.

| ID | Claim | Level / scope |
|---|---|---|
| E01 | envelope, active operational layout, constants/getters | CONFIRMED_IN_APK; historical1.2.14.15 only |
| E02 | 900 seeded envelope payloads matched isolated recovered serializer | CONFIRMED_IN_APK; envelope/checksum only |
| E03 | virtual dynamics, interlocks, OTA reply policy | INFERRED; original configurable model |
| E04 | physical RPM, MCU image/ISA, electrical details, bootloader | UNKNOWN |

Baseline code is original Python written during the prior research and carried in mcs_protocol/_baseline.py. The public typed facade, telemetry encoder, stream diagnostics and tools extend it. The historical SyntheticBoard remains an internal fixture for the retained regression tests; the product twin uses independent evolving SimulationEngine/MCSVirtualPowerBoard classes.

The previous 46 tests include44 portable tests retained here and2 tests against private extracted APK/Smali facts that remain outside the public repository. The old900 comparison executed only an inspected pure serializer/checksum method in an isolated JVM, not Android or firmware. Public envelope fixtures reproduce the same seed20261016 and payload lengths. The proprietary harness and sources are not shipped or needed at runtime. Newly frozen manual/operation/OTA vectors are a separate900-case corpus, not a claim of900 more original firmware comparisons.

Run `python -m unittest discover -s tests -v`, conformance and audit from the checkout. The release audit reports actual executions and skipped/unrun work. To extend a factual claim, specify source build/hash, symbols or lawful public reference, method, expected result and uncertainty. Do not relabel model success as hardware verification. No item in this register is HARDWARE_VERIFIED.
