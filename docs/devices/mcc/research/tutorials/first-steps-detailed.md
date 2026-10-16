> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Detailed first steps with MCC Developer Toolkit

These examples use only public source, synthetic data and Python 3.11+. From the repository root use `python`, or consistently substitute `python3`. The native window also needs Tk: [Windows/Linux/macOS setup](../powerboard-simulator/crossplatform-quickstart.md).

## 1. Open the Digital Twin or headless path

```console
python -m mcc_digital_twin
python -m mcc_digital_twin --headless
```

The first command opens the Tkinter/ttk GUI without a browser or network ports. The second runs a JSON demonstration without importing Tk. Decoder, builder, analyzer and inspector are independent tools; they need neither the GUI nor the original APK.

## 2. Decode and inspect a STOP

```console
python -m mcc_tools decode --hex "55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA" --json
python -m mcc_tools inspect --hex "55 0F A1 00 00 00 00 00 00 00 00 00 00 05 AA"
python -m mcc_tools validate --file examples/samples.txt
```

The decoder recognizes TX, length 15, operation STOP and checksum `05`. The inspector explains every byte. `validate` checks structure and checksum; it does not certify a physically safe command. Samples are synthetic. Noise or truncated frames produce diagnostics even when other frames are recovered.

## 3. Build a synthetic packet

```console
python -m mcc_tools build --operation standard --speed 2 --direction ccw
```

The result is `55 0F A1 01 00 02 00 00 00 00 00 01 00 09 AA`. It is not transmitted. Android uses 0 for counterclockwise while wire byte 11 uses 1. The builder rejects out-of-range values and unknown opcodes; active calibration is not generated.

## 4. Observe in-memory dynamics

Save this original code in a local test file and run it from the repository root:

```python
from mcc_protocol.codec import Direction, Operation, encode_tx
from mcc_powerboard_simulator.model import PowerBoardModel

board = PowerBoardModel()
board.feed(encode_tx(Operation.STANDARD, speed=3,
                     direction=Direction.COUNTER_CLOCKWISE))
board.advance(100)
print(board.snapshot()["telemetry"]["actual_rpm"])  # 400 synthetic
board.feed(encode_tx(Operation.STOP))
print(board.snapshot()["telemetry"]["actual_rpm"])  # still 400
board.advance(100)
print(board.snapshot()["telemetry"]["actual_rpm"])  # 0 synthetic
```

The target changes immediately; measured motion changes as virtual time advances. The values follow chosen coefficients, not MCC measurements. The GUI exposes the same concepts and editable parameters; animation caps visual speed for readability.

## 5. Exercise intermittent behavior, faults and stress

```console
python -m mcc_digital_twin scenario intermittent --json
python -m mcc_digital_twin scenario wait_stop --json
python -m mcc_digital_twin scenario lid --json
python -m mcc_digital_twin stress --count 1000 --seed 292 --json
```

The sequence distinguishes SPIN, WAIT_STOP and REST. Rest begins after a new local motor-off/zero-RPM sample; an old sample does not confirm STOP. The program latches errors and lid opening and does not restart automatically when they clear. Scenarios use a model separate from the current GUI session. Stress varies synthetic configurations/events; PASS does not demonstrate a safe duty cycle for real hardware.

## 6. Record and verify replay

```console
python -m mcc_digital_twin record --file session.json
python -m mcc_digital_twin replay --file session.json
python -m mcc_tools telemetry --file examples/digital-twin-session.json --input-format recording --format csv
python -m mcc_tools analyze --file examples/samples.txt --json
```

A recording contains supported actions, expected responses and model checkpoints. Replay recreates a synthetic session and compares RX bytes and state. It does not execute firmware or scripts from JSON. Recordings provide local virtual time; a raw frame contains no timestamp. The analyzer reads data, counts operations/errors and reports corruption without controlling a device.

## 7. Run tests and optional integrations

```console
python -m unittest discover -s tests -v
python examples/powerboard_client.py --self-test
```

The client opens only an ephemeral loopback TCP endpoint to verify a synthetic start, acceleration, rotation, stop and error cycle. This optional integration is not a dependency of the desktop or headless tools. The original Kotlin example described an injectable interface for source you control, without APK patching or hidden APIs. That historical source example was not compiled/tested as an Android application in the earlier release; current Android results have their separate evidence scope.

Further reading: [complete protocol reference](../protocol/README.md), [tools/API](../developer-tools.md), [scenarios](../powerboard-simulator/scenarios.md), [fidelity](../powerboard-simulator/fidelity.md), [research limits](../safety-and-limitations.md).
