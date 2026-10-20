"""External MCC Backup format adapter; never imports or launches the GPL tool."""
from pathlib import Path
import zipfile

from .image import sha256_file
from .session import BackupSession, safe_relative

KNOWN_TOOL_SHA256 = "711b1249b2b2e6d87e15f023b39d472acdf191dbdf642a910aafcfbec05ba9e9"


class MCCBackupAdapter:
    """Explicit user-selected installation/archive; no device discovery or tool launch."""
    def __init__(self, location):
        self.location = Path(location).resolve()

    def inspect(self):
        if self.location.is_dir():
            candidates = [p for p in (self.location / "MCCBackup_1.0_tool.zip",
                                     self.location / "MCCBackup.exe", self.location / "README.md") if p.is_file()]
            return {"format": "external-installation", "files": [p.name for p in candidates],
                    "release_verified": False, "executed": False,
                    "note": "A folder alone does not establish known-release integrity; select the original archive."}
        digest = sha256_file(self.location)
        if not zipfile.is_zipfile(self.location):
            raise ValueError("select a tool ZIP or explicit installation directory")
        with zipfile.ZipFile(self.location) as archive:
            entries = archive.infolist()
            if len(entries) > 100000 or sum(e.file_size for e in entries) > 8 * 1024**3:
                raise ValueError("tool archive inventory bound exceeded")
            for item in entries:
                safe_relative(item.filename.rstrip("/"))
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("tool archive symlink rejected")
        return {"format": "external-tool-archive", "sha256": digest,
                "release_verified": digest == KNOWN_TOOL_SHA256, "entries": len(entries),
                "executed": False, "license": "External MCC Backup/mtkclient GPL-3.0; not vendored"}

    @staticmethod
    def import_session(folder):
        """Open an existing session read-only, without copying or moving images."""
        return BackupSession.open(folder)
