# Validation and reproducibility

## SDK 2.0 local development verification (2026-10-18)

The `2.0.0.dev0` local branch passed **184 Python tests on each of CPython
3.11.17, 3.12.15, 3.13.16 and 3.14.8 on Windows 11**, including real Tk widgets,
the Backup tab and loopback integration. **29 Kotlin/JVM tests** passed offline;
both packaged JVM clients also passed against the actual native desktop/model.
No Android Activity/emulator or physical appliance was exercised in this phase.

The complete 57,998-record private OEM differential was re-compared with zero
mismatches; the 9,642-record public subset runs in the suite. The updated ext4
reader still matched an independent 7-Zip extraction for 1,421 regular files,
155 symlinks and 277 directories. The actual backup was re-hashed/reconstructed
successfully and inventory produced 21 partitions and 68 system app folders.
No personal userdata entries or APK internals were inspected.

The published v0.1.0 hosted results below are historical baseline evidence;
they are **not hosted CI results for this unpushed development branch**.
USB write/installation and hardware restoration are not claimed by fake-ADB or
offline rollback tests. See [USB](usb-toolkit.md), [backup](backup.md) and
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
