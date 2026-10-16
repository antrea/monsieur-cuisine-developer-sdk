# Troubleshooting

## Windows blocks the generated console launcher

Some application-control policies can block pip's generated `mc-sdk.exe` with Windows error 4551. The SDK itself is Python: use the documented module entrypoint, for example `python -m monsieur_cuisine_sdk.cli --model mcc capabilities`. This does not launch that EXE or change the computer's security policy. The native desktop already starts with `python -m monsieur_cuisine_sdk`. An EXE-policy block is distinct from a Python import or protocol failure.

Start from the installed package and an explicit model. Capture the exact command, selected model, Python/JDK/Android version, message and a minimal synthetic input when reporting a problem. Keep credentials, real device identifiers and proprietary logs out of a report.

| Symptom | Check and next step |
|---|---|
| `No module named monsieur_cuisine_sdk` | From the checkout run `python -m pip install -e .` with the same interpreter used to launch it. For temporary source tests, set `PYTHONPATH=src` using your shell's syntax. |
| `mc-sdk` is not found | Activate the intended environment, or use `python -m monsieur_cuisine_sdk.cli --model mcc capabilities`. Check `python -m pip show monsieur-cuisine-developer-sdk`. |
| Tk import/display error | Run `python -m tkinter`. Install matching Tcl/Tk support or use the [headless commands](setup.md). The full current test suite requires Tk/display; Linux CI uses Xvfb. Headless API/CLI remain available. |
| CLI asks for a model | Place `--model mcc` or `--model mcs` before the command. No automatic protocol/model detection is used for actuation. |
| A valid MCS command fails RX decoding | Use `--direction tx` for command layouts. RX is the default direction for decode/inspect; MCC instead carries A1/B1 kind bytes. |
| Checksum, length or truncated-tail diagnostics | Verify the selected protocol and input format. `validate --file ...` retains recovered frames but reports unsuccessful validation for noise/corruption/tails. Do not discard the diagnostic just because a later frame was recovered. |
| Temperature/duration rejected | Inspect capabilities. MCC has no 40 °C level or duration field; MCS's exact target table/manual duration differs. Native builders use `--params`, not ignored common flags. |
| Android cannot connect | Explicitly enable Android Connection, select the same model, and match the port. The standard emulator uses `10.0.2.2`; the desktop binds loopback. Check the debug demo variant and that no other client owns the listener. |
| Bind/port-in-use error | Inspect the displayed endpoint and another local process/listener using it. Disable the old connection or choose another available loopback port in both applications. Do not change to a wildcard/LAN address. |
| Desktop START/Tare/Send HEX is disabled | A remote client owns commands. Desktop STOP disconnects it; sensor/fault injection stays available. |
| MCS receiver sees stale backlog/high traffic | Use the shared SDK's single receiving loop and bounded query cadence. The default MCS host sends query/command responses, not unsolicited periodic telemetry. Avoid adding a new query for every received frame. |
| Motion does not stop with an injected link fault | Ordinary wire STOP can be ignored by the deliberately disconnected virtual link. Clear the fault for a deliberate command, or use lifecycle disarm/new-session cleanup. Allow virtual time for finite braking. |
| Replay fails | Verify unified schema/model, complete JSON and expected bytes/checkpoints. Legacy recordings require their canonical legacy helper. A mismatch is evidence, not permission to rewrite expectations silently. |
| Recording capacity reached | Save the valid ended trace and create a new session. The common recorder reserves a terminal disarm. CLI `record` saves the ended trace and returns status 1. |
| Old scenario result appears irrelevant after a switch | Generation checks discard stale results; use Cancel and run a new experiment for the selected model. Worker results never replace a new model automatically. |
| Android build cannot locate SDK/JDK | Follow [android/README.md](../android/README.md); configure your licensed local toolchain in untracked settings. No private `local.properties` belongs in the source distribution. |
| Release audit/build refuses output | Read the actual audit issues. The builder requires an output directory outside the checkout and excludes caches/generated/private material. Fix the source or configuration rather than bypassing the audit. |

Useful isolation checks:

```sh
python -m monsieur_cuisine_sdk --headless
mc-sdk --model mcc conformance
mc-sdk --model mcs conformance --corpus envelope
python -m unittest discover -s tests -p test_cli_unified.py -v
python tools/audit_release.py --runtime
```

[Setup](setup.md), [Digital Twin guide](digital-twin.md), [CLI](cli.md), [FAQ](faq.md) and [current validation](tests.md) provide the expected behavior. For security-relevant findings use the scope in [SECURITY.md](../SECURITY.md).
