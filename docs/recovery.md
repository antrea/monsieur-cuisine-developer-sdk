# Recovery scope and verified boundaries

The SDK 2.0 branch does not perform physical restoration. Its supported local
operations are described in [Backup Manager](backup.md) and [USB toolkit](usb-toolkit.md).

| Level | Available implementation | Verification |
|---|---|---|
| Application transaction rollback | In-memory package/launcher baseline, plan application and rollback equality | Automated sandbox tests; no device changes |
| Software/configuration restoration | No device writer; backup metadata can be inspected read-only | Hardware behavior unverified |
| Full firmware restoration | No flasher or executable recovery procedure | Not implemented or tested on hardware |

Integrity means matching recorded hashes and valid structures. Completeness
means the selected files account for the expected areas, subject to missing
RPMB and the evidence for gaps. Restorability additionally requires compatible
hardware, boot/security state and actual successful device recovery. Neither a
full-area hash nor a simulator result establishes that third property.

No signing keys/certificates, security bypasses, partition writers or physical
motor/heater commands are included. Keep original backup archives immutable and
private. The external backup tool is a separate GPL application whose output
format the SDK can inspect; it is never automatically executed.
