> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Installation

Use a Python 3.11+ environment. From the repository root:

```sh
python -m venv .venv
# Activate using your platform's normal venv command, then:
python -m pip install -e .
python -c "import mcs_protocol, mcs_digital_twin"
python -m mcs_digital_twin --headless
python -m mcs_digital_twin
```

Windows activation is `.venv\Scripts\Activate.ps1`; POSIX shells use `. .venv/bin/activate`. Activation is optional if you invoke that environment's Python directly. No administrator rights or global package changes are needed. `python3` is interchangeable when it selects the intended interpreter.

Runtime dependencies: Python standard library only. Build dependency: setuptools >=77 (PEP 517). Pip may download the build backend during installation; offline installation requires a locally available setuptools backend, for example `python -m pip install --no-build-isolation -e .` in an environment already containing it. Installed operation is completely offline.

For the desktop, verify `python -m tkinter`. Some Linux distributions distribute Tk separately as a system package; obtain it through your normal administrator-managed Python installation. Headless functions do not import Tk and can run without a display. On remote Linux, GUI tests need a display or Xvfb; otherwise they are reported as skipped. An ordinary Python source installation is the supported distribution, with no EXE required.

```sh
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
python -m unittest discover -s tests -v
```

Run tests from the source checkout; examples and documentation are repository resources, not installed package data. Wheel users can use all runtime CLI features and the built-in demo without these files. [Compatibility](compatibility.md) distinguishes tested platforms from CI targets.
