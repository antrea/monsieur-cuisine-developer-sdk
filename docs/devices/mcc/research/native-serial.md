# Original MCC serial JNI: isolated execution evidence

These findings concern the owner-supplied build-292 APK. Original DEX/native
bytes remain private. The public probe contains independent reflection and
test logic, no manufacturer implementation or assets.

| Component | SHA-256 |
|---|---|
| APK | `5e9125bb5e618e8eb989bfff8096f09cbad5e4fd3e5b08768fd624f36efc0482` |
| `classes.dex` | `daacbce286ea9f4911556d37c66b8559a3f341046cf720fb900bc047b10c2b53` |
| `lib/x86/libserial_port.so` | `bd3231f08be279700f6ba64b405429082e02159f136b56fe0f26a0c51877d0fa` |

## What actually ran

On Android 6/API23 x86 ART in a goldfish/ranchu software emulator,
`NativeSerialInstrumentation` loaded the original DEX through DexClassLoader
and the original SO through its private native-library path. It invoked the
original `android_serialport_api.SerialPort(File,int,int)` constructor with
literal `/dev/ptmx`, baud argument 4800 and flags 0. It obtained the original
descriptor field and checked its kernel character-device type. An original
native `open` invocation with unsupported baud argument 12345 returned null.

This is **OEM DYNAMIC VERIFIED** for these x86 open/argument paths. Zero
payload bytes were sent. PTY behavior is not measurement of a UART's baud,
electrical properties, MCU, motor, heater or physical protection mechanisms.
The other ARM libraries have static disassembly evidence only.

## Original close failure

The original Java class exposes descriptor field `a`. Its original x86 JNI
`Java_android_1serialport_1api_SerialPort_close` looks up `mFd` instead.
The close symbol starts at ELF file offset `0xcb0`; the observed abort stack
contains `close+154` (`0xd4a`). API23 CheckJNI reports a pending
`NoSuchFieldError` for the absent FileDescriptor field `mFd` and aborts.
Both the initial failure and an explicit reproduction were retained privately.

No OEM byte was patched to make the test succeed. This observation applies to
this supplied DEX/x86 pair and test runtime; it does not establish that the
physical MCC normally executes this close path or fails identically on ARM.
The default probe reports `original_native_close_verified: false` and
`original_native_close_invoked: false`. It retires the Java stream wrappers and
uses `android.system.Os.close` for its own cleanup, checked with `fstat`/EBADF.
That cleanup is not attributed to the original JNI.

## Reproduce with privately supplied originals

Build the independent probe from `android/` (`gradlew.bat` on Windows):

```sh
./gradlew :oemprobe:assembleDebug :oemprobe:lintDebug
```

From the repository root, provide a NEW private work folder outside the checkout:

```sh
python tools/verify_oem_native.py --apk OWNER_APK --probe-apk PROBE_APK --adb ADB \
  --serial emulator-5580 --server-port 5039 --workdir NEW_PRIVATE_WORK
```

The host and guest both restrict execution to the selected API23 x86 software
emulator; exact DEX/SO hashes are required. Only independent probe code is
installed. UUID remote inputs are removed; private work and command logs remain.
The result explicitly separates open, cleanup, original-close and hardware scope.

To deliberately reproduce the original close failure, repeat with a different
NEW work folder and add `--exercise-original-close`. The expected observed
abort produces **a nonzero tool exit and `failure.json` with `passed: false`**,
plus private instrumentation/logcat evidence. It is never counted as a passing
close test. No UART endpoint is accepted by either mode.

The separate [pure OEM conformance harness](../../../oem-conformance.md) still
runs all 57,998 original host codec/conversion vectors, with zero SDK
disagreements after the probe's targetSdk update. It does not use this native
component. None of these results is HARDWARE VERIFIED.
