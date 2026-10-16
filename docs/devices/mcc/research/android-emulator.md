> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Android Studio emulator setup

The Python Digital Twin works offline without Android tools. Building/running the optional Android demo requires a separately installed Android Studio/SDK, an emulator image and a JDK. The first Gradle/SDK setup generally needs Internet downloads; subsequent runs can be offline when dependencies and the emulator image are cached. Nothing installs a driver or SDK automatically.

## Host and emulator

1. Start the Python desktop and enable **Android Connection**, host `127.0.0.1`, port `8765`.
2. Open the toolkit's **`android`** directory in Android Studio. Use a compatible IDE and JDK 17+ (the project targets Java 17).
3. Install Android SDK Platform 35 and Build Tools 35.0.0 using your SDK Manager if missing. Select a standard Android emulator API 26 or newer; API 35 is a suitable target for this project.
4. Select the `mcc-bridge-demo` debug configuration and run it.
5. In **MCC Android Developer Demo**, leave port `8765` and tap **Connect**. It connects to `10.0.2.2`, the standard emulator alias for the host's loopback interface.
6. Choose speed 2, counter-clockwise, heat off; tap START. Watch intermediate RPM in both applications, then STOP and wait for measured RPM zero.
7. Inject error 5 in Python Sensors; the app should display board code 5 / Android code 4. Clear it in Python. Disconnect and reconnect: no automatic START should occur.

The emulator's `127.0.0.1` refers to the emulator itself. The host's `127.0.0.1` listener is reached through `10.0.2.2`. Keep the same port at both ends. This recipe targets the official emulator on the same host, not a physical phone, remote emulator, container, WSL boundary or third-party emulator. No LAN listener, ADB forwarding or root access is required by this design.

## Android networking and lifecycle

The demo declares `android.permission.INTERNET`, which does not need a runtime permission dialog. It uses `java.net.Socket` with binary streams; connect/write/receive run outside the UI thread. A bounded command executor and separate receive worker allow duplex telemetry. A main-thread Handler updates Android widgets. Read timeouts are reported without reconnecting or retrying a command. Disconnect/onStop closes the socket, invalidates session and command epochs, and cancels queued commands. Reconnection requires Connect and a fresh explicit START.

The debug manifest permits the emulator/loopback domains in a network-security configuration; release builds retain a deny-cleartext base configuration and the demo disables simulation connection in code. **Raw Socket traffic is not automatically enforced by Android's cleartext configuration.** The SDK's endpoint allowlist and the demo's `BuildConfig.DEBUG` check provide the actual application restrictions. This is a development transport, not encrypted or authenticated communication with a physical appliance.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Connection refused | Enable the GUI listener; confirm its actual port. |
| Listener Error | Port already in use, invalid host/port or local OS policy; choose another loopback port. |
| Client immediately closes | Another client owns the model, old session still closing, fragment timeout or malformed/slow input. |
| No RPM evolution | Resume virtual time; START must use speed above zero; inspect fault settings. |
| Telemetry timeout | Paused clock, injected loss/delay, broken link, listener disabled or local firewall rule. |
| Gradle says SDK location missing | Configure Android Studio's local SDK location; keep generated `local.properties` out of Git. |
| App disconnects on background/rotation | Intentional lifecycle policy: reconnect explicitly; no retained motor command queue. |

Do not expose the listener on all network interfaces to work around connectivity problems. Any same-host client can connect; the first client owns the simulated session.

Official references: [emulator network addresses](https://developer.android.com/studio/run/emulator-networking-address), [network security configuration](https://developer.android.com/privacy-and-security/security-config), [cleartext behavior and raw Socket limitation](https://developer.android.com/guide/topics/manifest/application-element#usesCleartextTraffic), [AGP 8.13 requirements](https://developer.android.com/build/releases/agp-8-13-0-release-notes).

The v0.2.0 local audit verifies the real Kotlin/JVM transport against the real Tk desktop. Android SDK/emulator execution was unavailable on the validation host; actual APK installation, ART lifecycle and emulator routing still require a device-lab check. See the [verification audit](../../../evidence.md).
