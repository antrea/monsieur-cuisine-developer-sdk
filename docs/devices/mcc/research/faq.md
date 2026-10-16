> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Frequently asked questions

**Is this the full microcontroller protocol or recovered firmware?**

It is a complete account of the application-side TX/RX fields and commands observed in the hash-identified build292. Unknown board commands, bootloader operations, internal control loops and MCU firmware remain outside the evidence. See [protocol](serial-protocol-v292.md) and [firmware research](mcupdater-and-firmware.md).

**Can I use the library without the desktop or simulator?**

Yes. Import `mcc_protocol.codec` or `mcc_protocol.stream`, or run `python -m mcc_protocol`. They have no GUI, network or simulator dependency. No proprietary APK is needed. `mcc_tools` adds local log analysis and field inspection.

**What runs when I open the Digital Twin?**

`python -m mcc_digital_twin` starts a native Tkinter/ttk window and its model in one Python process. It starts no HTTP/TCP server, browser, device port or child process. The headless model imports no Tkinter. Optional transports require an explicit API/CLI call.

**Does it work without Internet or hardware?**

Yes. Runtime code needs the standard library; GUI mode also needs your Python distributor's Tcl/Tk support. Python installation, optional pip build dependencies and GitHub CI provisioning can require downloads, but ordinary source execution does not. No firmware, account, device serial or vendor service is used.

**Which platforms were actually tested?**

The release audit records execution on Windows11 with Python3.11.9 and3.12.14; Tkinter GUI was tested with3.12.14/TclTk8.6.12. The codebase is portable and CI is configured for Windows/Linux/macOS. Linux/macOS execution and the POSIX PTY integration have not been run on the development host. A configured CI workflow is not a passed hosted run. See [release audit](../../../evidence.md).

**Can I connect an unmodified original APK directly?**

An APK expecting Binder/OEM services and `/dev/ttyMT0` is not redirected merely by starting Python. A developer must supply an integration seam or substitute byte transport. The application logic above that seam can use original MCC packets. The project provides a raw loopback TCP endpoint, a Python serial-like interface and an original Android mock example; no device modification or firmware replacement is included.

**What does the virtual serial adapter do on Windows?**

The in-process `SerialLike` API needs no drivers. The optional POSIX PTY bridge allocates a new virtual terminal on supported platforms. Windows COM-pair emulation is not implemented; no driver is installed and no arbitrary COM port is opened. TCP is the driver-free external application option. See [adapter limits](powerboard-simulator/virtual-serial.md).

**Does a simulated stop prove a real motor stopped safely?**

No. The model uses explicit synthetic coefficients for acceleration, braking, coasting and heating. Tests establish software consistency and protocol encoding only. The wire has no per-command ACK or timestamp; even new local telemetry cannot establish which TX it reflects. Physical stop times, duty cycles, watchdogs and hardware interlocks remain unverified.

**Are recipes, images or APKs included?**

No. Documentation and code are original, fixtures synthetic, and upstream work is attributed in [references](../third-party-references.md). The structural recipe JSON is illustrative and is not a working vendor recipe.
