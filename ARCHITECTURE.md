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

mc-usb -> opt-in read-only ADB diagnostics
       -> offline application plan / transaction sandbox / rollback rehearsal
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

The USB component supplies only an allowlisted read executor and a separate
local transaction model. APK/launcher changes can be rehearsed against that
model; there is no write-capable device executor or firmware restore path. This
boundary is visible in the CLI output and [USB guide](docs/usb-toolkit.md).

See [OEM policy](docs/mcc-oem-policy.md), [backup](docs/backup.md),
[recovery scope](docs/recovery.md), [existing architecture](docs/architecture.md)
and [evidence](docs/evidence.md).
