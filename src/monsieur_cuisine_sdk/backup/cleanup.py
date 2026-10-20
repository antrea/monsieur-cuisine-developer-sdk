"""Explicit removal of output directories this SDK created: imports, stages and file recoveries.

Deletion is opt-in and narrow. A directory qualifies only when its top level
carries the SDK's own status marker (``import-status.json`` or
``image-transaction.json`` with the known schema). Source sessions, arbitrary
folders, links and special files are refused, and a complete output is kept
unless the caller asks for it explicitly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

IMPORT_STATUS, IMPORT_SCHEMA = "import-status.json", "mcc-backup-import-v1"
RECOVERY_JOURNAL, RECOVERY_SCHEMA = "image-transaction.json", "mcc-image-recovery-v1"
MARKERS = ((IMPORT_STATUS, IMPORT_SCHEMA, "import"), (RECOVERY_JOURNAL, RECOVERY_SCHEMA, "recovery"))
MAX_ENTRIES = 200_000
MAX_MARKER_BYTES = 1024 * 1024


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def describe_output(directory) -> dict:
    """Identify an SDK-created output directory by its marker; raises ValueError for anything else."""
    directory = Path(directory)
    if _is_link(directory) or not directory.is_dir():
        raise ValueError("output must be an existing directory; links are refused")
    directory = directory.resolve()
    for marker, schema, kind in MARKERS:
        path = directory / marker
        if not path.is_file() or _is_link(path):
            continue
        if path.stat().st_size > MAX_MARKER_BYTES:
            raise ValueError("output marker exceeds bounds")
        data = json.loads(path.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("schema") != schema:
            raise ValueError("output marker has an unknown schema")
        status = data.get("status")
        return {"kind": kind, "status": status if isinstance(status, str) else "unknown",
                "directory": str(directory), "complete": status == "complete"}
    raise ValueError("directory carries no SDK output marker; it is not deleted")


def _enumerate(directory: Path, cancelled):
    files, folders, count = [], [], 0
    for root, names, leaves in os.walk(directory, topdown=False, followlinks=False):
        root = Path(root)
        for name in names + leaves:
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError("output directory exceeds the deletion bound")
            if _is_link(root / name):
                raise ValueError("output contains a link; nothing is deleted")
        for name in leaves:
            item = root / name
            if not stat.S_ISREG(item.lstat().st_mode):
                raise ValueError("output contains a special file; nothing is deleted")
            files.append(item)
        folders.append(root)
        if cancelled():
            raise InterruptedError("discard cancelled before any deletion")
    return files, folders


def discard_output(directory, *, include_complete=False, cancelled=lambda: False) -> dict:
    """Delete an SDK output directory. Returns what was removed; source sessions are never touched."""
    info = describe_output(directory)
    if info["complete"] and not include_complete:
        raise ValueError("output is complete; pass include_complete=True to delete it anyway")
    root = Path(info["directory"])
    files, folders = _enumerate(root, cancelled)
    removed_files = removed_bytes = 0
    for item in files:
        if cancelled():
            raise InterruptedError(f"discard cancelled after {removed_files} files; the rest is kept")
        size = item.lstat().st_size
        try:
            item.unlink()
        except PermissionError:
            os.chmod(item, stat.S_IWRITE | stat.S_IREAD)
            item.unlink()
        removed_files += 1
        removed_bytes += size
    for folder in folders:
        folder.rmdir()
    return {"kind": info["kind"], "status_before": info["status"], "removed_files": removed_files,
            "removed_bytes": removed_bytes, "removed_directories": len(folders),
            "directory_removed": not root.exists(), "source_modified": False}
