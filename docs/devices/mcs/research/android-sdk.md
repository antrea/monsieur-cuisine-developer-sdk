> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Kotlin SDK for your own MCS Android app

The original SDK is a small JVM library usable by Android, using Kotlin stdlib and java.net.Socket. It has no Android service, companion app, physics model, OEM code or hardware implementation. `McsTransport` abstracts connect/disconnect/sendFrame/receiveFrame/connectionState/cancel/close. TwinTcpTransport uses direct binary TCP; MockTransport queues test frames without simulating a machine; HardwareTransport is an interface only.

## Quick use (worker thread only)

```kotlin
import org.blackstufflabs.mcs.*
import java.util.concurrent.Executors

val worker = Executors.newSingleThreadExecutor()
val client = McsClient(TwinTcpTransport("10.0.2.2", 8766))
worker.execute {
    try {
        client.connect() // explicit; cached requests start stopped
        client.startMotor(speed = 3, reverse = true, temperature = 60, seconds = 90)
        val state = client.readState()
        println("Virtual level ${state.speedLevel}; ${state.temperature} °C")
        client.stopMotor()
    } finally { client.disconnect() }
}
// Activity onStop: client.disconnect(); onDestroy: worker.shutdownNow()
```

Functions also include setDirection, readTemperature, readWeight, readErrors and tare. The convenience client serializes request/response operations, checks response family/shape and never matches by an invented sequence ACK. A successful write means only bytes were written, not physical execution. `readWeight` applies decimal places while preserving the unknown unit code in Telemetry. Heater demand in the demo is explicitly inferred from target vs actual temperature; no measured heater-power bit is claimed.

`McsCodec.pack/parse/manual/operation/ota/telemetry` implement the historical protocol; Frame retains all raw bytes, bitmap, subtype and unknown payload. RX signed8/signed16/signed32 fields follow the APK getter behavior. Operation includes legacy mode and the original constant-temperature high-byte quirk. McsSequence increments/wraps and skips66. Explicit raw sequence parameters permit arbitrary bytes for offline analysis. FE05 has no outbound generator. McsStreamParser handles partial/concatenated frames, bounded diagnostics, resync and explicit expire/finish.

TwinTcpTransport defaults: host10.0.2.2, port8766, connect timeout2000ms, receive deadline1500ms, partial-prefix timeout1000ms. Loopback/emulator hosts only. Reads/writes are serialized separately; a client exchange is serialized as a unit. `disconnect`/`cancel` closes the socket to unblock receive. Timeout or EOF fails/closes that session; reconnect is explicit and creates fresh parser/queues. No stale callback should update a new Activity/session: the demo uses generation tokens. Standard Socket has no independent send deadline; close cancels blocked I/O. Call it off the UI thread.

## Independent Android Studio project

Include the mcs-bridge-sdk module as a Gradle project dependency, or run `:mcs-bridge-sdk:publish` to generate a local Maven repository under android/build/repository. Coordinates: `org.blackstufflabs:mcs-android-sdk:0.2.0`. Configure that local repository in another project and add implementation of the coordinate. No MCC or original MCS APK is required. Build emits library/source JARs; distribution contains original source, not proprietary APK classes.

The Android project pins AGP8.9.2, Gradle8.11.1, Kotlin2.1.20, compile/targetAPI35,minAPI26 and Java bytecode17. Use a compatible JDK17+ (local validation uses21). The wrapper downloads official Gradle on first use; dependency resolution/build may need Internet. Installed simulation communication needs only local TCP.

Run `:mcs-bridge-sdk:test`: golden checks compare the same900 historical envelope fixtures and900 SDK frames byte-for-byte with Python, plus1000 synthetic RX vectors, stream recovery, MockTransport, TCP fragmentation/EOF/deadline/cancellation. These tests establish software consistency, not real MCU compatibility.
