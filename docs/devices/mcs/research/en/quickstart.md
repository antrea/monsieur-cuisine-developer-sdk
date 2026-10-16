> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Quick start

After [installation](installation.md), launch `python -m mcs_digital_twin`. In Motor, select speed and send a manual frame. Change target temperature in Temperature. Inject mass and tare in Scale & sensors. Errors offers response drop, corruption and delay; Protocol HEX shows the resulting bytes. Pause and +60 virtual seconds let you inspect acceleration and thermal behavior. Settings resets the session with editable model parameters and seed.

For headless development:

```sh
python -m mcs_tools build manual --params '{"speed":3,"temperature":60,"seconds":90}'
python -m mcs_tools decode aa000a024f420001fe039f --direction tx
python -m mcs_tools inspect aa000a024f420001fe039f --direction tx
python -m mcs_tools analyze fixtures/telemetry.jsonl
python -m mcs_tools telemetry fixtures/telemetry.jsonl --csv telemetry.csv
python -m mcs_tools scenario examples/reversal.json --record replay.json
python -m mcs_tools replay replay.json
python -m mcs_tools conformance --vectors fixtures/conformance-900.json
```

The JSON argument uses POSIX/PowerShell single quotes; other shells may require escaping. Help is available with `python -m mcs_tools --help` and each subcommand's `--help`. Exit codes are 0 success, 1 scenario/conformance mismatch, 2 input/file/codec error. The `telemetry --gui` option opens a native plot for imported logs. No serial port is opened.

Log format is JSON Lines: `{"time":0.2,"direction":"rx","hex":"..."}`. A line can hold a partial chunk; concatenated frames and noise are allowed. Scenarios are JSON, recordings use a separate action format; use [API](api.md) for the distinction.
