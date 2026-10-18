# Recovery scope and verified boundaries

The SDK 2.0 branch does not perform physical restoration. Its supported local
operations are described in [Backup Manager](backup.md) and [USB toolkit](usb-toolkit.md).

| Level | Available implementation | Verification |
|---|---|---|
| Application transaction rollback | Durable ADB journal, verified removal of added user APKs, supported HOME/settings compensation | Actual API 23 emulator tests including interrupted install/rollback; no physical MCC changes |
| Software/configuration restoration | Supported screen settings restored via ADB; general app data/update recovery unfinished | Actual API 23 settings restoration; MCC hardware unverified |
| Full firmware restoration | No flasher or executable recovery procedure | Not implemented or tested on hardware |

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
