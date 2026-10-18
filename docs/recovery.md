# Recovery scope and verified boundaries

The SDK 2.0 branch does not perform physical restoration. Its supported local
operations are described in [Backup Manager](backup.md) and [USB toolkit](usb-toolkit.md).

| Level | Available implementation | Verification |
|---|---|---|
| Application transaction rollback | Durable ADB journal, verified removal of added user APKs, supported HOME/settings compensation | Actual API 23 emulator tests including interrupted install/rollback; no physical MCC changes |
| Software/configuration restoration | Supported screen settings restored via ADB; general app data/update recovery unfinished | Actual API 23 settings restoration; MCC hardware unverified |
| Full firmware preparation and file restoration | Verified plan and resumable reconstruction into NEW regular image files; physical execution disabled | Whole-user-area file reconstruction, interruption/resume and recorded SHA-256 verified; hardware restoration unverified |

## Verified file restoration

```sh
mc-recovery plan SESSION --destination NEW_PLAN.json
mc-recovery image SESSION --destination NEW_IMAGE_DIRECTORY
mc-recovery image SESSION --destination IMAGE_DIRECTORY --resume
```

`prepare_restore_plan()` checks source hashes, GPT and required partitions,
records user/boot-area operations and leaves `physical_execution_enabled=False`.
It requires a recorded full-user-area digest. `ImageRecovery.prepare()` creates
a private output, plan and durable per-chunk ledger; `execute()` writes real
bytes, handles one uncommitted valid tail after an interruption, verifies the
existing prefix against source and ledger, then checks the final full digest.
The CLI exposes `--chunk-mib`; resume must use the original chunk size.
Incomplete, altered, wrong-source or linked writable files are refused. A
completed image can be re-verified in read-only mode.

The native Toolkit **Recovery** panel calls those same APIs. Prepare validates
and creates a new image transaction; Restore file / resume advances it. Cancel
leaves a journal. This never accepts a physical disk as an output target.
For a full session usable by the original file verifier, use
[`mc-backup stage`](backup.md) instead of manually copying image files.

Integrity means matching recorded hashes and valid structures. Completeness
means the selected files account for the expected areas, subject to missing
RPMB and the evidence for gaps. Restorability additionally requires compatible
hardware, boot/security state and actual successful device recovery. Neither a
full-area hash nor a simulator result establishes that third property.

No OEM signing keys/certificates, security bypasses or partition writers are
included. The optional serial driver exposes controlled active host commands
only after explicit opt-in; it is never used for physical robot tests here.
Keep original backup archives immutable and
private. The external backup tool is a separate GPL application whose output
format the SDK can inspect; it is never automatically executed.
