# ADB application toolkit and durable rollback

Normal startup never runs ADB. Operational commands require an exact authorized
target and selected ADB tool; mutations also need `--allow-app-changes`. No
operation enables debugging, obtains root, replaces protected OEM apps or
writes firmware/partitions. Add `--server-port` for an isolated emulator server.

```sh
mc-usb info --adb ADB --serial SELECTED_DEVICE
mc-usb apps --adb ADB --serial SELECTED_DEVICE
mc-usb install YOUR.apk --aapt AAPT --adb ADB --serial SELECTED_DEVICE \
  --journal NEW_PRIVATE_TRANSACTION --allow-app-changes
mc-usb start org.example.app/.MainActivity --adb ADB --serial SELECTED_DEVICE
mc-usb rollback --adb ADB --serial SELECTED_DEVICE \
  --journal PRIVATE_TRANSACTION --allow-app-changes
```

`devices` lists identifiers for explicit selection; do not publish its output.
APK metadata comes from the real manifest via Android SDK aapt, with a size
bound and SHA-256 check. Android Package Manager validates signatures. No
verification-disabling or automatic permission-grant flags are used. The
explicit debug-update rollback below uses Android's checked developer downgrade.

`AdbClient` executes the actual subprocesses. `AppTransaction` saves a durable,
checksummed write-ahead journal, snapshots packages/HOME/supported settings,
and compensates changes in reverse order. New user apps and data-preserving
updates of supported debuggable user apps are implemented. Production/non-debug
and split-APK update recovery are outside this supported workflow and rejected.
Standalone `remove PACKAGE --allow-data-removal --allow-app-changes` removes a
selected user app and its data, without claiming a data-preserving rollback.
System/manufacturer packages are rejected.

Supported configuration keys are screen brightness and screen-off timeout:

```sh
mc-usb config screen_brightness 128 --adb ADB --serial SELECTED_DEVICE \
  --journal PRIVATE_TRANSACTION --allow-app-changes
```

Rollback can resume after interruption, verifies the target and installed APK
hash, and checks final conditions. Conflicting external APK/settings changes
stop compensation rather than being overwritten. Repeated rollback is
idempotent. Removing an app added by the transaction also removes data it
created during that transaction. Journals are private device metadata: keep
them outside published source and distributions.

`home COMPONENT --journal ... --allow-app-changes` changes persistent HOME using
Android pm where set-home-activity exists. API 23 lacks that command. On the
supported Android 6 stock HOME Settings screen the toolkit can select the exact
matching row's radio button through UI Automator, first checking the Settings
foreground app and then verifying Package Manager's persistent preference.
An ambiguous/unsupported screen fails without tapping guessed coordinates.
`home-chooser` just opens the supported selection UI and does not imply success.

The separate `android/manager` user app (API 23) coexists with OEM software. It
lists/starts apps, offers the system HOME settings, clears its own HOME preference
and returns to the previous launcher. The shell query/clear-own-HOME receiver is
protected by Android's DUMP permission. It cannot change arbitrary protected
packages. Install the manager with a transaction before selecting its HOME;
rollback restores the previous explicit or implicit HOME before removing it.
Its SAF/PackageInstaller flow requires normal Android user consent. The complete
file-selection/cancel/consent/new-install path passed on the API23 emulator.
Physical USB-drive recognition and deployment on an original MCC remain
unverified; the emulator test used a test-only document provider.

## Installing and updating from a USB drive with the Manager

The owner's path without a computer has two halves. The **first installation**
of the Manager uses stock Android 6 screens only: the storage notification's
*Explore* action (or the file browser) on the mounted drive, touching the APK,
Android's *Install blocked* dialog leading to *Settings → Unknown sources*,
then Android's own *Install* and *Open*. Every later installation or update
goes through the Manager: *Install a user-selected APK* opens Android's document
picker, where a mounted drive appears as a root; the Manager inspects the file,
states new-installation versus update and warns about an older version or a
different signing key, and Android's PackageInstaller asks for consent and
applies its signature and compatibility checks. Results are journaled, explained
in plain language together with what is actually installed now, and the
installed app can be started from the Manager. See the Android project README
for the implementation and the API 23 instrumentation.

Firmware facts (static): the original image declares USB Host and a vold-managed
removable volume for the service port (`fstab.mt6580`: `voldmanaged=usbotg:auto`,
vfat), and ships DocumentsUI, PackageInstaller, Settings, SystemUI and the
manufacturer's own file manager app. What they do not prove: that a physical
stick is powered, enumerated and mounted on an original MCC, and that the status
bar, Settings or that file manager can be reached from the full-screen
manufacturer app. One lab result narrows the path further: on Android 6 the
stock document browser (the notification's *Explore* screen) does **not** hand an
APK to the installer, because it offers a `content:` URI that the API 23
PackageInstaller refuses; a file manager that opens the APK by file path does,
and the installer side (blocked dialog → Settings → Unknown sources → Install →
Open) passed on the API 23 emulator with exactly that handover. The remaining
prerequisites are the owner's manual checks and stay the gate of the first
installation. There is no autorun.

## USB cable versus USB storage

The PC workflow uses an explicitly selected, authorized ADB connection. The
owner's backup shows debugging disabled by default; no physical MCC procedure
for enabling it has been verified. Operational emulator tests do not remove
that prerequisite on the actual appliance.

The native Manager can select an APK from a file provider exposed by Android,
including a USB drive **if the physical system mounts and exposes it**. It does
not supply USB autorun or a verified first-install path on the original MCC.
The actual SAF test proves new installation with consent, not a full USB-drive
update/rollback procedure. Supported desktop debug-app updates and rollback
have their separate evidence below. Firmware/partition writes are not enabled
by either application-installation workflow.

Two actual API 23 emulator cycles exercised installation, launch, removal,
setting restoration and resumed rollback, including interruption after Package
Manager installed the app but before journal success was saved. Both native
demo profiles also passed Activity-to-Tk integration on API 23. These are
emulator results, not physical MCC validation. No ADB bypass or USB autorun is
implemented. Persistent HOME selection and rollback have also passed on the
API 23 emulator. A second test executed Android commands as UID 2000 through an
emulator-only privilege-reduction adapter. The emulator's daemon/SELinux context
still differs from a physical non-root MCC: that test is not hardware validation
or proof of stock physical shell policy. Supported debug-app update/data cycles
also passed on API 23, including interruptions after forward replacement and
after returning to the original APK, Unicode/long/space names and a test-owned
AndroidKeyStore key. Real Tk update/rollback controls passed the same workflow.

## Existing debug-app update and file-data rollback

```sh
mc-usb update NEW_VERSION.apk --aapt AAPT --adb ADB --serial SELECTED_DEVICE --journal NEW_PRIVATE_TRANSACTION --allow-app-changes
mc-usb rollback --adb ADB --serial SELECTED_DEVICE --journal PRIVATE_TRANSACTION --allow-app-changes
```

`AppTransaction.update(apk, metadata, aapt=...)` checks a previously installed
monolithic user APK and requires both old/new manifests to be debuggable. It
backs up the old APK, makes a verified private copy of the replacement, checks
`run-as` access and the application's UID, then force-stops and snapshots its
accessible sandbox. The intent precedes app-state changes; a complete snapshot
is journaled before the checked `install -r` replacement. Android verifies the
signer and installation compatibility. A source APK being rebuilt cannot change
the private replacement after its hash was verified.

Rollback validates the journal, old APK, data archive, package and UID; preserves
current post-update data in a new private safety copy; restores the old debug APK
using supported `install -r -d`; and restores/verifies original accessible files.
It does **not** uninstall, clear data, obtain root, replace protected apps or
extract keystore keys. Keeping the same installed UID avoids the key loss of an
uninstall/reinstall fallback. The API 23 test verified a synthetic test key's MAC
before/after; it did not export that key or inspect manufacturer credentials.

Snapshots use bounded binary transfers, validated tar metadata and host-side
hashes; no archive member is extracted onto the host. Android 6 toybox tar
cannot safely handle all long/non-ASCII names. Such trees use NUL-delimited find,
batched numeric stat, direct file transfer and host-generated GNU archives.
Restore uses file-by-file writes for those trees, preserving original names.
Simple trees retain the tested native-tar path. Unsafe links/special files,
changing trees, excess size/count and unsupported access fail explicitly.

`RunAsData.snapshot(package, new_directory)`, `load(directory)` and
`restore(directory, workdir=...)` expose the file APIs. Whole-archive transfers
are bounded to 512 MiB; inventories to 20,000 entries. APK-provided `lib` is
excluded; accessible files, shared preferences, SQLite data, caches, no_backup,
custom directories and root sandbox files are included. External storage,
unavailable app data, device-wide permission state and keystore export are not
part of the file snapshot. App processes must remain quiescent; external tools
can still invalidate a transaction and are detected where observable.

After interruption, use the same journal with `rollback`. A failure before the
snapshot is ready cannot silently proceed with replacement. A failure after
replacement or downgrade is recovered by inspecting installed hashes and
reapplying the verified data restoration. Conflicting APK/UID/snapshot changes
stop recovery. Partial and safety copies remain private for diagnostics. At most
32 restoration safety copies are accepted per action; the bound stops further
mutation instead of deleting previous copies.

The [original platform/updater analysis](devices/mcc/research/platform-startup.md)
records disabled/debuggable defaults, privileged OEM update context and the
USB Host declaration. It does not establish USB-stick autorun, a physical ADB
activation procedure or permanence of an alternative HOME through OEM updates.

The ordinary Android Manager has also been exercised through real API23 system
UI: its install button opens DocumentsUI, a test-only SAF provider supplies an
independent developer APK, Cancel preserves absence, and Install requires normal
PackageInstaller consent before the package appears. The test enables the source
preference through Settings UI and restores its original value. The fixture is
copied for the provider, never installed through ADB. A real regression reproduced
API23's non-idempotent session-stream close; the Manager now closes that stream
once before commit and does not abandon committed sessions during cleanup.
Build and reproduction details are in the [Android project](../android/README.md).

Legacy plan/rehearse remain explicitly synthetic; they are not the evidence
for operational ADB behavior. See [recovery](recovery.md),
[OEM conformance](oem-conformance.md) and [serial transport](hardware-transport.md).
