# Roadmap and verification gaps

Version 0.1.0 is the initial unified product: one Python API/CLI/desktop, one optional Android connection, one Android SDK/demo project, independent MCC/MCS profiles, deterministic replay and preserved research. Shipped behavior and completed checks are in the [release notes](../RELEASE_NOTES.md) and [release audit](../RELEASE_AUDIT.md).

The items below are priorities, not promised delivery dates or claims of work already verified.

## Engineering priorities

1. **Execute the prepared platform matrix.** CI is configured for Windows, Ubuntu and macOS with Python 3.11–3.14, display support and isolated installed-wheel checks. Local verification covered Windows/Python 3.12.14; hosted CI and the additional environments still need actual runs when a remote is authorized.
2. **Broaden lifecycle and workload regressions.** Preserve the existing connected model-switch, cancellation, quota, observer, STOP-priority and unsolicited-frame tests while adding independent adversarial cases. Keep diagnostic and UI queues bounded.
3. **Exercise native portability.** Validate POSIX PTY behavior on a POSIX host and test Tk packaging, DPI, keyboard navigation and accessibility on each supported desktop platform. A Windows screenshot is not cross-platform visual verification.
4. **Evolve common scenario/recording tooling carefully.** Improve scenario authoring and large-session workflows with explicit schemas, compatibility readers and resource budgets. Preserve model selection, units and byte/checkpoint comparison rather than silently converting legacy formats.
5. **Repeat packaged-consumer/runtime checks per release.** Build from frozen audited source, install outside the checkout, and exercise the packaged SDK on JVM/ART plus both actual demo/profile paths. Keep build success separate from runtime evidence.

## Research questions

| Area | Current boundary |
|---|---|
| Physical motor behavior | MCC targets/rates are illustrative; MCS physical RPM mapping and both devices' real braking/duty cycles remain unverified. |
| MCU/firmware | Controller identity/image/implementation, watchdog and bootloader behavior are not established. |
| UART hardware | Historical host path/baud observations do not establish electrical levels, pinout or complete line settings. |
| Safety/interlocks | Synthetic host/model policies do not certify physical lid, temperature or fault interlocks. |
| MCS OTA | Qualified shapes exist; firmware validation, retry/success meaning and flashing remain unimplemented or unknown. |
| Additional builds | A compatible frame does not identify the installed app version. New profiles require build/hash-specific evidence. |

These are evidence gaps, not coding TODOs to fill with guessed values. Any future physical research or hardware transport needs its own explicit scope, lawful artifacts and separate validation. Automatic appliance discovery, OEM binary patching, manufacturer recipe redistribution and a firmware flasher are not implicit deliverables of this roadmap.

Contributors should follow [evidence requirements](evidence.md), [attribution/notices](../THIRD_PARTY_NOTICES.md), [CONTRIBUTING](../CONTRIBUTING.md) and [safety limits](safety.md). Publication/signing remain separate from preparing a local candidate; see [releasing](releasing.md).
