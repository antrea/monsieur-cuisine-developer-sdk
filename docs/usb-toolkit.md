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
Its SAF/PackageInstaller flow requires normal Android user consent; complete
end-to-end verification of that import/consent path remains in progress.

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

Legacy plan/rehearse remain explicitly synthetic; they are not the evidence
for operational ADB behavior. See [recovery](recovery.md),
[OEM conformance](oem-conformance.md) and [serial transport](hardware-transport.md).
