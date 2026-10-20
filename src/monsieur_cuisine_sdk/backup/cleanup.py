"""Explicit removal of output directories this SDK created: imports, stages and file recoveries.

Deletion is opt-in and narrow. A directory qualifies only when its top level
carries the SDK's own status marker (``import-status.json`` or
``image-transaction.json`` with the known schema). Source sessions, arbitrary
folders, links and special files are refused, and a complete output is kept
unless the caller asks for it explicitly.

Links are detected from ``lstat`` rather than ``Path.is_junction()``, which
Python 3.11 lacks: on Windows any reparse point (symbolic link, junction, mount
point) is refused, at the root, during enumeration and again right before each
deletion, so a junction can never redirect a delete outside the output.
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
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_link(path) -> bool:
    """True for a symbolic link and, on Windows, for any reparse point (junctions included).

    Works on every supported Python: ``st_file_attributes`` exists on Windows
    since 3.5, whereas ``Path.is_junction()`` only appeared in 3.12.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def _unlinked_path(root: Path, path: Path) -> bool:
    """True when no component from ``root`` down to ``path`` is a link or reparse point."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    if _is_link(current):
        return False
    for part in relative.parts:
        current = current / part
        if _is_link(current):
            return False
    return True


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
    """Every regular file and folder below ``directory``, checked before anything is deleted.

    A scandir walk that never descends into an entry before ``lstat`` has
    confirmed it is a plain directory (``os.walk`` on Python 3.11 enters
    junctions). Any link, reparse point or special file aborts the whole run.
    """
    files, folders, count = [], [], 0
    pending = [directory]
    while pending:
        folder = pending.pop()
        if _is_link(folder):
            raise ValueError("output contains a link; nothing is deleted")
        folders.append(folder)
        with os.scandir(folder) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError("output directory exceeds the deletion bound")
                item = Path(entry.path)
                if _is_link(item):
                    raise ValueError("output contains a link; nothing is deleted")
                mode = os.lstat(item).st_mode
                if stat.S_ISDIR(mode):
                    pending.append(item)
                elif stat.S_ISREG(mode):
                    files.append(item)
                else:
                    raise ValueError("output contains a special file; nothing is deleted")
        if cancelled():
            raise InterruptedError("discard cancelled before any deletion")
    # Children before parents, so every rmdir meets an empty folder.
    folders.sort(key=lambda path: len(path.parts), reverse=True)
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
        # Re-check the whole chain: a folder replaced by a junction after enumeration must not
        # redirect this delete outside the output.
        if not _unlinked_path(root, item) or not stat.S_ISREG(os.lstat(item).st_mode):
            raise ValueError(f"output changed during discard after {removed_files} files; the rest is kept")
        size = item.lstat().st_size
        try:
            item.unlink()
        except PermissionError:
            os.chmod(item, stat.S_IWRITE | stat.S_IREAD)
            item.unlink()
        removed_files += 1
        removed_bytes += size
    for folder in folders:
        if not _unlinked_path(root, folder):
            raise ValueError("output changed during discard; the remaining folders are kept")
        folder.rmdir()
    return {"kind": info["kind"], "status_before": info["status"], "removed_files": removed_files,
            "removed_bytes": removed_bytes, "removed_directories": len(folders),
            "directory_removed": not root.exists(), "source_modified": False}
