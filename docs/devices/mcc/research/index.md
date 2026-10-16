> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Documentation index

The specification is scoped to MCLauncher build 292. All public examples are synthetic and the toolkit operates offline.

| Task | Document |
|---|---|
| Understand the byte envelope, checksum and direction conversions | [Serial protocol](serial-protocol-v292.md) |
| Look up a command, its limits and evidence | [Commands](commands.md) |
| Decode status bits, weight, RPM, temperatures or firmware number | [Response fields](response-fields.md) |
| Distinguish raw board faults from Android errors | [Error codes](error-codes.md) |
| Understand caching, scheduling and intermittent sessions | [Timing and state](timing-and-state.md) |
| See the host/controller command and callback paths | [Hardware architecture](hardware-architecture.md) |
| Explore app components, privileges and OEM dependencies | [Android architecture](android-architecture.md) |
| Develop an independent Android app against the desktop | [Integrated connection](android-connection.md), [emulator](android-emulator.md), [demo](android-demo.md), [Kotlin API](../../../../android/README.md) |
| Understand SQLite/JSON research without proprietary content | [Recipe format](recipe-format.md) |
| Separate MCUpdater, Android/FOTA and powerboard firmware | [MCUpdater and firmware](mcupdater-and-firmware.md) |
| Compare the build-specific findings with earlier research | [Historical comparison](historical-comparison.md) |
| Inspect evidence classes, artifact hash and method anchors | [Research methodology](research-methodology.md) |
| Review physical and scientific limits | [Safety and limitations](safety-and-limitations.md) |
| Use the Python library and simulator interfaces | [API](api.md) |
| Launch the native desktop or reuse the headless dynamics | [Digital Twin](powerboard-simulator/README.md), [native desktop](powerboard-simulator/desktop.md) |
| Install Python/Tcl/Tk on Windows, Linux or macOS | [Cross-platform quick start](powerboard-simulator/crossplatform-quickstart.md) |
| Read the compact observed-protocol reference | [Build 292 reference](protocol/README.md) |
| Analyze logs, inspect bytes and view telemetry | [Developer tools](developer-tools.md) |
| Follow a complete memory-only development example | [Tutorial](tutorials/first-steps.md), [Detailed tutorial](tutorials/first-steps-detailed.md) |
| Resolve practical installation and fidelity questions | [FAQ](faq.md) |
| Resolve terminology | [Glossary](glossary.md) |

The structured field description is [protocol_292.json](../../../../specs/mcc/protocol_292.json). [Third-party references](../third-party-references.md) credits prior work and records the observed license status. For installation, CLI examples and test execution, start with the [README](../../../../README.md).
