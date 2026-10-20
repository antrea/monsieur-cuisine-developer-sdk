# Validation and reproducibility

## Offline software batch (2026-10-20)

The suite grew to **287 Python tests** with the virtual host presets, service
callbacks, scale display, LED model and the explicit output discard. It passed
on CPython 3.13 (build environment with the optional extras, one symlink skip)
and on CPython 3.11, 3.12 and 3.14 (base interpreters, three skips: symbolic
links need a privilege this user lacks, and the pyserial/capstone extras were
not installed). Every host rule added in this batch is a static reading of the
decompiled build-292 app; none was executed on Android or on an appliance, and
the twin's board responses remain synthetic. Windows only; hosted jobs for this
branch have not run.

## SDK 2.0 completion development verification (2026-10-18)

The latest complete local suite passed **265 Python tests in 102.928 seconds on
CPython 3.13/Windows**, including actual Tk widgets, backup/recovery file flows,
ADB transaction fault models and real pyserial software loopback. The earlier
184-test checkpoint passed on Python 3.11–3.14; that older matrix is not a final
cross-platform verification of all subsequent changes. This branch is still
`2.0.0.dev0`, unpushed and not a completed SDK 2.0 release.
All **29 Kotlin/JVM tests** were also executed again, with zero failures; the
normal API23 demo/debug-instrumentation outputs were rebuilt after the dedicated
consent fixture build. Build/lint for Manager, its instrumentation and oemprobe
passed locally. Remote hosted jobs for this branch have not run.

The independent build-292 DEX was executed directly on API23 ART: **57,998
codec/conversion comparisons, zero disagreements**, repeated with the updated
probe APK. The 9,642-record public subset also runs in the offline suite. A
separate actual original x86 JNI execution verified software PTY open and
invalid-baud rejection. Its original close failed due to the missing `mFd`
field and that failure was reproduced; it is not a passing native-close test.
See [OEM execution and provenance](oem-conformance.md).

Real API23 emulator tests cover both demo Activities communicating with Tk,
actual APK installation/list/start, persistent HOME selection and rollback,
same-UID debug-app updates with data/SQLite/preferences/keystore continuity and
interrupted recovery. Manager's normal SAF → PackageInstaller UI flow now covers
cancel, required consent, successful installation and restoration of the source
permission setting through system UI. These are ordinary app operations on an
emulator; the root-forced adbd and emulator SELinux domain do not prove the
privilege policy of a physical MCC. Mock ADB tests remain internal regressions,
separate from these actual Android runs.

The actual owner's backup was imported through Tk, materialized as a new
15,634,268,160-byte image, compared across 21 partitions and checked through the
original external file verifier. The ext4 reader's earlier independent 7-Zip
comparison covered 1,421 regular files, 155 symlinks and 277 directories.
Original APK internals, platform/updater configuration and native libraries have
also been analyzed privately; no OEM bytes or personal backup data are shipped.

The published v0.1.0 hosted results below are historical baseline evidence,
**not hosted CI results for this unpushed development branch**. Full final
packaging, consolidated conformance coverage and acceptance remain open. No
physical UART, robot actuation, eMMC restore or hardware safety result is claimed.
See [USB](usb-toolkit.md), [backup](backup.md), [recovery](recovery.md) and
[host evidence levels](mcc-oem-policy.md).

After an editable install, run from the repository root:

```sh
python -m unittest discover -s tests -v
mc-sdk --model mcc conformance
mc-sdk --model mcs conformance
mc-sdk --model mcs conformance --corpus envelope
python -m monsieur_cuisine_sdk --headless
```

The Android project has separate JVM, packaged-consumer, APK and instrumentation checks; see [its README](../android/README.md). An APK build, JVM connection test, genuine emulator run and real appliance test are different evidence classes.

## Verification record

Local development verification uses Windows, CPython 3.12.14, Tk 8.6 and a separate Java/Android toolchain. The [completed hosted run](https://github.com/antrea/monsieur-cuisine-developer-sdk/actions/runs/38873336351), on commit `b37d4ad`, additionally passed **all 12 Windows/Linux/macOS and Python 3.11–3.14 combinations** and the Android build/JVM job. Each Python job ran the source audit, all 97 tests with a real display, and an isolated wheel installation with actual API/CLI/GUI checks. Hosted Android checks compile instrumentation but do not execute an emulator. POSIX PTY integration remains unrun locally and is not covered by that unified suite. The [release audit](../RELEASE_AUDIT.md) records separate historical/runtime evidence and limits.

| Check | Completed result and scope |
|---|---|
| Current public unified Python suite | **97 tests passed**, including actual Tk and loopback integration |
| Shared acceptance coverage | Connected MCC→MCS→MCC and inverse transitions; all 16 common scenarios for both models with replay; fresh subprocess prohibits socket creation and Tk import for headless use |
| Frozen MCC baseline before migration | **266 tests total: 263 passed, three POSIX PTY skips**; both native Tk tests passed |
| Frozen MCS baseline before migration | 114 tests passed, including 12 real Tk and 12 TCP tests |
| MCC original core suite through canonical aliases | **201 tests total: 198 passed, three POSIX PTY skips**; includes 1000 seeded streams / 48000 actions |
| New MCC adapter/audit regressions | 12 passed: atomic sensors, fractional clock, profile units, finite disarm, aliases and proven baseline fixes |
| Unified CLI tests | 14 passed: both profile bytes, unsupported options, streams, recordings/replay, capacity trace preservation, expected corruption visibility, CSV units, scenarios and all frozen conformance corpora |
| Unified Android host JVM suite | 24 passed: six MCC codec, seven MCS codec, eleven shared client/transport/queue checks, including unsolicited-frame query cadence |
| Unified packaged JVM consumer | Java 17 consumer compiled using packaged SDK plus Kotlin stdlib and exercised both models |
| Independent Android consumer | Separate Android project used the packaged SDK JAR plus Kotlin stdlib, without source/project references; **two genuine ART runtime tests passed**, exercising both models |
| Python/Kotlin differential | 3020 byte cases, zero mismatches; same two independent profile formats |
| Unified Android packaging | Debug, unsigned release and test APK builds completed; this alone is not an emulator claim |
| Actual Android activity / native Tk integration | Final MCC and MCS activity runs passed against the same unified Tk model, including motion, host-injected error, lifecycle/disconnect and record/replay; both host-JVM integrations also passed |
| MCS unsolicited-frame runtime regression | Genuine Android activity passed with additional 50 ms unsolicited telemetry; query throttling/UI coalescing prevents amplification/backlog |
| Final common stress | MCC **1000/1000** and MCS **1000/1000** passed with seed 292, **48000 events per model**, zero failures |
| Current runnable examples | Three scripts executed for each profile: headless, record/replay and byte inspection; all six invocations returned 0 |

Counts are individual completed checks, not a sum to advertise as one unified suite. Full integration tests and platform-dependent skips are visible in the actual invocation output. Native-desktop/Android runtime evidence identifies the tested build, runtime, actions and results separately; no device hardware verification is claimed here.

## Meaningful regression areas

Tests cover both wire corpora, signed fields, field tables, corrupted/truncated streams, selected-profile rejection, finite dynamics, timer partitioning, transactional sensors, model-switch isolation, response faults, ownership, bounded queues/recordings, replay tampering, shutdown/reconnect and native Tk controls. MCC analyzer reset-boundary and old TCP delayed-response defects have narrow reproductions. MCS work/tick budgets, cancellation, telemetry saturation and scale-state derivation have profile-specific regressions.

The full current public suite requires working Tk and a graphical display; its shared GUI/acceptance tests do not silently skip when these are missing. Linux CI uses Xvfb. Native GUI cases run in fresh processes, matching the desktop entry point and avoiding repeated Cocoa/Tk interpreter lifetimes in a shared process. Failed assertions, crashes and timeouts propagate to the suite. Socket acceptance waits for actual bounded readiness rather than assuming that a fixed number of polls completes a round trip on every platform. The headless API/CLI and targeted non-GUI tests do not require Tk. The retained historical POSIX PTY tests were skipped on Windows and remain unexecuted here. Historical screenshots in the research archive depict earlier products; current README screenshots come from the unified application.

Fixtures are synthetic, separately stored under `fixtures/mcc` and `fixtures/mcs`. The MCS 900-envelope and 900-operational corpora have distinct provenance. Tests do not need an OEM APK, firmware, external account, serial port or remote service. Record any future physical test separately with lawful provenance and an explicit safety scope.
