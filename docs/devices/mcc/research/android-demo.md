> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# MCC Android Developer Demo

The original native Android sample in [android](../../../../android/README.md) demonstrates direct binary TCP control of the existing Python desktop. Its reusable Kotlin classes are optional; developers can implement the documented frames themselves. No OEM services, original APK, root, Binder workaround, UART, HTTP or additional Python server is involved.

## Included controls

Connect/Disconnect, configurable port, connection state, START/change speed, STOP, speed 0–10, both directions and heat level. Live status shows requested/actual RPM and temperature, signed weight, lid, board/Android errors, firmware version and a bounded TX/RX HEX monitor. The UI uses platform Android widgets and original styling with no proprietary imagery. All displayed appliance state is simulated.

The demo owns one `MccClient` per connection. Writes and connection attempts use a bounded worker queue, reads use a separate worker, and UI updates carry a session epoch. STOP invalidates queued earlier commands. Leaving the foreground or destroying the Activity clears queued work and closes the transport; reconnecting does not resend START. Already transmitted bytes cannot be recalled. The desktop's disconnect STOP policy provides the corresponding synthetic model cleanup.

## Build

Open `android` in Android Studio, sync, and run `mcc-bridge-demo` **debug** on a standard emulator. Or, with JDK 17+ and Android SDK 35 installed, from `android`:

```console
./gradlew :mcc-bridge-demo:assembleDebug
```

Windows PowerShell: `./gradlew.bat :mcc-bridge-demo:assembleDebug`. The output is `mcc-bridge-demo/build/outputs/apk/debug/mcc-bridge-demo-debug.apk` when a real build succeeds. APKs and build caches are excluded from the source archive. Gradle 8.13, Kotlin 2.3.21 and Android Gradle Plugin 8.13.2 are pinned. No release signing key is supplied. Release builds deliberately disable demo connections.

Follow the [emulator walkthrough](android-emulator.md) for the full interactive start/telemetry/STOP/error/reconnect check.

## Develop your own app

Add the `mcc-bridge-sdk` module as a project dependency or copy its MIT-licensed source with attribution. Declare INTERNET permission. Supply worker-thread scheduling and a receive loop; the SDK deliberately does not own an Android Activity or autonomous command scheduler.

```kotlin
import labs.blackstuff.mcc.*

// On a background worker:
val client = MccClient(TwinTcpTransport(TwinEndpoint(port = 8765)))
client.open()
try {
    client.startMotor(2, Direction.COUNTER_CLOCKWISE, temperatureLevel = 0)
    repeat(8) {
        val state = client.receiveState(1000)
        println("${state.actualRpm}/${state.targetRpm}: ${state.rawHex}")
    }
    client.stopMotor()
    // Keep receiving until measured RPM is zero; do not treat write as ACK.
    while (client.receiveState(1000).actualRpm != 0) { }
} finally {
    client.close()
}
```

Production-quality application logic needs a cancellation/deadline policy around that illustrative receive loop, separate receiver/writer workers and main-thread UI updates. The complete demo implements duplex receive, bounded queues, timeouts and lifecycle cleanup. `readState()`, `readTemperature()`, `readWeight()` and `readErrors()` return cached observations; they do not invent query opcodes. See the [API](../../../../android/README.md).

The original MCLauncher binary cannot connect automatically: its device-specific serial/Binder/OEM dependencies remain. Future physical PowerBoard support is represented only by an abstract `HardwareTransport` contract; no implementation or access to `/dev/ttyMT0` is supplied.

## Reproducible host checks

From `android`, without an Android SDK:

```console
./gradlew -PincludeAndroidDemo=false :mcc-bridge-sdk:test :mcc-bridge-sdk:hostJar
```

Then from the toolkit root (JDK `java` on PATH):

```console
python tools/verify_kotlin_vectors.py
python tools/verify_android_connection.py
python tools/verify_android_connection.py --gui
python -m unittest discover -s tests -v
```

The host-tests JAR is a local build output, not a distributed binary. Verification tools accept `--java`, `--jar`, `--report`. Cross-language checks use the existing eight Python golden TX fixtures, all 6160 encoder parameter combinations and 4096 seeded RX frames with 30 decoded fields each. The JVM integration drives START, speed change, finite STOP, injected error, clear, disconnect and reconnect against the real Python controller; `--gui` creates the real Tk window and enables its integrated connection. The recording must replay identically.

Host tests exercise the same SDK/client used by the Android demo. They do **not** execute the Activity, Android framework, ART, manifest/resource processing or emulator networking. These require an actual SDK/emulator run; the [audit](../../../evidence.md) states the executed scope explicitly. A passed simulator test never certifies real appliance safety.
