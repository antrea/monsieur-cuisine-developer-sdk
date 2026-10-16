# Quick Command Reference

Run these commands after installing from the source checkout with `python -m pip install -e .`. Use `python3` when required by your platform. The CLI requires an explicit device model and opens no network endpoint.

Every `mc-sdk ...` command also works as `python -m monsieur_cuisine_sdk.cli ...`. Use that normal Python entrypoint when a script directory is absent from PATH or a managed Windows policy blocks pip's generated console launcher; no system policy change is needed.

| Task | Command |
|---|---|
| Launch the desktop | `python -m monsieur_cuisine_sdk` |
| Launch with MCS initially selected | `python -m monsieur_cuisine_sdk --model mcs` |
| Check both models without a display | `python -m monsieur_cuisine_sdk --headless` |
| Show CLI help | `mc-sdk --help` |
| Show command-specific help | `mc-sdk --model mcc build --help` |
| Show MCC capabilities | `mc-sdk --model mcc capabilities` |
| Show MCS capabilities | `mc-sdk --model mcs capabilities` |
| Build a motor command | `mc-sdk --model mcc build start --speed 2 --direction ccw --temperature 60` |
| Build a STOP | `mc-sdk --model mcs build stop` |
| Decode a complete MCC STOP | `mc-sdk --model mcc decode --hex "55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA"` |
| Inspect the same frame | `mc-sdk --model mcc inspect --hex "55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA"` |
| Run a deterministic scenario | `mc-sdk --model mcs scenario start_stop` |
| Run seeded stress | `mc-sdk --model mcc stress --count 1000 --seed 292` |
| Run MCC conformance | `mc-sdk --model mcc conformance` |
| Run MCS conformance | `mc-sdk --model mcs conformance` |
| Check MCS envelope corpus | `mc-sdk --model mcs conformance --corpus envelope` |
| Record a synthetic session | `mc-sdk --model mcs record --file session.json --seconds 1` |
| Verify that session | `mc-sdk --model mcs replay session.json` |
| Run the full source suite | `python -m unittest discover -s tests -v` |

Recording writes a local file. Run it in a directory where you want that output; replay requires the recording's initial model to match `--model`. Full tests need Tk/display; Linux can use `xvfb-run -a` before the test command.

MCS TX decoding additionally needs `--direction tx`; its default decode direction is RX. MCC's A1/B1 type identifies its layout. Build output is bytes represented in JSON; it does not send commands to a robot. See the [complete CLI reference](cli.md) for files, CSV telemetry, native parameters, bounds and errors.
