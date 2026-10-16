> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Developer tools and public APIs

All commands below work on local/synthetic data without a robot. Python3.11+ and the standard library are sufficient. Source execution works from the repository root; an optional installation adds `mcc-tools` as a console command. `mcc_protocol` is independently usable without importing the Digital Twin or Tkinter.

| Tool | CLI | Reusable module / purpose |
| --- | --- | --- |
| Protocol Decoder | `python -m mcc_tools decode --file examples/samples.txt --json` | `mcc_protocol.codec.decode_frame`, `StreamParser` |
| Packet Builder | `python -m mcc_tools build --operation standard --speed 3 --direction ccw` | `mcc_protocol.codec.encode_tx`; synthetic bytes only |
| Serial Log Analyzer | `python -m mcc_tools analyze --file examples/samples.txt --json` | `mcc_tools.analyzer.analyze_file`, `analyze_chunks`, `analyze_recording` |
| Protocol Inspector | `python -m mcc_tools inspect --hex "55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA"` | `mcc_tools.inspector.inspect_frame`; every byte with offset, width, raw value and meaning |
| Telemetry Viewer | `python -m mcc_tools telemetry --file examples/digital-twin-session.json --input-format recording --format csv` | `LogAnalysis.telemetry()`; native GUI additionally plots RPM and displays live virtual sensors |
| Scenario Runner | `python -m mcc_tools scenario intermittent --json` | `run_scenario(name,seed=...,config=...)`; separate deterministic model |
| Replay Tool | `python -m mcc_tools replay --file examples/digital-twin-session.json` | `replay_recording`; verifies every expected RX byte and state checkpoint |
| Test Harness | `python -m unittest discover -s tests -v` | Independent protocol, transport, model, tool, controller and GUI tests |

The aliases `decode`, `build` and `validate` delegate to the same protocol CLI; `scenario`, `replay` and `stress` delegate to the same model CLI. They do not create a parallel implementation. Standalone protocol API details are in [api.md](api.md); Digital Twin API details are [here](powerboard-simulator/api.md).

## Log inputs and diagnostics

`--input-format hex` is the default. It accepts ASCII-whitespace-separated or compact hexadecimal bytes, `#` comments and frames split across lines at byte boundaries. Arbitrary timestamp prefixes and terminal log decorations are not inferred; normalize them to raw byte columns first. `--input-format binary` reads a local binary stream. Neither opens a serial port.

`--input-format recording` reads the public synthetic `mcc-powerboard-recording-v1` JSON format. It examines recorded inputs/expected responses without executing their operations. TX fragments cannot cross recorded input resets or virtual disconnects; offline input is reported as ignored. An RX supplied as a command is diagnosed separately from observed RX responses. Corrupt responses remain diagnostics.

The report includes counts, operation frequencies, flagged board errors, min/max RPM/temperature/signed weight, semantic warning counts, decoded frames and parser issues. It does not infer a missed hardware command, actual sampling interval or motor safety. Raw wire frames contain **no timestamp**. `observed_ms` is present only when a synthetic recording supplies local virtual metadata; it is `null` for raw streams.

`telemetry` offers `--format table`, `json` or `csv` (`--json` also selects JSON). CSV can be redirected to a local file with ordinary shell redirection. It includes requested/measured RPM and temperature, signed weight, direction, lid, motor/heater, board/Android errors and firmware. The GUI provides a graphical view of the same model's live state; no plotting package is required.

`analyze` and `telemetry` return status0 when at least one structurally valid frame exists and there are no corruption/truncation/input issues, otherwise2. Semantic warnings stay visible in reports. `inspect` validates one complete frame and preserves warnings; it does not authorize physical use. Replay returns0 on a match,1 on a well-formed expectation mismatch,2 on invalid input. See [first steps](tutorials/first-steps.md) for a working end-to-end memory example.
