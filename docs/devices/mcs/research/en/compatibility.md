> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Compatibility and validation matrix

Local verified environment: **Windows, CPython3.12.14, Tk8.6**. SDK/headless import, source tests, real Tk initialization/interactions/close, examples and CLI are tested locally. See [release audit](../../../../evidence.md) for exact installation/build results and test counts.

Declared Python requirement >=3.11. GitHub Actions targets Windows/Ubuntu/macOS × Python3.11/3.12/3.13; it has not run remotely in this local-only release. Linux/macOS and other Python versions are intended source compatibility, not passed executions. Tk packaging/display availability varies. No compiled platform extension or Windows path is required by runtime code.

Wire compatibility: the historical1.2.14.15 active multo layout only. Legacy TX35 is supported as a layout variant, not proof all historical app versions behave identically. Version1.2.13.4 and factory1.1.24.6 were retained in private research, not promoted to independently validated public protocol profiles. ReportedV2.19.1 was not acquired. No MCU image or physical appliance was tested.

The SDK intentionally validates exact length more strictly than permissive APK helpers and supplies a robust stream parser instead of copying the original fixed-read loop. Consumers must handle exceptions, None/delayed replies and unknown fields. It has no binary ABI relationship with Android or dependency on MCC, Java, REA, Flask, Node or network services.
