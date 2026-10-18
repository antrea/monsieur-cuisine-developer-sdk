# Protocol fixture corpora

- [OEM software-reference vectors](oem/README.md): 9,642 input/output cases from
  isolated build-292 bytecode execution, kept separate from synthetic corpora.

- `mcc/golden_tx_292.json`: eight representative TX inputs with isolated-JVM serializer provenance. Frames are synthetic.
- `mcs/envelope-reference-900.json`: 900 seeded envelope inputs at six payload lengths; arbitrary payloads need not be operationally meaningful.
- `mcs/conformance-900.json`: a distinct 900-case manual/operation/OTA software encoder corpus.
- `mcs/android-rx-vectors.json`: synthetic complete/signed RX cases for Kotlin/Python agreement.
- `mcs/telemetry.jsonl`: synthetic bidirectional observation log.

The installed CLI includes matching JSON byte corpora in package resources so conformance also works outside the checkout. No OEM capture, APK, firmware, proprietary recipe or device identity is included. [Evidence](../docs/evidence.md) describes the different comparison scopes.
