# Changelog

## 2.0.0.dev0 — local development, not published

- Read-only backup/session and bounded GPT/ext4/Android-boot/MTK image readers;
  external MCC Backup archive integrity and format adapter without GPL code import.
- Privacy-minimized partition/system-app/build inventory and userdata allocation
  metadata; separate `mc-backup verify|inventory|report`, cancellable native Backup tab.
- 9,642 plain-text OEM software-reference vectors from prior isolated build-292
  execution; provenance and intentional out-of-range serializer difference documented.
- MCC high-level OEM/strict host policy: heated/reverse caps, STANDARD minimum 1,
  program-preserving temperature changes, explicit recipe conversion and turbo entry.
- Python/Kotlin start defaults change to CW; Kotlin STANDARD commands enforce the
  same minimum/caps with an optional strict mode. Explicit raw feeds remain unadapted.
- Stable error names retained, with separate build-292 UI descriptions for board 5/6/7.
- Synthetic, configurable scale-calibration responses/progression and 10 Hz latch
  tolerance; optional virtual CookingHost for latch collapse, timers, pause, turbo and sleep.
- Read-only allowlisted ADB diagnostics and explicitly offline application plans,
  launcher transaction/rollback rehearsal. No physical installer, writer or restoration.
- Development versions distinguish these local artifacts from the published 0.1.0.


## Unreleased — independent audit corrections

- Framing: one stray or missing byte no longer blacks out later commands for good. An 0xAA immediately followed by a header byte (MCC terminator before the next `55 0F`, or a stray 0xAA before a real MCS header) is treated as noise, so STOP keeps working after line noise. Complete envelopes up to `max_frame` are still validated and discarded as one unit; only oversized declarations whose high length byte is 0x55/0xAA (≥ 21761 bytes, never documented) are no longer quarantined blindly. Other oversized declarations can still cost up to 64 KiB of input (design limit, see the audit roadmap).
- MCC frames refused by the model (STOP with speed, unknown operation, out-of-range level, calibration) are reported as `rejected_command` and no longer counted as accepted; new `rejected_commands` counter.
- `set_temperature()` reissues the running command (MCC operation; MCS function, raw level, turbo lock and remaining countdown) instead of a STANDARD/manual start without timer.
- MCS model: a command re-sending the reported countdown keeps the running deadline (repeated `set_temperature()` calls can no longer keep a timer alive); `switch_model()` after a truncated recording starts a fresh session; `new_session()` keeps `record=False`.
- New `on_recording_full="continue"` policy; the desktop uses it, so long interactive sessions no longer stop the motor after about three minutes (MCC) or fifteen minutes (MCS).
- Desktop: status line always visible and window fitted to the screen; Protocol Monitor/Timeline keep scroll and selection and follow the newest frame; sensor injection sends only edited fields; refused/discarded input is reported.
- Release builder refuses untracked or uncommitted files when packaging from a Git checkout; linked-worktree checkouts pass the source audit.
- Android connection: a client reconnecting right after the previous client's last frames is accepted instead of being closed after the TCP handshake.
- Kotlin SDK: `close()` racing `connect()` no longer leaves the transport connected; a burst of more than 128 MCC frames in one read no longer fails the session.
- `python -m mcc_tools.cli` / `mcs_tools.cli` run the unified CLI instead of exiting silently; `replay()` raises `ValueError` for every malformed recording.
- Tests: the Python RX decoders are frozen against the repository's MCC/MCS RX corpora (previously read only by Kotlin); the stress oracle no longer disappears under `python -O`; the CLI reports deeply nested JSON as an error. `docs/cli.md` no longer calls the MCS encoder corpus independent.
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
