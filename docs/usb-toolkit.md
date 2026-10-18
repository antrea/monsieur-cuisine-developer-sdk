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
verification-disabling, downgrade or automatic permission-grant flags are used.

`AdbClient` executes the actual subprocesses. `AppTransaction` saves a durable,
checksummed write-ahead journal, snapshots packages/HOME/supported settings,
and compensates changes in reverse order. New user apps are supported; general
updates of existing apps and their private data are unfinished and rejected.
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

`home COMPONENT --journal ... --allow-app-changes` changes persistent HOME only
when Android pm provides set-home-activity and the old HOME is unambiguous.
API 23 lacks that command; the toolkit reports the limit. `home-chooser` opens
Android's supported selection UI without claiming automatic persistent success.

Two actual API 23 emulator cycles exercised installation, launch, removal,
setting restoration and resumed rollback, including interruption after Package
Manager installed the app but before journal success was saved. Both native
demo profiles also passed Activity-to-Tk integration on API 23. These are
emulator results, not physical MCC validation. No ADB bypass or USB autorun is
implemented. The alternative launcher/complete App Manager remain in progress.

Legacy plan/rehearse remain explicitly synthetic; they are not the evidence
for operational ADB behavior. See [recovery](recovery.md),
[OEM conformance](oem-conformance.md) and [serial transport](hardware-transport.md).
