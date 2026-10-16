> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# MCC Digital Twin: Windows quick start

This retained Windows-specific guide supplements the primary [cross-platform guide](crossplatform-quickstart.md). Use Python 3.11+ source execution with Tkinter/ttk for the native desktop. No browser, APK, device connection, ADB, virtual COM driver, EXE or installer is needed. Examples assume PowerShell is in the directory containing the extracted repository folder.

## Check the interpreter and source directory

```powershell
Set-Location .\mcc-developer-toolkit
python --version
python -m mcc_digital_twin
```

Use Python 3.11 or newer. If your system exposes the interpreter as `py` or `python3`, substitute that executable consistently. Source execution works directly from the repository root; the simulator and shared codec are bundled together.

This opens the native window in one process without network listeners. If Tk is missing, use the matching Python installation's Tcl/Tk option; `python -m tkinter` checks it. `python -m mcc_digital_twin --headless` works without Tk.

## Optional raw protocol TCP

```powershell
python -m mcc_powerboard_simulator serve
```

Leave this terminal running. Raw MCC byte clients use `127.0.0.1:8766`. No HTTP server or browser frontend is included. The standalone TCP model and an ordinarily launched desktop window are independent.

In the native desktop, select a low synthetic speed, observe requested/actual RPM, issue STOP and inspect finite deceleration. Its sensor and fault controls inject synthetic states; all physics parameters are unmeasured examples. See [fidelity](fidelity.md).

Ctrl+C in the TCP terminal shuts down the optional listener. This stops a development process; no physical machine is connected.

## Try raw protocol bytes from a second terminal

From the same repository directory:

```powershell
python examples/powerboard_client.py
python examples/powerboard_client.py --self-test
```

The external client checks synthetic start, acceleration, rotation and finite STOP, printing observed RX in JSON. `--port` selects another loopback TCP port. `--self-test` additionally injects/clears an error through Python API calls and uses an ephemeral endpoint with explicit virtual time, independent of a running `serve` process. Fault injection is not part of the original UART commands. TCP fragmentation is handled; RX remains status rather than a per-command ACK.

The server accepts one raw TCP client at a time. Close another client before running this example. Response faults configured through the Python API can cause expected timeouts; use a fresh default model for the normal example.

## Run reproducible headless checks

Stop the server if it is no longer needed; these commands do not require it:

```powershell
python -m mcc_powerboard_simulator scenario start_stop --json
python -m mcc_powerboard_simulator stress --count 1000 --seed 292 --json
python -m mcc_powerboard_simulator record --file session.json
python -m mcc_powerboard_simulator replay --file session.json
python -m unittest discover -s tests -v
```

The scenario and stress runner use virtual milliseconds, so they do not wait through the modeled physical duration. Software checks do not establish real braking time, watchdog behavior or safe repeated-start frequency.

For an interactive recording, start `python -m mcc_powerboard_simulator serve --record-file interactive-session.json` and close it with Ctrl+C when finished. Replay the saved local JSON with `python -m mcc_powerboard_simulator replay --file interactive-session.json`. A matching replay checks recorded RX bytes and model checkpoints; it does not validate against a physical robot.

## Common setup problems

| Symptom | Check |
|---|---|
| `No module named mcc_powerboard_simulator` | Run from the extracted repository root, or install that same public source package into the interpreter you are using. |
| Address/port already in use | Stop another simulator instance or consult `python -m mcc_powerboard_simulator serve --help` for its port options. |
| TCP client cannot connect | Keep `serve` running and use the exact `127.0.0.1` address/port printed by it. |
| Raw client is closed immediately | Check for another active TCP client; only one is supported. |
| No RX or a checksum error | Check whether intentional response loss, delay, disconnect or corruption is enabled. |
| RPM does not change in direct Python API use | Explicitly call `.advance(delta_ms)`; standalone model/server APIs have no automatic clock. |

Optional installation uses the toolkit's normal setuptools build backend; it may require obtaining that build dependency if absent. It is not necessary for source execution. For the API and integration seam see [API](api.md), the [Python client](../../../../../examples/headless.py) and [Kotlin mock](../../../../../examples/headless.py).
