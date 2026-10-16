> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Synthetic scenarios, stress and replay

These experiments exercise **MCC Digital Twin / MCC PowerBoard Simulator**, one component of MCC Developer Toolkit, with explicit virtual time. The primary desktop starts with `python -m mcc_digital_twin`; the commands below are headless equivalents and require neither Tk nor listeners. No appliance is connected. A scenario PASS means its software expectations held under chosen parameters; it does not indicate real-hardware validation.

## Scenario catalog

```console
python -m mcc_powerboard_simulator scenario start_stop --json
```

| Name | What its checks cover |
|---|---|
| `start_stop` | Acceleration is finite, STOP preserves motion initially, and sufficient virtual deceleration eventually reaches zero. |
| `directions` | A reversal initially reports the old moving direction, passes through zero and subsequently accelerates in the opposite direction. |
| `intermittent` | Multiple spin phases, WAIT_STOP and REST occur; the total deadline ends the session and the model subsequently decelerates to zero. |
| `wait_stop` | WAIT_STOP persists while RPM is positive, then a post-STOP zero observation permits REST without an extra START. |
| `partial_corrupt` | A partial TX does not actuate; its completion is accepted; corrupt input is logged and a following valid STOP is recovered. |
| `stale` | A delayed RX retains earlier RPM even though the current model is already moving; the wire has no receive timestamp. |
| `disconnect` | A STOP sent through a virtually disconnected link is not delivered; an explicit STOP after reconnect is required in this hypothesis. |
| `response_loss` | Every-second-response loss and every-third-response corruption follow deterministic attempted-response counters. |
| `lid` | The independent session program latches a lid-open event, requests STOP and does not restart after the injected lid state clears. |
| `error` | The program latches a board-error event and does not restart when it clears. This is program logic, not emulated firmware protection. |
| `stop_phases` | Explicit user STOP is terminal from SPIN, WAIT_STOP and REST, with no additional automatic spin. |
| `late_timer` | A late callback beyond the total deadline finishes the session without catch-up STARTs. |
| `interrupted` | Stale-link failure terminates the program; reconnect does not restart it or falsely establish that the disconnected STOP reached the model. |

Some named scenario fixtures intentionally choose different rates from the interactive default so checks have convenient deterministic boundaries. Those rates are still synthetic. `run_scenario(name, *, seed=292, config=None)` accepts an optional validated `PhysicsConfig` and returns `synthetic`, `name`, `seed`, boolean `PASS`/`passed`, named boolean `checks`, model `log` and `final_state`; some include `program_log`.

An exception or failed check is a failed software experiment, not a hidden successful result. Inspect the named checks and final state rather than inferring success from frame validity alone.

## Seeded stress

```console
python -m mcc_powerboard_simulator stress --count 1000 --seed 292 --json
```

`run_stress(count=1000, seed=292)` generates a distinct seeded configuration/event stream for each case. Each case has 48 events drawn from commands, STOPs, sensor changes, fault configuration, sampling, fragmented commands and virtual-time advancement. Acceleration/deceleration/coasting/thermal coefficients vary across cases.

The checks include finite/bounded velocity, consistency of direction and RPM magnitude, integer telemetry ranges, target-table consistency and eventual zero after an explicit delivered STOP with sufficient virtual time. Generated commands are low-level format tests; they are not recommendations for allowed application operating combinations.

The compact result has `count`, integer `passed` and `failed`, boolean `PASS`, `failures` with case seeds/details, total `events`, `valid_responses` and `corrupt_responses`. Expected injected checksum corruption is counted separately; it is not automatically a failed model invariant. Reuse the seed and case index to investigate a failure. Stress success does not establish physical duty-cycle safety.

## Raw external-client cycle

Start `serve`, then run:

```console
python examples/powerboard_client.py
```

The external client connects to `127.0.0.1:8766` and observes intermediate acceleration, target-speed rotation, finite STOP deceleration and zero RPM. `--port` selects another loopback TCP port. The server clock must be advancing with default fault controls. External mode does not inject errors through the original wire protocol; use the self-contained run below for the full error cycle.

For a reproducible self-contained run:

```console
python examples/powerboard_client.py --self-test
```

This starts an ephemeral loopback TCP server, explicitly advances virtual time between ordinary TX requests, and injects errors through the in-process API. It does not invent a UART clock/error-injection command. The resulting JSON reports observed phases, raw RX data and `passed`. Neither mode correlates a response to a particular request or contacts an appliance.

## Record and replay

```console
python -m mcc_powerboard_simulator record --file session.json
python -m mcc_powerboard_simulator replay --file session.json
python -m mcc_powerboard_simulator serve --record-file interactive-session.json
```

The headless record command creates an original synthetic full-cycle recording. The interactive option saves supported model calls, responses and state on clean shutdown. Replay checks supported local JSON inputs, RX byte equality and state checkpoints against a new model. It is a determinism check, not a playback of proprietary firmware or a real-device capture.

Use the recording facade for mutations that must be replayable; direct writes into a model's controller are outside that event contract. When interpreting a mismatch, first check configuration, recorded event order and whether an unrecorded mutation occurred. See the [API](api.md) and [fidelity matrix](fidelity.md).
