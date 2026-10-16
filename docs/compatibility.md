# Compatibility and Verification Scope

The SDK targets Python **3.11+** on Windows, Linux and macOS using one Python/Tk codebase. This page separates completed local/hosted evidence and device-profile compatibility. Later interpreter versions require their own verification.

| Environment | Executed verification |
|---|---|
| Windows 11, CPython 3.12.14, Tk 8.6 | Local Python API, CLI, all 97 tests, real native GUI, loopback and isolated wheel installation passed |
| GitHub-hosted Windows, Linux and macOS, CPython 3.11–3.14 | All **12 combinations passed** the source audit, 97 tests with real Tk/display, wheel build and isolated installed API/CLI/GUI verification |
| Android 30 x86_64 ART | Actual debug demo Activity controlled both profiles through the real Tk desktop, including STOP, errors and lifecycle |
| JVM / Android build | JDK 21 build, Java 17 SDK bytecode, Kotlin/JVM tests, independent packaged consumers and debug/instrumentation APK compilation passed locally |
| Physical MCC/MCS | Not tested by this simulator release; no physical UART transport or safety certification |

The [completed hosted run](https://github.com/antrea/monsieur-cuisine-developer-sdk/actions/runs/38873336351), on commit `b37d4ad`, passed all 13 jobs, including Android SDK/demo compilation, Kotlin/JVM tests and both binary client integrations. This does not imply Android instrumentation was executed on hosted CI: the ART/Activity evidence above was obtained separately. The [workflow](../.github/workflows/ci.yml), [test record](tests.md) and [release audit](../RELEASE_AUDIT.md) distinguish those scopes.

## Platform requirements

- **Windows:** Python with Tcl/Tk; no virtual COM driver is required.
- **Linux:** matching Python/Tk packages and a graphical session for the desktop. CI uses Xvfb for real widget tests; the API/CLI remain headless.
- **macOS:** a Python distribution with a compatible Tcl/Tk installation and desktop session for GUI use.
- **Android:** Android Studio/JDK/SDK are build tools for the optional project, not dependencies of the Python twin. The demo is for emulator/test use.

The Python wheel contains no platform-specific runtime extension or Python dependency. Tcl/Tk is supplied by the interpreter/platform, and optional POSIX pseudo-terminal support is platform-specific. Source paths are portable; no development-machine directory is required.

## Device and API compatibility

The MCC profile describes host build292; MCS describes mc30 version10214015. A matching packet shape does not prove compatibility with another installed app/controller firmware. Raw protocol semantics and synthetic physical policies remain separate.

Legacy pure helper imports often alias canonical modules. The public desktop/CLI/API use the unified namespace and explicit model. Recordings from older toolkit formats are not silently converted to the new schema. Read [migration](migration.md), [profiles](protocols.md) and [evidence levels](evidence.md) before extending a compatibility claim.
