> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Cross-platform quick start

MCC Developer Toolkit is a Python 3.11+ source package. The native Digital Twin uses Tkinter/ttk; the decoder, tools and headless model do not need Tk. No executable bundle or platform-specific launcher is distributed.

## Start from the extracted source

Open a terminal in the extracted repository root and check your interpreter:

```console
python --version
python -m mcc_digital_twin
```

Use `python3` consistently if needed. The default command opens the native GUI without a browser or network listeners. Optional source installation is `python -m pip install .`; its distribution name is `mcc-developer-toolkit`. Running from the source tree needs no installation or additional runtime packages.

## Tk on each operating system

| Platform | Interpreter/Tk setup |
|---|---|
| Windows | A standard Python.org installation can include Tcl/Tk support. If missing, modify that installation to include its Tcl/Tk option, then use the same interpreter. An embedded/minimal Python runtime may omit Tk. |
| Linux | Install the Tk binding matching your interpreter through your distribution if absent. Debian/Ubuntu commonly package it as `python3-tk`; Fedora-family distributions use `python3-tkinter`. Package names for other distributions/versions may differ. |
| macOS | Use a Python distribution with matching Tcl/Tk support, such as the Python.org installer, or a Homebrew Python with its matching `python-tk@3.x` formula. Select the version matching the interpreter; do not mix installations. |

`python -m tkinter` is the standard small Tk installation check: it should open a test window. A graphical desktop/display is required. No COM driver or appliance software is required. The toolkit does not install Python, Tk, package-manager software or drivers automatically. See [Python's Tkinter documentation](https://docs.python.org/3/library/tkinter.html), [Python Windows installation documentation](https://docs.python.org/3/using/windows.html), [Ubuntu python3-tk](https://packages.ubuntu.com/noble/python3-tk), [Fedora python3-tkinter](https://packages.fedoraproject.org/pkgs/python3.14/python3-tkinter/index.html) and [Homebrew Tk formula](https://formulae.brew.sh/formula/python-tk@3.13) for distributor information; choose your installed Python/distribution version rather than assuming the linked example version.

## Headless use and first checks

```console
python -m mcc_digital_twin --headless
python -m mcc_tools decode --file examples/samples.txt --json
python -m mcc_tools build --operation standard --speed 2 --direction ccw
python -m mcc_digital_twin scenario intermittent --json
python -m mcc_digital_twin record --file session.json
python -m mcc_digital_twin replay --file session.json
python -m unittest discover -s tests -v
```

These operations require no display, browser or listener. Samples and generated sessions are synthetic. A missing Tk installation affects the GUI, not the independent protocol decoder or headless tools. Display/PTY-dependent tests can skip where unavailable; local test reports and any not-yet-run remote CI must remain distinct.

## Optional local transport

```console
python -m mcc_powerboard_simulator serve
python examples/powerboard_client.py --self-test
```

`serve` explicitly starts optional raw TCP at `127.0.0.1:8766`; it is not required for the native desktop. No HTTP server or browser frontend is included. The client self-test creates its own ephemeral loopback endpoint and injects errors through Python API calls. No real serial port or robot is contacted. See [API](api.md), [desktop controls](desktop.md), [virtual serial](virtual-serial.md) and [fidelity](fidelity.md).

For decoder, builder, dynamics and replay exercises, follow the [detailed first-steps tutorial](../tutorials/first-steps-detailed.md).
