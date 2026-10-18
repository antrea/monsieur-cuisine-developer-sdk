# Read-only MCC Backup Manager

The SDK opens an existing MCC Backup 1.x session folder. It never acquires a
device dump, launches the external tool, installs a driver, mounts images or
writes to a device. The Python runtime remains standard-library only.

```sh
mc-backup verify SESSION --output ../verification.json
mc-backup inventory SESSION --output ../inventory.json
mc-backup report SESSION --output ../combined-report.json
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

The native desktop has a **Backup** tab. Choose a session, then **Verify** or
**Inventory**. Progress comes from real reads; Cancel is checked between streaming
chunks. **Export report** writes the actual completed result. There is no device,
restore or simulated acquisition button.

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
