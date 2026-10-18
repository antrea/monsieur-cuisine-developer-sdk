# SDK 2.0 local development architecture

This branch evolves the unified SDK; it does not replace the original device
codecs or introduce a second application. The development version is
`2.0.0.dev0` (Kotlin `2.0.0-dev0`). No remote release or physical device validation
is implied by a successful local build.

```text
Python library / CLI / native Tk desktop / optional localhost Android client
                           |
               DigitalTwin session and recording
                   /                     \
          MCC profile                  MCS profile
          HostPolicy                   independent semantics
          build-292 codec              independent wire codec
          synthetic controller         synthetic controller

Optional MCC CookingHost -> host latch/timers -> original MCC frames -> twin

Backup tab / mc-backup -> read-only session -> GPT/image/ext4 readers
                         |                   -> sanitized inventory/reports
                         + external MCC Backup format adapter (no tool launch)

mc-usb / native Toolkit tab -> explicit-target AdbClient -> Android Package Manager
                           -> AppTransaction -> durable journal / compensation
MCCSerialSession -> explicit SerialTransport (optional pyserial) or RX trace replay
Conformance lab / verifier -> independent recorded references or isolated OEM DEX
```

The PowerBoard endpoint accepts selected original binary frames. High-level
MCC command construction applies documented host policy; `feed()` bypasses that
policy so a controller experiment is not confused with app behavior. Optional
`CookingHost` represents the app latch/timer layer with explicit virtual time.
Neither layer proves firmware interlocks. The independent MCS profile is not
inferred from the MCC backup.

Firmware readers operate on bounded file windows. No image is mounted or
executed. The backup integration reads the external tool's output format and
known archive hash; it imports no GPL implementation into the MIT SDK. Personal
userdata is hashed for integrity and inspected only for fixed filesystem
allocation metadata. System APKs are opaque files for inventory hashing, never
parsed for manifests, signatures, classes or resources.

The Tk Backup panel runs file work in one bounded worker, sends progress/results
through a bounded queue, and cancels on close. Workers never manipulate widgets.
Reports exclude device identifiers, filesystem UUIDs, boot command lines and
absolute workstation paths. Report export creates a new file outside the
source session. Normal desktop startup performs no device discovery, ADB call,
network bind or backup-file read.

The USB component now has an explicit-target ADB executor for user-app and
supported-setting changes, plus durable write-ahead rollback. Legacy sandbox
rehearsal is kept separate. Package Manager checks signatures; system/OEM
replacement and general private-app-data restoration are not supported.
The native Toolkit uses the same APIs, with one bounded worker per panel.
The [USB guide](docs/usb-toolkit.md) describes remaining launcher limitations.
Serial monitoring is receive-only unless active mode is deliberately enabled;
no firmware/partition writer is supplied. The independent
[OEM probe](docs/oem-conformance.md) directly executes original DEX on an
explicit API 23 emulator without a Digital Twin or SDK codec dependency.

See [OEM policy](docs/mcc-oem-policy.md), [backup](docs/backup.md),
[recovery scope](docs/recovery.md), [existing architecture](docs/architecture.md)
and [evidence](docs/evidence.md).
