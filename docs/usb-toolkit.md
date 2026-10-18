# MCC USB toolkit: available offline and diagnostic functions

This component has two deliberately separate operations: opt-in read-only ADB
diagnostics and an offline application transaction sandbox. It has **no device
installation, launcher-changing or flash-writing executor**.

```sh
mc-usb diagnostics --adb PATH_TO_ADB
mc-usb plan sample.apk --package org.example.demo --minimum-sdk 23 --output app-plan.json
mc-usb rehearse app-plan.json
```

The module form is `python -m monsieur_cuisine_sdk.usb`. `diagnostics` is an
explicit opt-in device read, not a startup action. It permits only `get-state`
and four selected `getprop` keys; arbitrary shell, device enumeration, serial
properties, `pm`, install, settings, reboot and push are rejected. The appliance
normally has ADB disabled, and this branch has not run diagnostics on hardware.
Errors do not print raw device identifiers or private paths. Tests use a fake
ADB runner; no real ADB command is sent by the test suite.

`plan` hashes a user-selected APK as opaque bytes. Package and minimum API are
caller-supplied declarations, **not verified APK metadata**. Signatures are not
inspected and no signing key is used. Manufacturer/system replacement plans are
rejected. A plan cannot prove that an app works on the MCC's Android 6/API 23.

`rehearse` takes an in-memory baseline, applies the plan to a simulated package
registry, selects its simulated launcher, then rolls back and checks equality.
The JSON result explicitly reports simulation, zero hardware commands and no
hardware restoration test. API users can use `ApplicationSandbox.snapshot`,
`apply`, `select_launcher` and `rollback`. This is useful for testing transaction
logic; it is not an installer and does not modify a connected appliance.

The manufacturer launcher remains the sandbox's baseline. The Python/Android
Digital Twin demo is an emulator/test application; its build succeeding does
not establish Android 6 appliance compatibility. USB-host support and automatic
execution from a USB drive have not been established; no autorun mechanism is
claimed or supplied. See [recovery scope](recovery.md).
