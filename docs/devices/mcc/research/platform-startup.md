# MCC platform startup, USB and updater evidence

This SDK 2.0 note uses the owner's private full backup. It supersedes the
artifact-absence claims in the [historical updater investigation](mcupdater-and-firmware.md).
No OEM APK, ramdisk or decompiled body is included. Findings below are **OEM
STATIC VERIFIED** for the identified files, not physical-device observations.
Decompiler output remains an interpretation of bytecode, not recovered source.

## Identified artifacts

| Artifact | SHA-256 |
|---|---|
| Android `boot.bin` | `23b1c6eba1ac28e673be53433efe4f79ff6006213f7e87eb4674c6d840f2cae8` |
| Android `recovery.bin` | `52fc98c3731977fbba23415bb0470aebf49bc44aeb3d87518b32ccd883bb20da` |
| `system/priv-app/MCUpdater/MCUpdater.apk` | `cf13ca9849ab2444a7f6df54c133d85a3d979fd69635efb511cd7b2d9c0e0cd1` |

The updater manifest identifies `de.silpion.mcupdater`, version code 9 / 1.0.9,
minSdk 21 and shared UID `android.uid.system`. It requests install/reboot/boot
permissions. This is privileged OEM context; an ordinary independent user app
does not gain those privileges by reproducing its package name or manifest.

## Boot and ADB

The original boot ramdisk `default.prop` records `ro.adb.secure=1` at line 4,
`ro.secure=1` at line 6, `ro.debuggable=0` at line 9 and the default USB
configuration `mtp` at line 17. `init.rc:559–564` defines adbd as disabled and
controlled by USB property triggers. The separate QEMU trigger begins at line
567. Its emulator behavior does not establish the MCC's physical shell policy.

Recovery has the same secure/debuggable defaults. Its `init.rc:92–100` declares
a disabled adbd service and a separate debuggable-build trigger. These findings
do not establish that a physical owner can activate authorized debugging from
the OEM UI. No menu sequence, key combination or firmware edit has been verified
for that purpose by this SDK. The ADB toolkit reports unavailable/unauthorized
targets; it does not change these properties or obtain root.

`init.project.rc:107–108` sets mode 0666 on `ttyMT0` and `ttyMT1`. Permission bits
alone do not establish SELinux access, wiring or safe operation. Serial-driver
tests stay separate from startup and never open those names automatically.

## USB direct installation boundary

The system contains `etc/permissions/android.hardware.usb.host.xml` declaring
the Android USB Host feature. The ramdisk also contains USB gadget property
rules. These are software capability evidence, not proof of physical OTG role
switching, service-port wiring, external-storage mounting or automatic launch.
The SDK does not claim that inserting a USB stick executes a script.

The independent native Manager offers SAF file selection and ordinary Android
PackageInstaller consent. This supplies an installation component where the
platform exposes an accessible file provider. Its existence does not prove the
MCC can read a specific USB drive; that needs a physical port/mounting test.

## Original updater control flow and SDK consequences

JADX 1.5.6 output from the identified APK provides these exact method references:

| Original unit | Static result | SDK consequence |
|---|---|---|
| `BootBroadcastReceiver.onReceive`, lines 13–18 | Starts MCUpdateService for boot/reboot broadcasts | Alternative HOME selection alone does not remove the OEM updater; the SDK leaves it intact |
| `MCUpdateService.onStartCommand`, lines 191–194 | Returns service mode 1 | Service lifecycle is separate from the HOME preference |
| `MCUpdateService.installUpdate`, lines 421–433 | Starts installation with three attempts | The independent transaction journal verifies actual package postconditions rather than imitating retries blindly |
| `MCUpdateService.AnonymousClass4.installCompleted`, lines 397–402 | Clears download/state and invokes the package launch path | An OEM update can explicitly launch its app even when another HOME is selected |
| `MCUpdateService.launch`, lines 459–469 | Resolves the package launch intent and starts it | HOME rollback must not be advertised as permanent control over all OEM startup/update paths |
| `PackageUpdater.installPackage`, lines 40–83 | Creates/writes/fsyncs/commits an Android PackageInstaller session | The independent Manager uses supported PackageInstaller APIs with normal user consent |
| `PackageUpdater` completion receiver, lines 46–52 | Calls installCompleted without reading the status extra in this decompilation | The SDK deliberately checks real results; it does not copy an apparent success-only callback assumption |

The last observation is a static finding, not a dynamically reproduced OEM
installer defect. The updater was not run against vendor services or used to
install OEM software. The SDK Manager handles pending user action, failure and
success separately; the desktop backend verifies packages and hashes after ADB
operations. Neither replaces the privileged OEM updater.

The recovered updater is an Android package-update implementation. These paths
do not identify a PowerBoard firmware payload, MCU bootloader, page-write
protocol or a safe flashing procedure. Those remain unverified.

See [ADB/App Manager](../../../usb-toolkit.md), [recovery](../../../recovery.md)
and [independent OEM conformance](../../../oem-conformance.md) for the different
dynamic-test scopes.
