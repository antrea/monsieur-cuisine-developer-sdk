# Independent OEM reference execution

The original build-292 DEX is the reference, not an SDK-generated implementation.
Rebuilding the older dex2jar/JVM reference reproduced all 57,998 prior records.
The independent `android/oemprobe` now also executes the original DEX directly
on Android 6/API 23 ART, without a conversion step.

The probe contains only reflection/input/output code: no SDK codec dependency,
OEM classes/assets or INTERNET permission. It never instantiates UART/services.
Only named PowerBoard, CookingUtils and Limits methods run.

```sh
# From android/: use gradlew.bat on Windows
./gradlew :oemprobe:assembleDebug

# From repository root; choose a NEW private work directory outside it
python tools/verify_oem.py --apk OWNER_APK --probe-apk PROBE_APK --adb ADB \
  --serial emulator-5580 --server-port 5039 --workdir PRIVATE_WORK
```

The host verifier requires an explicit emulator and confirms API 23. It extracts
a bounded DEX, hashes it and verifies that digest inside Android before load.
Only the open-source probe is installed. Original bytes and logs stay outside
the source checkout; the temporary remote DEX is removed after execution.
Android SDK/emulator and an owner-supplied reference are optional test tools,
never normal Digital Twin requirements.

The actual ART comparison produced 34,560 TX, 20,000 RX, 351 Celsius-to-level,
29 level-to-Celsius, 15 time-limit and 3,043 RPM-to-level records, with zero
SDK disagreements. Invalid serializer inputs remain an intentional difference:
OEM substitutes zero while SDK rejects. Calibration bytes are also compared
against the SDK calibration encoder.

Original APK SHA-256:
`5e9125bb5e618e8eb989bfff8096f09cbad5e4fd3e5b08768fd624f36efc0482`.
Original DEX SHA-256:
`daacbce286ea9f4911556d37c66b8559a3f341046cf720fb900bc047b10c2b53`.

`monsieur_cuisine_sdk.conformance.compare_reference(path)` streams a bounded
recorded dataset without loading executable code. Dataset agreement alone does
not prove OEM origin; `tools/verify_oem.py` records the separate execution chain.
Neither comparison invokes Digital Twin physics.

Results are OEM DYNAMIC VERIFIED for these host methods only. Decompiled
cooking rules remain OEM STATIC VERIFIED; synthetic models/transport tests
remain INTERNAL TESTED. The MCU, real UART, motor/heater dynamics and restore
safety remain UNVERIFIED. No HARDWARE VERIFIED result is claimed.
