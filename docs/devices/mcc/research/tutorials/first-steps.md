> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# First steps: protocol to dynamic telemetry

Start in the extracted repository with Python3.11+. No installation or Internet connection is needed once Python is available. For the native GUI, [install/check Tcl/Tk](../powerboard-simulator/crossplatform-quickstart.md), then run `python -m mcc_digital_twin`. Use `python3` on systems that require it. [Detailed tutorial](first-steps-detailed.md).

## Decode and build independently

```console
python -m mcc_protocol decode --file examples/samples.txt --json
python -m mcc_tools build --operation standard --speed 2 --direction ccw
python -m mcc_tools inspect --hex "55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA"
```

The decoder shows a signed weight of−100 and firmware value4924 in the synthetic RX fixture. The builder produces bytes only, without opening a transport. Android CCW0 becomes wire direction1. A sum checksum checks framing integrity; it neither authenticates data nor proves the age or execution of a command.

## Control the same engine used by the desktop

Run the complete example:

```console
python examples/digital_twin_memory.py
```

Its essential API is:

```python
from mcc_protocol.codec import Direction, Operation, decode_frame, encode_tx
from mcc_powerboard_simulator.model import PhysicsConfig, PowerBoardModel

board = PowerBoardModel(PhysicsConfig(acceleration_rpm_s=4000))
responses = board.feed(encode_tx(Operation.STANDARD, speed=3,
                                direction=Direction.CLOCKWISE))
assert decode_frame(responses[-1]).actual_rpm == 0
board.advance(100)
assert decode_frame(board.sample()[-1]).actual_rpm == 400
board.feed(encode_tx(Operation.STOP))
board.advance(1000)
assert decode_frame(board.sample()[-1]).actual_rpm == 0
```

The model preserves internal motion and temperature between calls. `advance` uses virtual milliseconds and never sleeps. Finite acceleration, braking, target-RPM points and thermal rates are selected software hypotheses. They are not measurements of the appliance. The full example also reverses direction, changes heat, injects signed weight/lid/error/firmware and checks the resulting binary telemetry.

## Intermittent programs and fault handling

```console
python -m mcc_digital_twin scenario intermittent --json
python -m mcc_digital_twin scenario wait_stop --json
python -m mcc_digital_twin scenario lid --json
python -m mcc_digital_twin stress --count 1000 --seed 292 --json
```

These scenarios test virtual software behavior, including waiting for a new zero-RPM observation before rest/restart, late timers and latched errors. The local observation is not a command-correlated ACK. See [scenario descriptions](../powerboard-simulator/scenarios.md) and [original timing limits](../timing-and-state.md).

## Record, replay and inspect telemetry

```console
python -m mcc_digital_twin replay --file examples/digital-twin-session.json
python -m mcc_tools analyze --file examples/digital-twin-session.json --input-format recording --json
python -m mcc_tools telemetry --file examples/digital-twin-session.json --input-format recording --format table
python -m unittest discover -s tests -v
```

To create a new deterministic example recording, use `python -m mcc_digital_twin record --file session.json`; native session controls can save a live interactive session as well. Recordings contain supported model inputs and expected responses/checkpoints, never executable code. Only changes through the recording facade are replayable.

For external software, `python examples/powerboard_client.py --self-test` explicitly starts an ephemeral loopback TCP endpoint and demonstrates the complete binary cycle. This optional transport is independent of normal desktop use. An Android source project can inject the [original mock seam](../../../../../examples/headless.py); the example is not a patched APK or a replacement proprietary Binder service.
