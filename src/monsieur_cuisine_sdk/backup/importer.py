"""Import private backup files into NEW folders, with bounded I/O and verification.

Inputs are never modified or linked into writable output. ZIP imports select an
unambiguous session; raw-image imports extract actual GPT partitions. A copied
session can optionally materialize a missing whole-user-area image using the
same resumable file recovery implementation as the Recovery Manager.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

from .image import RawImage, sha256_file
from .session import BackupSession, BOOT_AREAS, EXTRACTED, FULL_IMAGE, GPT_PRIMARY, MANIFEST, safe_relative
from .verify import verify_session
from ..firmware import gpt

MAX_TOTAL = 64 * 1024**3
MAX_MEMBER = 32 * 1024**3
MAX_ENTRIES = 100000
CHUNK = 4 * 1024**2
_RESERVED = {"con", "prn", "aux", "nul"} | {f"{base}{n}" for base in ("com", "lpt") for n in range(1, 10)}


def _relative(name):
    path = safe_relative(name)
    for part in path.parts:
        if (part.endswith((".", " ")) or part != part.strip()
                or any(ord(c) < 32 or c in '<>"|?*' for c in part)
                or part.split(".", 1)[0].casefold() in _RESERVED):
            raise ValueError("backup input has a nonportable file name")
    return path


def _regular(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError("only regular backup files are accepted")
    return path, info.st_size


def _new_destination(source, destination, required):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("import requires a NEW private directory")
    source = Path(source).resolve()
    destination = destination.resolve()
    if source.is_dir() and destination.is_relative_to(source):
        raise ValueError("import output must be outside the immutable source")
    if shutil.disk_usage(destination.parent).free < required + 65536:
        raise OSError("insufficient free space for backup import")
    destination.mkdir(mode=0o700)
    _state(destination, "incomplete")
    return destination


def _state(directory, status, **extra):
    from ..recovery import _atomic_json
    _atomic_json(directory / "import-status.json", {"schema": "mcc-backup-import-v1", "status": status, **extra})


def _stream(source, target, size, *, expected=None, progress=None, cancelled=lambda: False):
    target.parent.mkdir(parents=True, exist_ok=True)
    digest, written = hashlib.sha256(), 0
    with target.open("xb") as output:
        while written < size:
            if cancelled():
                raise InterruptedError("backup file import cancelled")
            block = source.read(min(CHUNK, size - written))
            if not block:
                raise ValueError("backup file ended before its declared size")
            output.write(block)
            digest.update(block)
            written += len(block)
            if progress:
                progress(f"Importing file bytes {written}/{size}")
        if source.read(1):
            raise ValueError("backup file exceeds its declared size")
        output.flush(); os.fsync(output.fileno())
    actual = digest.hexdigest()
    if expected is not None and actual != expected:
        raise ValueError("imported bytes do not match the recorded SHA-256")
    return actual


def _copy(source, target, *, expected=None, progress=None, cancelled=lambda: False):
    source, size = _regular(source)
    with source.open("rb") as reader:
        if not stat.S_ISREG(os.fstat(reader.fileno()).st_mode):
            raise ValueError("backup source changed into a nonregular file")
        return _stream(reader, target, size, expected=expected, progress=progress, cancelled=cancelled)


def _finish(directory, kind, *, progress=None, cancelled=lambda: False, **extra):
    report = verify_session(directory / "backup_session", progress=progress, cancelled=cancelled)
    if not report.passed:
        raise ValueError("imported session failed independent validation; output is incomplete")
    result = {"schema": "mcc-backup-import-v1", "passed": True, "complete": True,
              "kind": kind, "session": "backup_session", "verification": report.to_dict(),
              "physical_device_access": False, "source_modified": False,
              "hardware_compatibility": "UNVERIFIED", **extra}
    _state(directory, "complete", result=result)
    return result


def _failed(directory, error):
    # Keep partial output for diagnostics; never erase a directory recursively.
    _state(directory, "interrupted" if isinstance(error, InterruptedError) else "failed")


def copy_session(source, destination, *, materialize=False, progress=None, cancelled=lambda: False):
    """Copy a verified session, excluding unreferenced device logs/identifiers.

    When materialize=True, missing full-image bytes are reconstructed only if
    the recorded whole-area hash agrees. ImageRecovery retains its durable
    journal alongside the output. Every other copied file is re-hashed too.
    """
    session = BackupSession.open(source)
    needs_materialization = materialize and not session.has_full_image
    # ImageRecovery.prepare performs the full independent source verification.
    # Avoid hashing a multi-gigabyte session twice before the first copied byte.
    if not needs_materialization:
        report = verify_session(source, progress=progress, cancelled=cancelled)
        if not report.passed:
            raise ValueError("source session failed validation")
    files = {MANIFEST: None}
    for name, expected in session.manifest.items():
        if name == FULL_IMAGE and not session.has_full_image:
            continue
        files[_relative(name).as_posix()] = expected
    if session.extracted_manifest:
        files[f"{EXTRACTED}/{MANIFEST}"] = None
        files.update({f"{EXTRACTED}/{_relative(name).as_posix()}": value
                      for name, value in session.extracted_manifest.items()})
    if len({name.casefold() for name in files}) != len(files):
        raise ValueError("session contains nonportable case-colliding file names")
    required = sum(_regular(session.path(name))[1] for name in files)
    if needs_materialization:
        from ..recovery import user_area
        required += user_area(session)[0].size
    if len(files) > MAX_ENTRIES or required > MAX_TOTAL:
        raise ValueError("session exceeds the import bounds")
    directory = _new_destination(source, destination, required)
    try:
        target = directory / "backup_session"
        if needs_materialization:
            from ..recovery import ImageRecovery
            recovery = ImageRecovery(source, target, chunk_bytes=CHUNK)
            recovery.prepare(progress=progress, cancelled=cancelled)
            result = recovery.execute(cancelled=cancelled, progress=(lambda done, total: progress(f"Materializing {done}/{total}")) if progress else None)
            if not result["complete"]:
                raise InterruptedError("full-image materialization interrupted; recovery journal is resumable")
        else:
            target.mkdir()
        for name, expected in sorted(files.items()):
            _copy(session.path(name), target / name, expected=expected, progress=progress, cancelled=cancelled)
        (target / "session.json").write_text(json.dumps({"source": "SDK file copy", "commands": session.commands}) + "\n", encoding="utf-8")
        return _finish(directory, "copied-session", progress=progress, cancelled=cancelled,
                       full_image_materialized=(target / FULL_IMAGE).is_file())
    except Exception as error:
        _failed(directory, error)
        raise


def import_archive(source, destination, *, session_member=None, max_total=MAX_TOTAL,
                   max_member=MAX_MEMBER, max_entries=MAX_ENTRIES, progress=None, cancelled=lambda: False):
    """Defensively extract ONE MCC Backup session from a ZIP and validate it.

    session_member is its relative directory inside the archive ('.' for the
    root), required if several candidate sessions exist. Unrelated files are
    not extracted. All member paths/types are checked before output creation.
    Partial/failed imports retain a status file and cannot be reported complete.
    """
    source, _ = _regular(source)
    if any(type(n) is not int or n <= 0 for n in (max_total, max_member, max_entries)):
        raise ValueError("ZIP bounds must be positive integers")
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > max_entries:
            raise ValueError("ZIP member count exceeds bound")
        names, total = {}, 0
        for item in entries:
            path = _relative(item.filename[:-1] if item.is_dir() else item.filename)
            key = path.as_posix().casefold()
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (key in names or item.flag_bits & 1 or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or item.file_size > max_member or item.file_size < 0):
                raise ValueError("ZIP contains duplicate, encrypted, special or oversized entries")
            names[key] = (path, item)
            total += item.file_size
        if total > max_total:
            raise ValueError("ZIP expands above the total size bound")
        for path, item in names.values():
            for parent in path.parents:
                record = names.get(parent.as_posix().casefold())
                if record and not record[1].is_dir():
                    raise ValueError("ZIP has a file/directory collision")
        candidates = [path.parent for path, item in names.values() if not item.is_dir() and path.name == MANIFEST
                      and (path.parent / GPT_PRIMARY).as_posix().casefold() in names]
        if session_member is None:
            if len(candidates) != 1:
                raise ValueError("select an explicit session_member when the ZIP has no unique session")
            selected = candidates[0]
        else:
            selected = PurePosixPath(".") if session_member == "." else _relative(session_member)
            if selected not in candidates:
                raise ValueError("selected archive member is not a backup session")
        members = [(path.relative_to(selected), item) for path, item in names.values()
                   if path.is_relative_to(selected) and path != selected]
        required = sum(item.file_size for _, item in members)
        archive_hash = sha256_file(source, cancelled=cancelled)
        directory = _new_destination(source, destination, required)
        try:
            target = directory / "backup_session"
            target.mkdir()
            for relative, item in members:
                output = target.joinpath(*relative.parts)
                if item.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                else:
                    with archive.open(item) as reader:
                        _stream(reader, output, item.file_size, progress=progress, cancelled=cancelled)
            return _finish(directory, "zip-session", progress=progress, cancelled=cancelled, archive_sha256=archive_hash)
        except Exception as error:
            _failed(directory, error)
            raise


def import_raw_image(source, destination, *, boot1, boot2, expected_sha256=None,
                     progress=None, cancelled=lambda: False):
    """Copy a raw user area and both boot areas, then extract actual partitions.

    Requires a valid primary AND backup GPT, exact disk size, portable partition
    names and no unsafe layout. Newly computed hashes establish copy integrity,
    not OEM authenticity; supply expected_sha256 for an independent reference.
    """
    source, size = _regular(source)
    areas = [_regular(path) for path in (boot1, boot2)]
    if size > MAX_MEMBER or any(length > 512 * 1024**2 for _, length in areas):
        raise ValueError("raw import exceeds image bounds")
    if expected_sha256 is not None and (len(expected_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256)):
        raise ValueError("expected SHA-256 must contain 64 hexadecimal digits")
    image = RawImage(source)
    if size % 512:
        raise ValueError("raw disk image must be sector aligned")
    table = gpt.read_table(image.read_at, disk_sectors=size // 512)
    backup = gpt.read_table(image.read_at, header_lba=table.header.backup_lba, disk_sectors=size // 512)
    if (table.problems or backup.problems or size != (table.header.backup_lba + 1) * 512
            or backup.entries_raw != table.entries_raw or backup.header.disk_guid != table.header.disk_guid):
        raise ValueError("raw disk GPT/size validation failed")
    for part in table.partitions:
        if _relative(part.name).name != part.name or len(part.name) > 64 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in part.name):
            raise ValueError("raw image has an unsupported partition name")
    if len({p.name.casefold() for p in table.partitions}) != len(table.partitions):
        raise ValueError("raw image has colliding partition names")
    primary_bytes = max(1024, table.header.entries_lba * 512 + len(table.entries_raw))
    required = size + primary_bytes + sum(length for _, length in areas) + sum(p.size(512) for p in table.partitions)
    if primary_bytes > table.header.first_usable_lba * 512 or required > MAX_TOTAL:
        raise ValueError("raw import size/layout exceeds bounds")
    directory = _new_destination(source, destination, required)
    try:
        target = directory / "backup_session"
        target.mkdir()
        full_hash = _copy(source, target / FULL_IMAGE, expected=expected_sha256.lower() if expected_sha256 else None,
                          progress=progress, cancelled=cancelled)
        # Extract from the newly copied bytes, not a source that could change.
        copied = RawImage(target / FULL_IMAGE)
        sums = {FULL_IMAGE: full_hash}
        primary = copied.read_at(0, primary_bytes)
        (target / GPT_PRIMARY).write_bytes(primary)
        sums[GPT_PRIMARY] = hashlib.sha256(primary).hexdigest()
        for name, (path, _) in zip(BOOT_AREAS, areas):
            sums[name] = _copy(path, target / name, progress=progress, cancelled=cancelled)
        extracted = {}
        for part in table.partitions:
            with (target / FULL_IMAGE).open("rb") as reader:
                reader.seek(part.offset(512))
                # Limit the stream to the exact partition, excluding next bytes.
                class Slice:
                    remaining = part.size(512)
                    def read(self, length):
                        data = reader.read(min(length, self.remaining))
                        self.remaining -= len(data)
                        return data
                extracted[part.name + ".bin"] = _stream(Slice(), target / EXTRACTED / (part.name + ".bin"),
                    part.size(512), progress=progress, cancelled=cancelled)
        for name, manifest in ((MANIFEST, sums), (f"{EXTRACTED}/{MANIFEST}", extracted)):
            (target / name).write_text("".join(f"{value}  {key}\n" for key, value in sorted(manifest.items())), encoding="ascii")
        (target / "session.json").write_text(json.dumps({"source": "SDK raw file import", "commands": []}) + "\n", encoding="utf-8")
        return _finish(directory, "raw-image", progress=progress, cancelled=cancelled,
                       independent_hash_provided=expected_sha256 is not None)
    except Exception as error:
        _failed(directory, error)
        raise


def import_backup(source, destination, *, materialize=False, session_member=None,
                  boot1=None, boot2=None, expected_sha256=None, progress=None, cancelled=lambda: False):
    """Unified entry point for session folders, ZIP sessions and raw disk images."""
    source = Path(source)
    shared = {"progress": progress, "cancelled": cancelled}
    if source.is_dir():
        if boot1 is not None or boot2 is not None or expected_sha256 is not None or session_member is not None:
            raise ValueError("raw/ZIP import options do not apply to a session folder")
        return copy_session(source, destination, materialize=materialize, **shared)
    source, _ = _regular(source)
    if zipfile.is_zipfile(source):
        if boot1 is not None or boot2 is not None or expected_sha256 is not None:
            raise ValueError("raw image import options do not apply to a ZIP")
        if materialize:
            raise ValueError("import the ZIP first, then materialize its session into a new folder")
        return import_archive(source, destination, session_member=session_member, **shared)
    if boot1 is None or boot2 is None:
        raise ValueError("raw image import requires explicit boot1 and boot2 files")
    if materialize or session_member is not None:
        raise ValueError("session/ZIP options do not apply to a raw image")
    return import_raw_image(source, destination, boot1=boot1, boot2=boot2, expected_sha256=expected_sha256, **shared)
