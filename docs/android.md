# Android integration

The single [`android`](../android/README.md) project contains `sdk` and `demo`. Its public package is `org.blackstufflabs.monsieurcuisine`. Both codecs remain independent beneath `DeviceModel`, `MonsieurCuisineClient`, `TwinTcpTransport`, `MockTransport` and profile capability metadata. Consult the Android project's README for its checked-in Gradle/plugin versions and exact build/test commands.

## Connect the demo

1. Launch `python -m monsieur_cuisine_sdk` and select MCC or MCS.
2. Enable **Android Connection** in that same desktop window. Default listener: `127.0.0.1:8765` for MCC, `127.0.0.1:8766` for MCS.
3. Open this repository's `android/` directory in Android Studio, prepare a standard emulator, and build/install the `demo` module's **debug** variant.
4. Choose the same device model and matching editable port in the demo, then connect. The demo uses the fixed emulator host alias `10.0.2.2`; custom SDK clients configure an explicit `TwinEndpoint`.
5. Start a bounded synthetic operation. Observe state in both applications. Use STOP and disconnect before selecting another device.

`10.0.2.2` is the standard emulator's host alias; it is not a desktop bind address. The Python listener accepts literal IPv4 loopback addresses only. Remote LAN exposure, device serial access and physical appliance control are not implemented by this bridge.

The APK is an **Android Developer Demo — Emulator/Test Use**, not an official manufacturer app or a validated replacement on an appliance. Android Studio and its SDK dependencies are needed to build it; they are not required by the Python twin. The [Android project README](../android/README.md) includes beginner setup and packaged-JAR consumer instructions.

![Unified desktop with one connected Android command owner](../assets/screenshots/android-connection.png)

## Source API

`MonsieurCuisineClient(model, transport)` validates the model/transport pairing. `startMotor(speed, direction, temperatureC, durationSeconds)`, `stopMotor()`, `receiveState(timeoutMillis)`, cached `readState()`, `connect()` and `close()` provide a common surface. Exact supported values remain profile-specific: MCC duration must be zero; MCS raw levels must not be presented as RPM.

Use the SDK's explicit `TwinEndpoint`/`TwinTcpTransport` for a desktop endpoint or `MockTransport(model)` for offline byte exercises. Hardware transport remains abstract. The SDK cannot make an OEM APK use this simulator merely by presenting compatible bytes; the application must use an authorized source integration seam.

Only one receiving loop should consume a transport. The demo uses a worker and lifecycle cancellation so its UI remains responsive. Model changes require disconnect; STOP invalidates older queued starts. Write buffers are copied, transport queues are bounded, and obsolete generation callbacks cannot update a new session. `readState()` is cached observation, not a fresh wire request or acknowledgement.

MCS telemetry uses its real query operation: the shared client limits queries to at most four per second within the caller's deadline. The desktop's default MCS connection sends responses to queries/commands rather than unsolicited periodic telemetry, avoiding query/response amplification and stale backlog. MCC has no verified query opcode and uses host synthetic sampling. These are explicit simulator/client policies, not proof of the OEM firmware's timing.

## Python embedding

```python
from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.android_connection import AndroidConnection

twin = DigitalTwin(model="mcc")
connection = AndroidConnection(twin)
try:
    connection.start()             # explicitly bind localhost
    # In the owner's event loop: connection.poll(); twin.advance(dt); twin.sample()
finally:
    connection.close()
```

Drive both model and bridge from the creating thread. `poll()` performs bounded nonblocking work; it does not create a second simulation. Network acceptance grants one remote command lease. Another client is rejected. Desktop STOP disconnects and disarms the lease. Disconnect, overflow, fragment timeout (an incomplete frame older than `fragment_timeout`, default 2 s), idle timeout (no traffic in either direction for `idle_timeout`, default 30 s; `last_disconnect: "idle timeout"`) and model switch discard stale fragments/responses and remove targets as an explicit simulator lifecycle policy; measured motion may coast. Telemetry sent by the desktop counts as traffic: with the GUI sampling MCC, a listening-only client keeps its lease; headless, a client that never sends is disconnected after 30 s.

The bytes are raw MCC TX15/RX27 or MCS OB frames. No HTTP, handshake wrapper, clock opcode or invented ACK is added. MCC has no request sequence; MCS's independent counter skips `0x66` but is not proven request/response correlation.

## Validation boundary

JVM codec/transport tests and Android APK build checks are separate from actual emulator instrumentation. A successful APK build does not prove the demo launched, received telemetry or survived a reconnect. The [validation record](tests.md) reports only completed work; original OEM apps and real hardware are outside these tests. Debug-only simulator network policy belongs to the demo; applications integrating the SDK must choose their own explicit transport policy.
