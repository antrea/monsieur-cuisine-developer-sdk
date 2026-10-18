# Changelog

## Unreleased — independent audit corrections

- Framing: one stray or missing byte no longer blacks out later commands for good. An 0xAA immediately followed by a header byte (MCC terminator before the next `55 0F`, or a stray 0xAA before a real MCS header) is treated as noise, so STOP keeps working after line noise. Complete envelopes up to `max_frame` are still validated and discarded as one unit; only oversized declarations whose high length byte is 0x55/0xAA (≥ 21761 bytes, never documented) are no longer quarantined blindly. Other oversized declarations can still cost up to 64 KiB of input (design limit, see the audit roadmap).
- MCC frames refused by the model (STOP with speed, unknown operation, out-of-range level, calibration) are reported as `rejected_command` and no longer counted as accepted; new `rejected_commands` counter.
- `set_temperature()` reissues the running command (MCC operation; MCS function, raw level, turbo lock and remaining countdown) instead of a STANDARD/manual start without timer.
- New `on_recording_full="continue"` policy; the desktop uses it, so long interactive sessions no longer stop the motor after about three minutes (MCC) or fifteen minutes (MCS).
- Desktop: status line always visible and window fitted to the screen; Protocol Monitor/Timeline keep scroll and selection and follow the newest frame; sensor injection sends only edited fields; refused/discarded input is reported.
- Release builder refuses untracked or uncommitted files when packaging from a Git checkout; linked-worktree checkouts pass the source audit.
- `python -m mcc_tools.cli` / `mcs_tools.cli` run the unified CLI instead of exiting silently; `replay()` raises `ValueError` for every malformed recording.
- Documentation: Windows PowerShell quoting for `--params`, setuptools prerequisite for the release builder, Android fragment/idle timeouts, per-profile lid/NTC/error behavior, current publication state.

## 0.1.0 — initial unified product

- One Python package/API, native model-selecting Digital Twin and explicit-profile offline CLI.
- Independent MCC build-292 and MCS mc30-1.2.14.15 codec/model profiles; no fabricated cross-profile RPM, ACK or timer equivalence.
- One optional localhost Android connection with command ownership, session generations, bounded queues and transport cleanup.
- One Android Studio `sdk`/`demo` project with common lifecycle and independent codecs.
- Deterministic model-explicit recordings/replay and bounded scenario/stress workflows.
- Preserved research/specifications/attributions and separate synthetic fixture corpora.
- Corrected proven baseline parser-boundary, delayed-response, recording-budget, work-control, telemetry-range and Android lifecycle issues, with focused regressions.

This version is separate from the earlier MCC and MCS toolkit version histories. See [migration](docs/migration.md), [evidence](docs/evidence.md) and [validation](docs/tests.md) for scope. Version 0.1.0 was published as a GitHub release on 2026-10-16.
