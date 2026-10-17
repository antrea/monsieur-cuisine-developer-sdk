# Changelog

## Unreleased — independent audit corrections

- Framing: one stray or missing byte no longer blacks out later commands. An MCS-looking header whose length bytes contain 0x55/0xAA is treated as noise, and MCC candidates are rejected as soon as the type byte disagrees, so STOP keeps working after line noise. Foreign-envelope quarantine is unchanged.
- MCC frames refused by the model (STOP with speed, unknown operation, out-of-range level, calibration) are reported as `rejected_command` and no longer counted as accepted; new `rejected_commands` counter.
- `set_temperature()` reissues the running command (MCC operation; MCS function, raw level, turbo lock and remaining countdown) instead of a STANDARD/manual start without timer.
- New `on_recording_full="continue"` policy; the desktop uses it, so long interactive sessions no longer stop the motor after about three minutes (MCC) or fifteen minutes (MCS).
- Desktop: status line always visible and window fitted to the screen; Protocol Monitor/Timeline keep scroll and selection and follow the newest frame; sensor injection sends only edited fields; refused/discarded input is reported.
- Release builder refuses untracked or uncommitted files when packaging from a Git checkout; linked-worktree checkouts pass the source audit.

## 0.1.0 — initial unified product

- One Python package/API, native model-selecting Digital Twin and explicit-profile offline CLI.
- Independent MCC build-292 and MCS mc30-1.2.14.15 codec/model profiles; no fabricated cross-profile RPM, ACK or timer equivalence.
- One optional localhost Android connection with command ownership, session generations, bounded queues and transport cleanup.
- One Android Studio `sdk`/`demo` project with common lifecycle and independent codecs.
- Deterministic model-explicit recordings/replay and bounded scenario/stress workflows.
- Preserved research/specifications/attributions and separate synthetic fixture corpora.
- Corrected proven baseline parser-boundary, delayed-response, recording-budget, work-control, telemetry-range and Android lifecycle issues, with focused regressions.

This version is separate from the earlier MCC and MCS toolkit version histories. See [migration](docs/migration.md), [evidence](docs/evidence.md) and [validation](docs/tests.md) for scope. No remote publication is implied by this changelog.
