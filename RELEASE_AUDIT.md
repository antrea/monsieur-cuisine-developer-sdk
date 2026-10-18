# Release audit — unified SDK 0.1.0

## SDK 2.0 local development checkpoint — 2026-10-18

This branch is `2.0.0.dev0`, not a published SDK 2.0 release. The following is
the **previous checkpoint**, before the in-progress completion extension.
The extension adds explicit serial transport, actual API 23 ADB transactions,
native Toolkit panels and [direct OEM ART execution](docs/oem-conformance.md).
Final completion gates remain open. Previous checkpoint verification:
184 Python tests passed on each of Python 3.11–3.14/Windows; 29 Kotlin/JVM tests
passed; both JVM clients exercised the same native Tk/model instance. Backup
integrity/reconstruction and privacy-minimized inventory were exercised on the
owner's local files. The full 57,998-vector software comparison and independent
1,421-file ext4 comparison passed. Public fixture data is plain JSONL under the
existing text allowlist; no compressed-binary exception was added.

The read-only Backup tab/CLI and external format adapter are implemented. USB
diagnostics have fake-ADB tests; application/launcher rollback is an offline
transaction model, with no device writer. Firmware restoration, hardware
interlocks and the MCU implementation remain unverified. Current details are in
[architecture](ARCHITECTURE.md), [tests](docs/tests.md), [backup](docs/backup.md)
and [MCC host policy](docs/mcc-oem-policy.md). The v0.1.0 record below is retained
as historical provenance; no remote operation was performed for this branch.

Audit date: 2026-10-16. **Pre-publication technical verification snapshot.**
This initial unified product has its own version history, separate from the two
predecessor 0.2.0 toolkits. Results below describe the current unified source.

This document retains the local audit evidence from unification. Subsequent
publication checks and actual hosted runs are identified in [testing](docs/tests.md)
and [compatibility](docs/compatibility.md). The [SDK workflow](https://github.com/antrea/monsieur-cuisine-developer-sdk/actions/workflows/ci.yml)
provides the live GitHub result; configuration alone is not a PASS.

Publication verification on 2026-10-16: the [completed hosted run](https://github.com/antrea/monsieur-cuisine-developer-sdk/actions/runs/38873336351)
passed all 13 jobs: 12 Windows/Linux/macOS and Python 3.11–3.14 combinations,
plus Android compilation, JVM tests and both binary client integrations. A fresh
anonymous remote clone also passed all 97 tests and a separate installed-wheel
API/CLI/GUI check. Public source and all reachable commit metadata/content were
reviewed for private development details. Build logs remain outside distribution.

## Verification actually performed

| Check | Result and scope |
|---|---|
| Immutable MCC baseline | 266 Python tests: 263 passed, 3 POSIX-only skips; real Tk checks ran. Separate Kotlin baseline: 13 tests passed; debug/release APK builds succeeded. |
| Immutable MCS baseline | 114 Python tests passed, including Tk/TCP. Frozen 900-case conformance reproduced. Separate Kotlin baseline: 10 tests passed; debug/release APK builds succeeded. |
| Unified public Python suite | 97 tests passed on Windows 11, CPython 3.12.14, Tk 8.6. Includes real Tk widgets, loopback sockets, CLI subprocesses, both connected roundtrip model-switch sequences and library use with socket creation forbidden. |
| Retained historical coverage | 201 selected MCC core tests: 198 passed, 3 POSIX skips; 82 selected MCS headless tests passed against canonical modules/aliases. These are additional migration checks, not part of the 97-case public suite. |
| Scenarios and stress | All 16 shared scenarios passed for each model, including deterministic replay. Seed 292 stress: 1,000 cases and 48,000 reported events per model, zero failures. |
| Unified Kotlin | 24 JUnit tests passed; SDK JAR and source JAR built; debug, unsigned release and instrumentation APKs compiled. |
| Python/Kotlin differential | 3,020 cases, zero mismatches: MCC 440 TX + 456 RX; MCS 924 TX + 1,200 RX. Synthetic and frozen software-reference data; no robot capture claim. |
| Independent consumers | Java 17 consumer compiled and ran with the packaged SDK JAR. A separate Android application imported that JAR as a file dependency, compiled and ran both profiles on Android ART. Neither consumer included SDK sources. |
| Real Android Activity integration | Android 30 x86_64 emulator; final demo Activity controls drove the same model instance shown by the real Tk desktop. MCC and MCS passed START, speed change, telemetry, STOP, injected error, disconnect/reconnect disarmed, model selection/switch and background cleanup. Saved traces replayed exactly. |
| Optional unsolicited MCS telemetry | A further actual Activity/Tk run with synthetic status pushed every 50 ms passed. Host JVM/Tk runs also passed for both models; these are distinguished from ART runs. |
| Documentation/examples | All six example invocations passed. English primary documentation, parallel device chapters, 79 historical research documents retained with historical banners. Relative links, heading fragments and private-path checks passed before packaging. |
| Packaging gates | The release builder selects audited source, creates a deterministic source ZIP and separate manifest, and can build/install the wheel in a new isolated environment outside the checkout. Exported Android artifacts are generated SDK/demo code only. See the external release manifests and installed-wheel verification supplied with the candidate. |

The independent common-implementation review added 31 of the public regression
tests. The author-independent profile review also compared canonical codecs with
the baseline sources; Android and release tooling were reviewed separately.

## Findings corrected

Baseline corrections include interrupted-stream analysis, recorder/reader quota
agreement, delayed responses crossing clients, bounded imported simulation work,
GUI worker cancellation, MCS sensor representability and tare state, opaque
unknown MCS subtypes, finite parser parameters, Android command queues, session
epochs, copied writes and debug-only demo connection policy.

During unification, an independent adversarial test found that a corrupt foreign
MCS envelope could expose a nested MCC START during resynchronization. The
selected-model framer now quarantines the foreign envelope before scanning its
payload. A further boundary probe found that oversized foreign envelopes needed
the same protection: a bounded three-byte header and remaining-byte counter now
discard the complete declared payload without allocating it. The counter is
reset at session boundaries, included in replay checkpoints and subject to the
normal partial-frame timeout. Regression tests cover valid/corrupt envelopes,
oversized wire lengths, fragmentation and a subsequent separate local command.
Other fixed integration findings include
fractional work-budget accounting, late-invalid replay preflight, closed Tk worker
retention, observer callback reentrancy and MCS query amplification under push
telemetry. No established P0 or P1 finding remains open in the tested scope.

## Reproduction

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
mc-sdk --model mcc conformance
mc-sdk --model mcs conformance --corpus envelope
mc-sdk --model mcc stress --count 1000
mc-sdk --model mcs stress --count 1000
python -m monsieur_cuisine_sdk --model mcc --smoke-test
python -m monsieur_cuisine_sdk --model mcs --smoke-test
python tools/audit_release.py
```

Tk tests need a display; on headless Linux use Xvfb as configured in CI. Android
build and emulator reproduction are documented in [the Android project](android/README.md)
and [Android integration](docs/android.md). The optional E2E tool requires explicit
emulator/adb settings and does not install APKs or select physical devices.

## Distribution and license review

The public source contains independent MIT code, synthetic corpora, research
documentation, real screenshots of the independent applications and the official
Gradle wrapper with Apache notices and pinned hashes. Toolchains, caches, private
reports, keys, OEM APKs, decompiled implementations, firmware and vendor databases
are excluded. The generated debug APK contains the new demo and its dependency
license assets; it is not a manufacturer application. Heuristic scans complement
manual review and do not constitute legal certification.

## Explicit limits and remaining verification

- Windows 11 / Python 3.12.14 / Tk 8.6 and Android 30 ART were executed locally.
  Hosted Windows/Linux/macOS across Python 3.11–3.14 subsequently passed as
  recorded above. Hosted Android instrumentation/emulator execution and POSIX
  PTY integration are outside that result.
- Runtime Python dependencies are empty; the desktop requires platform Tcl/Tk.
  Source setup covers all three operating systems. Android builds resolve their
  separately licensed tools/dependencies; the built twin and demo run offline.
- Physics, interlocks, delay/loss policies and sensor evolution are synthetic.
  MCC modeled RPM is not a measured motor curve. MCS physical RPM is unknown;
  raw motor levels remain explicit. Unknown/partial OTA structures remain offline
  codec research, without a flashing implementation.
- No physical UART driver or real-device automatic connection is supplied.
  Status frames are observations, not proof of execution or invented ACKs.
  A simulator PASS does not certify physical appliance safety.
- The initial unification audit performed no publication or replacement of either
  predecessor repository. The subsequent publication mandate has a separate
  verification record; these historical checks do not imply a release-signing or
  hardware result.

See [testing](docs/tests.md), [evidence levels](docs/evidence.md),
[migration](docs/migration.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
