# Monsieur Cuisine Android Developer SDK

One Android Studio project, one Kotlin client, one duplex TCP transport and one native demo support an explicitly selected MCC or MCS model. Each model retains its original binary codec and stream parser. The project is an independent developer simulator; it supplies no physical serial driver, manufacturer service or firmware flasher.

## Build

Use JDK 17 or 21, Android SDK platform 35 and build-tools 35.0.0. Set `ANDROID_HOME` to your licensed local SDK installation, or set `sdk.dir` in an untracked `local.properties`. Open this directory in Android Studio.

```sh
./gradlew :sdk:test :sdk:assemble :demo:assembleDebug :demo:assembleDebugAndroidTest \
  :manager:assembleDebug :manager:assembleDebugAndroidTest :manager:lintDebug \
  :oemprobe:assembleDebug :oemprobe:lintDebug
```

On Windows use `gradlew.bat`. Gradle 8.13's distribution checksum is pinned. Kotlin 2.3.21 and Android Gradle Plugin 8.13.2 are declared once at the project root. Android dependency installation is disabled; install required SDK packages separately. The JVM SDK can also be tested with `-PincludeAndroidDemo=false` (the root build still resolves its declared plugins).

The development SDK JAR is `sdk/build/libs/sdk-2.0.0-dev0.jar`; it needs the Kotlin standard library on its runtime classpath. The installable developer APK is `demo/build/outputs/apk/debug/demo-debug.apk`. Release APK output intentionally disables the demo connection. No signing keys are supplied with the sources.

## Signing release builds with your own key

`manager` and `demo` accept `-PmcSigningProperties=PATH` pointing to a private
properties file with `mcSigningStoreFile`, `mcSigningStorePassword`,
`mcSigningKeyAlias` and `mcSigningKeyPassword`. With it, `assembleRelease`
produces APKs signed with that key; without it the release APK stays unsigned.
A missing properties file or keystore fails the build: no key is generated
automatically. Keep the keystore outside the repository (`*.jks`, `*.keystore`
and `*.apk` are ignored by Git). Android accepts an update only when the new
APK is signed with the same key and carries a higher `versionCode`, so the key
used for the first installation must be kept for every later update. The demo
also takes `-PdemoVersionCode`, `-PdemoVersionName`, `-PdemoApplicationId` and,
for deliberately incompatible test fixtures only, `-PdemoMinSdk`.

## Native Manager and independent reference probes

All application modules retain **minSdk 23**, including Manager and oemprobe.
Manager is an ordinary user-space HOME/app list with a user-selected SAF APK
installer. It leaves protected system/OEM apps intact; Android owns install and
uninstall consent. PackageInstaller streams close once before commit, and a
committed session is never abandoned by post-commit cleanup errors.

The install flow reads the selected document's name and size, copies it into
private cache with a 512 MiB bound, inspects it with `getPackageArchiveInfo`
(label, package, version, signatures), distinguishes a damaged file from a
well-formed APK that API 23 cannot parse (typically a newer minimum SDK),
refuses manufacturer/system packages, and
tells the user whether this is a new installation or an update, whether the file
is older than the installed copy and whether its signing key differs; Android's
PackageInstaller then performs the authoritative signature/compatibility checks
and asks for consent. Every outcome is journaled (`InstallJournal`), mapped to a
plain-language message with the actual installed state re-checked afterwards,
and an **Open** button starts the installed app. If the Manager is closed while
reading, before Android answers, or while a confirmation is pending, the next
start explains what happened and discards its own stale session. The demo app
keeps a launch counter and a notes file in private storage, visible on screen,
so an update's data preservation can be observed.

`UsbDeliveryExercise`, run through the same `ConsentInstrumentation` with
`-e scenario usb`, drives the whole path through the real DocumentsUI and
PackageInstaller on an API 23 emulator with fixtures served by the test-only
provider (`files/fixtures/*.apk`): new install with consent, data creation in the
installed app, cancelled update, damaged file, foreign signing key, incompatible
minSdk, file vanished before reading (`unreadable-*.apk`), real update keeping
the data, downgrade refusal, and the Manager closed during Android's consent.
Arguments: `-e scenario usb -e package PKG -e v1 FILE -e v2 FILE [-e v3 FILE
-e damaged FILE -e otherkey FILE -e minsdk FILE -e unreadable FILE]`. A software
provider never proves that a physical USB drive is mounted by an appliance.

Manager's test-only DocumentsProvider supplies one independent developer APK to
the real DocumentsUI; it is absent from the runtime APK. `ConsentInstrumentation`
drives actual system controls for source permission, SAF selection, cancellation
and installation approval. It requires an API23 software emulator and a fresh
`org.blackstufflabs.monsieurcuisine.demo.consenttest.debug` fixture, built with
`-PdemoApplicationId=org.blackstufflabs.monsieurcuisine.demo.consenttest`.
Supply that APK privately, hash it, and place a copy in the test provider's
`files/consent-fixture.apk` sandbox using `run-as` for the test package. This
bootstrap copies a test document; it does not install the fixture app. Invoke:

```sh
adb -s SELECTED_EMULATOR install -t -r manager/build/outputs/apk/debug/manager-debug.apk
adb -s SELECTED_EMULATOR install -t -r manager/build/outputs/apk/androidTest/debug/manager-debug-androidTest.apk
adb -s SELECTED_EMULATOR push PRIVATE_FIXTURE_APK /data/local/tmp/mc-sdk-consent-fixture.apk
adb -s SELECTED_EMULATOR shell run-as org.blackstufflabs.monsieurcuisine.manager.test mkdir -p files
adb -s SELECTED_EMULATOR shell run-as org.blackstufflabs.monsieurcuisine.manager.test \
  cp /data/local/tmp/mc-sdk-consent-fixture.apk files/consent-fixture.apk
adb -s SELECTED_EMULATOR shell am instrument -w -r \
  -e apk /data/local/tmp/mc-sdk-consent-fixture.apk -e sha256 FIXTURE_SHA256 \
  org.blackstufflabs.monsieurcuisine.manager.test/org.blackstufflabs.monsieurcuisine.manager.ConsentInstrumentation
```

The remote input must begin `/data/local/tmp/mc-sdk-consent-`. The test uses
normal Settings UI for the unknown-source preference and restores its original
value. Keep these emulator tests separate from physical USB/mount claims.
Use a fresh emulator for this test; a preexisting fixture package is rejected.
After recording the result, remove only these test-owned packages/documents and
rebuild `:demo:assembleDebug :demo:assembleDebugAndroidTest` without the custom
applicationId property to restore the normal demo outputs. The provider and
instrumentation are test artifacts, never a requirement for the Manager.

The [OEM conformance probes](../docs/oem-conformance.md) use owner-supplied
private DEX/native inputs, never bundled firmware. The pure ART harness covers
57,998 codec/conversion records. The separate x86 JNI harness proves software
PTY open; its reproduced original close failure is explicitly not a passing
close test. No normal application startup requires either probe or emulator.

## Open and run in Android Studio

1. Open the repository's `android` directory, containing `settings.gradle.kts`, as the Android Studio project. Let Gradle sync complete. Use JDK 17 or 21 for Gradle and install the SDK packages listed above if they are missing.
2. Start a standard Android Studio emulator running API 23 or newer. Select the `demo` application and its **debug** build variant, then Run it on that emulator. The release variant deliberately refuses the simulation connection.
3. On the desktop, start the Python application with `python -m monsieur_cuisine_sdk`, select **MCC** or **MCS**, and enable **Android Connection** in that same window. See the repository [quick start](../README.md) for Python installation.
4. Select the same model in the Android demo. Use port **8765 for MCC** or **8766 for MCS**, matching the desktop listener, and press **Connect**. The demo automatically uses **10.0.2.2**, the emulator's address for the desktop host. The desktop listener binds **127.0.0.1**; do not change that bind address to 10.0.2.2.
5. Choose speed, direction and an offered temperature, then press **START / apply**. Observe the synthetic state and HEX frames in both applications. Press **STOP**, wait for observed motion to reach zero, and disconnect when finished. Changing the model or backgrounding the Android app disconnects it.

If connection fails, check that the desktop connection is enabled, the selected model and port match, and the Android build is debug. This demo targets the standard emulator's host connection; its endpoint policy does not support a physical phone's LAN address.

## Use the packaged SDK in another Android app

The demo in this repository uses a Gradle project dependency. Your own application can consume the packaged JAR independently:

1. Run `./gradlew :sdk:assemble` from this directory (`gradlew.bat` on Windows).
2. Copy `sdk/build/libs/sdk-2.0.0-dev0.jar` into your application's `app/libs` directory.
3. Add these dependencies to your application's `app/build.gradle.kts`:

```kotlin
dependencies {
    implementation(files("libs/sdk-2.0.0-dev0.jar"))
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.3.21")
}
```

Use Java 17 bytecode compatibility, as in this project's demo. Kotlin consumers should use a compiler compatible with the library's Kotlin 2.3.21 metadata. A plain JAR does not declare transitive dependencies, so include the Kotlin standard library explicitly. Use the normal SDK JAR for this dependency; `host-tests` and `codec-probe` JARs are development harnesses containing test libraries.

Import `org.blackstufflabs.monsieurcuisine` classes and use the public API below. Start with `MockTransport(model)` for an offline frame fixture, or `TwinTcpTransport` for the explicit desktop connection. When using TCP, keep blocking calls on a worker thread, include your app's Internet permission, and choose an explicit transport policy for your application. A separate Android consumer built from only the packaged SDK JAR and Kotlin standard library has been compiled and executed for both models; it does not need this repository's SDK source directories.

## Public API

```kotlin
import org.blackstufflabs.monsieurcuisine.*

val model = DeviceModel.MCC // or MCS; never inferred from received bytes
val transport = TwinTcpTransport(TwinEndpoint("10.0.2.2", model.defaultPort), model)
val client = MonsieurCuisineClient(model, transport)

// All blocking operations belong on a worker thread.
client.connect()
val initial = client.readState() // null until an observation is received
client.startMotor(3, MotorDirection.COUNTER_CLOCKWISE, temperatureC = 60)
val observation = client.receiveState()
val cached = client.readState() // no new wire query
client.stopMotor()
client.close()
```

MCC duration must be zero because that protocol has no timer field. MCS supports a manual duration of 0–5940 seconds. Temperatures must be exact entries in `client.capabilities.temperaturesC`; the two tables differ. MCS `receiveState` sends the documented state request at most four times per second within the caller's timeout; unsolicited observations drain independently of polling. MCC receives its existing telemetry stream without inventing a request. Successful command methods mean bytes were written, never a confirmed physical action. MCS sequence is preserved, including skipping 0x66, but is not advertised as an acknowledgment correlation key.

`DeviceState` includes the selected model, raw HEX, session generation, arrival time and model-specific raw fields. MCC observed speed is RPM; MCS observed speed is a signed raw motor level, with an explicit unit. No MCS RPM is fabricated. `weightGrams` is nullable for unknown MCS weight-unit codes; raw value, decimal places and unit code remain available. Unit 0 means grams for the synthetic twin's explicit default, not a hardware-verified conversion table.

`MockTransport(model)` is an explicit queued frame fixture, not an appliance model. `HardwareTransport` is only an interface. The TCP endpoint policy accepts literal `127.0.0.1` or Android emulator alias `10.0.2.2`; it cannot select a LAN address or hostname. Default ports are MCC 8765 and MCS 8766.

## Lifecycle and demo

There is one reader, serialized copied writes, bounded receive and command queues, and explicit reconnect. Closing a socket cancels blocked I/O. An ordinary receive timeout retains the connection and does not retry a command. Reconnect clears cached observations and requested output. Frames and UI work carry session generations. Cached reads return null when disconnected or failed.

The native demo has one model selector and common controls. Selecting another model disconnects before the next explicit Connect. STOP invalidates pending commands; an already executing write cannot be undone. Backgrounding the Activity disconnects. Display updates coalesce the latest telemetry, cap pending HEX lines at 64 and refresh at most every 50 ms, so high-rate input cannot grow the main-thread callback queue without bound. TCP is enabled only by an explicit debug-build code guard: a manifest cleartext flag alone cannot enforce raw `Socket` policy.

## Validation

The test suite retains the two original codec suites and their frozen vectors and adds shared transport/client/lifecycle/STOP-queue tests. Run `:sdk:hostJar` to build a private integration harness and invoke `org.blackstufflabs.monsieurcuisine.HostExercise MCC 8765` (or MCS 8766) from its runtime JAR.

The instrumented test launches the actual demo Activity and drives its visible controls. With the shared Python twin listening on the selected port, run:

```sh
adb shell am instrument -w -r -e model MCC -e port 8765 \
  org.blackstufflabs.monsieurcuisine.demo.debug.test/org.blackstufflabs.monsieurcuisine.demo.BridgeInstrumentation
```

The host must inject error code 3 through its ordinary sensor API after the `AWAIT_HOST_ERROR` marker. Repeat with MCS and port 8766. This covers actual Android controls and original binary frames, both model-selector directions, start, speed change, telemetry, STOP, a host-injected fault, reconnect while disarmed and background cancellation. An emulator success does not verify physical UART behavior or an appliance's safety interlocks.

See [third-party notices](THIRD_PARTY_NOTICES.md) and the repository license.
