> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Android Emulator setup

1. Open the android directory in Android Studio and sync the pinned Gradle project.
2. Install Android SDK platform35/build-tools35 and create an official Android emulator (API26+).
3. Run the Python desktop and Enable Android Connection on127.0.0.1:8766.
4. Run the demo on the emulator and Connect to10.0.2.2:8766. Use the same configurable port on both sides.

The emulator's10.0.2.2 address is a special alias for the host loopback.127.0.0.1 inside Android points to Android itself. Do not change Python bind to0.0.0.0 to make this work. See [official emulator networking](https://developer.android.com/studio/run/emulator-networking-address).

The APK requests only normal INTERNET permission. It has no system UID, root requirement, UART access or OEM-service dependency. Network I/O runs on an executor, not Android's main thread. Activity onStop disconnects; onDestroy shuts down the executor. Polling and callbacks are tagged with a generation so old sessions cannot restart a new one. Reconnection requires an explicit button press.

Debug manifest permits local cleartext; release manifest declares cleartext false. Raw java.net.Socket is not HTTP and this manifest flag is not a substitute for TLS/authentication or a universal raw-socket firewall. The library itself restricts destination hosts to emulator/loopback values. This development protocol is unencrypted and unauthenticated and is intended for trusted local use only; no LAN binding is provided.

If Connect fails: verify the listener is enabled, ports match, no other client owns control and local firewall rules permit the emulator. EOF may mean a rejected second controller or unsupported frame; inspect Python diagnostics. Receive deadline expiry closes the client; reconnect explicitly. Do not assume a missing response means the command was not applied.

This is an original developer APK. The manufacturer's com.tecpal.device.mc30 APK relies on OEM services/libraries/privileges and is not promised to run on a generic emulator. No real hardware is contacted by these instructions.

See the release audit for the exact emulator/API versions and actual results; a configured CI job is not proof it ran. Android Studio UI installation itself is not necessary for command-line Gradle/emulator verification.
