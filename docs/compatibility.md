# Compatibility and Verification Scope

The SDK targets Python **3.11+** on Windows, Linux and macOS using one Python/Tk codebase. A target is not the same as an executed result. This page separates local evidence, prepared CI and device-profile compatibility.

| Environment | Executed verification |
|---|---|
| Windows 11, CPython 3.12.14, Tk 8.6 | Local Python API, CLI, all 97 tests, real native GUI, loopback and isolated wheel installation passed |
| Linux and macOS | GitHub Actions matrix prepared; see the workflow results for actual execution. No local result is inferred from configuration |
| Python 3.11, 3.13 and 3.14 | Included in the hosted matrix; local checks above used 3.12.14 |
| Android 30 x86_64 ART | Actual debug demo Activity controlled both profiles through the real Tk desktop, including STOP, errors and lifecycle |
| JVM / Android build | JDK 21 build, Java 17 SDK bytecode, Kotlin/JVM tests, independent packaged consumers and debug/instrumentation APK compilation passed locally |
| Physical MCC/MCS | Not tested by this simulator release; no physical UART transport or safety certification |

The [workflow](../.github/workflows/ci.yml) runs Windows/Linux/macOS across Python 3.11–3.14. A pending or failed run is not platform verification. The [test record](tests.md) and [release audit](../RELEASE_AUDIT.md) identify completed checks.

## Platform requirements

- **Windows:** Python with Tcl/Tk; no virtual COM driver is required.
- **Linux:** matching Python/Tk packages and a graphical session for the desktop. CI uses Xvfb for real widget tests; the API/CLI remain headless.
- **macOS:** a Python distribution with a compatible Tcl/Tk installation and desktop session for GUI use.
- **Android:** Android Studio/JDK/SDK are build tools for the optional project, not dependencies of the Python twin. The demo is for emulator/test use.

The Python wheel contains no platform-specific runtime extension or Python dependency. Tcl/Tk is supplied by the interpreter/platform, and optional POSIX pseudo-terminal support is platform-specific. Source paths are portable; no development-machine directory is required.

## Device and API compatibility

The MCC profile describes host build292; MCS describes mc30 version10214015. A matching packet shape does not prove compatibility with another installed app/controller firmware. Raw protocol semantics and synthetic physical policies remain separate.

Legacy pure helper imports often alias canonical modules. The public desktop/CLI/API use the unified namespace and explicit model. Recordings from older toolkit formats are not silently converted to the new schema. Read [migration](migration.md), [profiles](protocols.md) and [evidence levels](evidence.md) before extending a compatibility claim.
