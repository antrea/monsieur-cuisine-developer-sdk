# Monsieur Cuisine Developer SDK 0.1.0

**Initial Unified Release**

One offline SDK and native Digital Twin for Monsieur Cuisine Connect and Smart, from the independent BlackStuffLabs project. This product starts at 0.1.0; it does not continue either predecessor toolkit's 0.2.0 version history.

## Included

- One explicit-model Python API, native Tk desktop and `mc-sdk` CLI.
- Independent MCC build-292 and MCS mc30-1.2.14.15 codecs, capabilities and synthetic models, with separate specifications and frozen corpora.
- One optional loopback Android connection sharing the desktop's model and command owner, with bounded queues, generations and deterministic cleanup.
- One Android Studio `sdk`/`demo` project with common client/lifecycle behavior and independent wire delegates.
- Model-explicit recording/replay, bounded scenarios/stress, sensor/fault injection, protocol inspection and CSV telemetry with explicit units.
- Current English product guides, secondary Italian introduction, preserved historical device research, original MIT credits and included third-party notices.

## Correctness work

Migration fixes include interrupted-stream analysis, delayed RX crossing client boundaries, recorder/reader budget agreement, imported simulation-work limits, cancellation, telemetry saturation/tare state and Android queue/session/write-copy behavior. Independent shared tests additionally cover foreign-envelope quarantine, fractional work accounting, replay preflight, observer reentrancy, model-switch isolation and MCS query amplification/UI backlog. See the [release audit](RELEASE_AUDIT.md) for evidence and scope.

## Verification snapshot

The current public Python suite passed **97 tests** on Windows/Python 3.12.14/Tk 8.6, including actual Tk/loopback integration. All 16 shared scenarios passed for both models; seeded stress passed **1000 cases / 48000 events per model**, with zero failures.

Android verification includes **24 JVM tests**, **3020 Python/Kotlin byte comparisons with zero mismatches**, APK compilation, independent packaged consumers on JVM/ART and both actual demo activities controlling the same model shown by the real Tk window. The additional MCS unsolicited-telemetry runtime regression passed. These are separate checks, not hardware validation. Full details and baseline/migration counts are in [testing](docs/tests.md) and [RELEASE_AUDIT.md](RELEASE_AUDIT.md).

The full current test suite requires Tk/display; the library/CLI work headlessly. Windows, Linux and macOS CI results are tracked by the [real SDK workflow](https://github.com/antrea/monsieur-cuisine-developer-sdk/actions/workflows/ci.yml). See the [compatibility record](docs/compatibility.md) for completed environments; a workflow configuration alone is not a successful run.

## Compatibility and limits

Use `python -m monsieur_cuisine_sdk` for the desktop and `mc-sdk --model mcc|mcs ...` for tools. Common time is virtual seconds. MCC modeled RPM and MCS raw motor levels remain distinct; MCS `actual_rpm` is unavailable. MCC has no invented query/duration field and rejects unsupported temperatures. Error/OTA/timer semantics remain profile-specific.

Many pure legacy imports alias canonical modules; old desktop/server processes and every historical CLI flag are not preserved as parallel products. New shared recordings use a distinct model-explicit schema. Read [migration](docs/migration.md) before reusing an older integration or recording.

No physical UART driver, OEM APK patch, firmware flasher, manufacturer recipe importer or hardware-safety claim is included. Dynamics/interlocks and firmware defaults are synthetic policies. Source remains independent of the named vendors.

Start with the [README](README.md), [Digital Twin guide](docs/digital-twin.md), [API](docs/api.md), [FAQ](docs/faq.md) and [troubleshooting](docs/troubleshooting.md). [Release preparation/publication](docs/releasing.md) documents future authorized distribution; [MIT](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md) preserve attribution. [Support BlackStuffLabs on Ko-fi](https://ko-fi.com/blackstufflabs).
