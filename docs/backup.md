# MCC Backup & Recovery Manager

Normal SDK/Tk startup opens no device and launches no external program. The
file workflow verifies, imports, compares and materializes MCC Backup 1.x
sessions using the standard library. A separate explicit action can provision
the owner's known external tool and run its original file-only verifier. The
SDK never installs a USB driver or mounts an image automatically.

```sh
mc-backup verify SESSION --output ../verification.json
mc-backup inventory SESSION --output ../inventory.json
mc-backup report SESSION --output ../combined-report.json
mc-backup compare SESSION SECOND_SESSION --output ../comparison.json
mc-backup import-backup BACKUP.zip NEW_PRIVATE_IMPORT
mc-backup stage NEW_PRIVATE_IMPORT/backup_session NEW_PRIVATE_STAGE
```

`python -m monsieur_cuisine_sdk.backup.cli` is the equivalent module entry point.
`SESSION` is a local `backup_session` directory with `SHA256SUMS.txt`,
`gpt_primary.bin`, boot areas and partition files. `--no-reconstruct` skips the
potentially long full-area reconstruction on `verify`/`report`; this is explicitly
a narrower check. The output must be a new file outside the session. Omit
`--output` to print JSON. Exit status is 0 on a successful check, 1 on verification
failure, 2 on invalid input/output. `mc-sdk` still requires `--model`.

```python
from monsieur_cuisine_sdk.backup.verify import verify_session
from monsieur_cuisine_sdk.backup.inventory import inventory_session
from monsieur_cuisine_sdk.backup.external import MCCBackupAdapter

verification = verify_session("SESSION", progress=print)
inventory = inventory_session("SESSION").to_dict()
session = MCCBackupAdapter.import_session("SESSION")  # no copy, move or execution
tool = MCCBackupAdapter("MCCBackup_1.0_tool.zip").inspect()
print(verification.passed, tool["release_verified"])
```

`inspect()` hashes the selected tool archive against the known MCC Backup 1.0
release, validates ZIP entry paths/bounds and identifies the external GPL scope.
Selecting an installation folder lists only explicit expected files and cannot
establish known-release integrity by itself. Nothing is automatically searched
outside the user-selected location; no executable is launched. `import_session`
opens a read-only format model, not a new backup acquisition.

## Import, extract and stage

`import-backup SOURCE NEW_DIRECTORY` supports a session folder, a ZIP containing
a session, or a raw user-area image with both boot areas supplied explicitly:

```sh
mc-backup import-backup USER_AREA.bin NEW_RAW_IMPORT --boot1 BOOT1.bin --boot2 BOOT2.bin
```

For a raw image, add `--sha256` with its expected 64-digit hexadecimal digest
when an independent recorded reference exists. Otherwise the new manifest
proves copy integrity, not OEM authenticity. Raw import validates both GPTs,
copies the real full-image bytes, extracts every actual partition and creates
manifests, then independently verifies the resulting session.

ZIP import rejects unsafe/nonportable names, special files, case collisions,
encrypted entries, file/directory conflicts and size/count violations before
creating output. Default bounds are 100,000 members, 32 GiB per member and
64 GiB total. CRCs are checked during extraction. If the archive contains
several sessions, specify `--session-member RELATIVE_DIRECTORY`; no arbitrary
session is selected. Unrelated archive folders are not extracted.

Output always goes into a **new private directory**, with `backup_session/`
and `import-status.json`. A directory is complete only after independent
validation succeeds. Failed/cancelled copies remain marked as such; they are
not silently reused or deleted. All output may contain personal disk data and
must stay out of Git. Folder copies omit unreferenced device logs/identifiers;
ZIP session imports preserve the selected session, including its private logs.

`stage` copies a validated session and materializes its missing full user area
using the recorded whole-area hash and the same `ImageRecovery` engine as the
Recovery Manager. It never uses writable hard links to the source. Plan for
space for the full image **plus** partition copies. The image-writing substep
retains a resumable recovery journal, while a failed overall import must not be
treated as a complete session. Do not overwrite a partial import to retry.

```python
from monsieur_cuisine_sdk.backup.importer import import_backup, copy_session
from monsieur_cuisine_sdk.backup.compare import compare_sessions

result = import_backup("BACKUP.zip", "NEW_IMPORT", progress=print)
staged = copy_session("NEW_IMPORT/backup_session", "NEW_STAGE", materialize=True)
comparison = compare_sessions("NEW_IMPORT/backup_session", "NEW_STAGE/backup_session")
```

These APIs also accept `cancelled=lambda: False` and optional `progress` callbacks.
Comparison validates both backups before comparing GPT layout, partition/boot
content and selected version/model properties. Matching files are never
reported as proof of hardware compatibility.

## Discarding SDK outputs

```sh
mc-backup discard NEW_PRIVATE_IMPORT            # describes the folder, deletes nothing
mc-backup discard NEW_PRIVATE_IMPORT --yes      # deletes an incomplete/failed/interrupted output
mc-backup discard NEW_STAGE --yes --include-complete
```

`discard` removes only a directory whose top level carries the SDK's own
marker (`import-status.json` from imports and stages, or `image-transaction.json`
from file recoveries). Source sessions, plain folders, unknown markers, links,
junctions and special files are refused and nothing is deleted. A complete
output is kept unless `--include-complete` is given. Deletion stops cleanly on
cancellation, leaving the remainder in place. `backup.cleanup.discard_output`
is the API; the native Backup tab's **Discard output** button deletes the folder
named in the output field after a confirmation and never a complete one.

## Original external verifier

```sh
mc-backup provision-tool MCCBackup_1.0_tool.zip NEW_TOOL_SOURCE
mc-backup external-verify MCCBackup_1.0_tool.zip NEW_STAGE/backup_session --installation NEW_TOOL_SOURCE --python python --reports NEW_PRIVATE_REPORTS
```

`MCCBackupRuntime` checks the pinned original distribution and **all** installed
files before execution. It rejects changes, unknown files and links. Provision
extracts source files only; it never installs dependencies or drivers. The
original `verify_offline.py` runs in a separate selected Python process after
bounded GPT preflight. Its report and actual exit code determine success; a
stray printed OK cannot hide a FAIL. Output reports must be in a new directory
outside the session. The verifier requires a materialized full image: use
`stage` first if the original ZIP only carries partition pieces.

`offline_verify(..., python=..., cancelled=..., progress=..., timeout=3600)`
supports cancellation and bounded execution, terminating only its own child
process if cancelled or timed out. It never communicates with USB.

The separate low-level `start_acquisition(..., device_reads=True)` API launches
the original device-read engine; it is **not** a complete supervised acquisition
workflow yet. Its caller owns the process and must independently validate the
result. The original engine has Windows-specific serial patches, loads a DA
into RAM and changes the watchdog during connection. No physical acquisition
is claimed tested by the offline file verifier. No flash writer is supplied.

## Native desktop

The **Backup** tab has **Private backup files** and **Original external tool**
panels. Verify/Inventory read files; Compare validates two sessions; Import and
Stage write only to a new private directory. For raw import, supply both boot
paths. Export writes the actual completed result outside either source captured
by the operation, even if an input entry was edited afterwards.

The external-tool panel provides real ZIP inspection, source provisioning,
installation verification and an explicit **Run original file verifier** action.
Progress comes from actual work; Cancel is checked between file chunks or
while supervising the verifier process. No acquisition button is shown until
that full workflow is implemented.

## Evidence and privacy

- **Integrity:** streaming SHA-256 comparison with manifests, structural bounds,
  GPT CRCs and duplicate partition comparison.
- **Completeness:** expected partitions/boot areas, sizes and optionally a
  composite full-user-area hash. Zero-filled gaps and synthesized backup GPT are
  assumptions until the recorded whole-area digest matches. RPMB is not covered.
- **Restorability:** unverified. A matching digest does not establish hardware
  recovery, eMMC health, bootloader acceptance or compatibility with another unit.

Inventory classifies firmware/device-unique/personal partitions, reads selected
Android build properties, and hashes regular files under system `/app` and
`/priv-app`. App folder hashes commit to relative names, lengths and file hashes.
It never inspects APK internals or follows filesystem symlinks. Userdata is never
enumerated: only ext4 superblock allocation counters are read for used/free space.
Unknown/encrypted/sparse layouts are not silently treated as verified ext4.

No serial, MAC, eMMC CID, filesystem UUID, private mount path, key or credential is
exported. The selected backup remains private; never add it or its private logs
to Git. The tool's GPL code/binaries are external, not bundled into this MIT SDK.
See [architecture](../ARCHITECTURE.md) and [recovery limits](recovery.md).
