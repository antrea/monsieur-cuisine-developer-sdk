# Setup

Use Python **3.11 or newer**. Core simulation and CLI use the standard library and do not require Android, a browser, a serial driver or a hardware connection.

From the checkout:

```sh
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` in PowerShell, `.venv\Scripts\activate.bat` in Command Prompt, or `source .venv/bin/activate` in a POSIX shell. Then:

```sh
python -m pip install -e .
python -m monsieur_cuisine_sdk
```

The package installs `mc-sdk` and `monsieur-cuisine-digital-twin`. `python -m monsieur_cuisine_sdk.cli --model mcc capabilities` also works when a shell does not find the script entrypoint.

## Native desktop

Test Tk with `python -m tkinter`. On Windows, use an interpreter distribution containing Tcl/Tk. On macOS, use a Python distribution with a working matching Tk installation. Linux commonly packages Tk separately; install the distribution's Python Tk package (often `python3-tk`). A graphical display is needed for the window and real GUI tests. A headless machine can run:

```sh
python -m monsieur_cuisine_sdk --headless
mc-sdk --model mcs scenario start_stop
```

The full current `python -m unittest discover -s tests -v` suite requires Tk and an available graphical display; its shared GUI/acceptance tests do not silently skip without them. Prepared Linux CI uses Xvfb. Headless API/CLI checks remain usable without Tk. Virtual serial memory and localhost TCP adapters work on Windows; POSIX pseudo-terminal integration is platform-specific, and no virtual Windows COM driver is supplied.

## Android

The optional [`android`](../android/README.md) project has one `sdk` and one `demo` module. Android Studio/Gradle obtain their normal external dependencies; none is required by the Python runtime. Use the checked-in official wrapper, preserving its notices. The standard Android emulator reaches the host loopback bridge at `10.0.2.2`. Explicitly enable Android Connection in the desktop and select the same device model in both applications.

## Source checkout and tests

An editable install makes the `src` layout importable. Alternatively, set `PYTHONPATH=src` for a temporary source-only test run using your shell's syntax. Run commands from the repository root. No installation step downloads an OEM application or firmware.
