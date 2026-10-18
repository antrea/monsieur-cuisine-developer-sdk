"""Bounded run-as snapshots for explicit, debuggable Android app transactions.

No root, adb backup format, key extraction or system-directory access. Archives
remain private. Native libraries are supplied by the backed-up APK, not copied
from the lib symlink. All other accessible sandbox files, including no_backup
and caches, are covered. Restore uses the SAME installed UID, never pm clear.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path, PurePosixPath
import shlex
import shutil
import stat
import subprocess
import tarfile
import tempfile
import threading
import time

from .adb import AdbError, CapabilityError, package_name
from .backup.image import sha256_file
from .backup.runtime import _stop_process_tree

MAX_DATA = 512 * 1024**2
MAX_FILES = 20000


@contextmanager
def _open_archive(path):
    try:
        with tarfile.open(path, "r:") as archive:
            yield archive
    except (tarfile.TarError, OverflowError) as error:
        raise ValueError("invalid application-data tar archive") from error


def _bounded_headers(path):
    """Bound GNU/PAX metadata before tarfile can allocate an extended record."""
    length = path.stat().st_size
    with path.open("rb") as reader:
        count = 0
        while reader.tell() < length:
            header = reader.read(512)
            if len(header) != 512:
                raise ValueError("truncated application-data tar header")
            if header == bytes(512):
                break
            count += 1
            if count > MAX_FILES * 2:
                raise ValueError("application tar header count exceeds bound")
            field = header[124:136]
            if field[0] & 0x80:
                if field[0] != 0x80:
                    raise ValueError("negative/unsupported tar size")
                size = int.from_bytes(field[1:], "big")
            else:
                try:
                    size = int(field.strip(b" \0") or b"0", 8)
                except ValueError as error:
                    raise ValueError("invalid application tar size") from error
            if size > MAX_DATA or (header[156:157] in (b"x", b"g", b"L", b"K") and size > 1024**2):
                raise ValueError("application tar payload/metadata exceeds bound")
            end = reader.tell() + ((size + 511) // 512) * 512
            if end > length:
                raise ValueError("application tar payload extends past file")
            reader.seek(end)


def _member_path(name):
    while name.startswith("./"):
        name = name[2:]
    name = name.rstrip("/")
    if name in ("", "."):
        return None
    parts = name.split("/")
    if name.startswith("/") or any(p in ("", ".", "..") or "\0" in p or "\\" in p for p in parts):
        raise ValueError("unsafe application-data archive path")
    if parts[0] == "lib":
        raise ValueError("application data archive must exclude the native library link")
    return PurePosixPath(*parts).as_posix()


def archive_inventory(path):
    """Validate an archive without extracting a single host filesystem entry."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DATA:
        raise ValueError("application-data archive exceeds bound or is not a regular file")
    _bounded_headers(path)
    entries, total = {}, 0
    with _open_archive(path) as archive:
        for count, member in enumerate(archive, 1):
            if count > MAX_FILES or not (member.isfile() or member.isdir()) or member.mode & 0o7000:
                raise ValueError("application-data archive contains unsafe types/modes or too many entries")
            if not isinstance(member.mtime, (int, float)) or not 0 <= member.mtime <= 253402300799:
                raise ValueError("application-data modification time is invalid")
            name = _member_path(member.name)
            if name is None:
                if not member.isdir():
                    raise ValueError("archive root must be a directory")
                continue
            if name in entries or member.size < 0:
                raise ValueError("duplicate or invalid application-data entry")
            total += member.size
            if total > MAX_DATA:
                raise ValueError("application data exceeds bound")
            row = {"kind": "file" if member.isfile() else "directory", "mode": member.mode & 0o777}
            if member.isfile():
                digest, got = hashlib.sha256(), 0
                with archive.extractfile(member) as reader:
                    while block := reader.read(64 * 1024):
                        got += len(block); digest.update(block)
                if got != member.size:
                    raise ValueError("truncated application data")
                row.update(size=got, sha256=digest.hexdigest())
            entries[name] = row
    for name in entries:
        for parent in PurePosixPath(name).parents:
            record = entries.get(parent.as_posix())
            if record is not None and record["kind"] != "directory":
                raise ValueError("application archive file/directory collision")
    return {"entries": entries, "data_bytes": total}


def _stream_adb(client, command, destination, *, input_path=None, limit=MAX_DATA, timeout=120):
    """Drain a binary ADB stream with byte/time limits on all supported hosts."""
    prefix = [client.executable, "-P", str(client.server_port), "-s", client.serial]
    destination = Path(destination)
    errors, size = [], [0]
    with tempfile.TemporaryFile() as stderr, destination.open("xb") as output:
        reader = Path(input_path).open("rb") if input_path is not None else None
        process = None
        try:
            process = client.process_factory(prefix + list(command), stdin=reader or subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=stderr, start_new_session=os.name != "nt",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            def drain():
                try:
                    while block := process.stdout.read(64 * 1024):
                        size[0] += len(block)
                        if size[0] > limit:
                            raise ValueError("application-data transfer exceeds byte limit")
                        output.write(block)
                except Exception as error:
                    errors.append(error)
            worker = threading.Thread(target=drain, daemon=True, name="adb-data-pipe")
            worker.start()
            deadline = time.monotonic() + timeout
            try:
                while worker.is_alive():
                    worker.join(.1)
                    if errors:
                        raise errors[0]
                    if time.monotonic() >= deadline:
                        raise TimeoutError("application-data transfer timed out")
                if errors:
                    raise errors[0]
                process.wait(timeout=max(.1, deadline - time.monotonic()))
                if process.returncode:
                    raise AdbError("Android run-as transfer failed; check debugging access and storage")
            finally:
                if process.poll() is None:
                    _stop_process_tree(process)
                worker.join(5)
                process.stdout.close()
                if worker.is_alive():
                    raise AdbError("application-data pipe did not close after process termination")
            output.flush(); os.fsync(output.fileno())
        finally:
            if reader is not None:
                reader.close()
    return size[0]


class RunAsData:
    """Read/write only the selected app's sandbox through Android's run-as gate."""
    def __init__(self, client):
        self.client = client

    def identity(self, package):
        package_name(package)
        self.client._user_package(package)
        try:
            uid = self.client._shell("run-as", package, "id", "-u")
            directory = self.client._shell("run-as", package, "pwd")
        except AdbError as error:
            raise CapabilityError("run-as is unavailable: only accessible debuggable user-app data is supported") from error
        if not uid.isdecimal() or int(uid) < 10000:
            raise CapabilityError("run-as did not select an ordinary user application UID")
        allowed = {"/data/data/" + package, "/data/user/0/" + package}
        if directory not in allowed:
            raise CapabilityError("run-as sandbox directory could not be verified")
        return int(uid)

    def _as(self, package, command, *arguments):
        return self.client._run(["shell", "run-as", package, command, *(shlex.quote(str(value)) for value in arguments)])

    def _tree(self, package, output):
        """NUL paths and separately batched stat output, preserving UTF-8 names."""
        _stream_adb(self.client, ["exec-out", "run-as", package, "find", ".", "-print0"], output, limit=16 * 1024**2)
        raw, result, total = Path(output).read_bytes(), {}, 0
        if not raw.endswith(b"\0"):
            raise ValueError("Android file inventory was incomplete")
        paths, seen = [], set()
        for name in raw[:-1].split(b"\0"):
            name = name.decode("utf-8")
            if name in (".", "./", "lib", "./lib") or name.startswith(("lib/", "./lib/")):
                continue
            name = _member_path(name)
            if name is None or name in seen or len(paths) >= MAX_FILES:
                raise ValueError("unsupported application file inventory")
            paths.append(name); seen.add(name)
        offset = 0
        while offset < len(paths):
            batch, byte_count = [], 0
            while offset < len(paths) and len(batch) < 64:
                name = paths[offset]
                needed = len(shlex.quote("./" + name).encode("utf-8"))
                if batch and byte_count + needed > 8192:
                    break
                batch.append(name); byte_count += needed; offset += 1
            records = [line.strip() for line in self._as(package, "stat", "-c", "%f:%s:%Y",
                       *("./" + name for name in batch)).splitlines() if line.strip()]
            if len(records) != len(batch):
                raise ValueError("Android stat did not return one record per path")
            for name, record in zip(batch, records):
                if not re.fullmatch(r"[0-9a-fA-F]+:[0-9]+:[0-9]+", record):
                    raise ValueError("Android file inventory contains an error or unsupported metadata")
                mode, size, mtime = record.split(":")
                mode, size, mtime = int(mode, 16), int(size), int(mtime)
                if mode & 0o7000 or mtime > 253402300799:
                    raise ValueError("unsupported application file mode/time")
                kind = stat.S_IFMT(mode)
                if kind not in (stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("application contains a link or special file outside APK libraries")
                total += size if kind == stat.S_IFREG else 0
                if total > MAX_DATA:
                    raise ValueError("application file data exceeds bound")
                result[name] = {"mode": mode & 0o777, "size": size if kind == stat.S_IFREG else 0,
                                "mtime": mtime, "kind": "file" if kind == stat.S_IFREG else "directory"}
        return result

    @staticmethod
    def _old_tar_compatible(entries):
        # Android 6 toybox tar aborts on long names, and its legacy headers can
        # corrupt non-ASCII names. Keep the working fast path for simple trees.
        return all(name.isascii() and len(name.encode("ascii")) + 2 <= 99 for name in entries)

    def _capture_files(self, package, tree, archive, temporary):
        with archive.open("xb") as handle, tarfile.open(fileobj=handle, mode="w", format=tarfile.GNU_FORMAT) as output:
            for index, (name, row) in enumerate(tree.items()):
                item = tarfile.TarInfo(name); item.mode = row["mode"]; item.mtime = row["mtime"]
                item.type = tarfile.REGTYPE if row["kind"] == "file" else tarfile.DIRTYPE
                item.size = row["size"]
                if item.isfile():
                    target = temporary / (str(index) + ".file")
                    # exec-in/out preserve argv; unlike `adb shell`, adding our
                    # own shell quotes turns them into literal filename bytes.
                    size = _stream_adb(self.client, ["exec-out", "run-as", package, "cat", "./" + name],
                                       target, limit=row["size"])
                    if size != row["size"]:
                        raise AdbError("application file changed while being captured")
                    with target.open("rb") as reader:
                        output.addfile(item, reader)
                else:
                    output.addfile(item)

    def _restore_files(self, package, archive, temporary):
        from datetime import datetime, timezone
        directories = []
        with _open_archive(archive) as source:
            members = [(member, _member_path(member.name)) for member in source]
            for member, name in sorted(members, key=lambda value: (value[1] or "").count("/")):
                if name is None:
                    continue
                parent = PurePosixPath(name).parent.as_posix()
                if member.isdir():
                    self._as(package, "mkdir", "-p", "./" + name)
                    directories.append((name, member.mode, member.mtime))
                else:
                    if parent != ".":
                        self._as(package, "mkdir", "-p", "./" + parent)
                    local = temporary / "payload.file"
                    with source.extractfile(member) as reader, local.open("wb") as output:
                        shutil.copyfileobj(reader, output, length=64 * 1024)
                    _stream_adb(self.client, ["exec-in", "run-as", package, "dd", "of=./" + name, "bs=65536"],
                                temporary / (str(len(directories)) + "-" + hashlib.sha256(name.encode()).hexdigest() + ".log"),
                                input_path=local, limit=65536)
                    self._as(package, "chmod", format(member.mode & 0o777, "o"), "./" + name)
                    date = datetime.fromtimestamp(int(member.mtime), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    self._as(package, "touch", "-m", "-d", date, "./" + name)
        for name, mode, mtime in sorted(directories, key=lambda value: value[0].count("/"), reverse=True):
            self._as(package, "chmod", format(mode & 0o777, "o"), "./" + name)
            date = datetime.fromtimestamp(int(mtime), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._as(package, "touch", "-m", "-d", date, "./" + name)

    def snapshot(self, package, destination):
        self.client._mutating()
        uid = self.identity(package)
        directory = Path(destination).resolve()
        if directory.exists():
            raise ValueError("application snapshot needs a NEW private directory")
        directory.mkdir(mode=0o700)
        self.client._shell("am", "force-stop", package)
        archive = directory / "data.tar"
        with tempfile.TemporaryDirectory(dir=directory, prefix="capture-") as temporary:
            temporary = Path(temporary)
            tree = self._tree(package, temporary / "tree-before")
            strategy = "android-tar" if self._old_tar_compatible(tree) else "run-as-files"
            if strategy == "android-tar":
                _stream_adb(self.client, ["exec-out", "run-as", package, "tar", "-c", "-f", "-", "--exclude=./lib", "."], archive)
            else:
                self._capture_files(package, tree, archive, temporary)
            if self._tree(package, temporary / "tree-after") != tree:
                raise AdbError("application tree changed while being captured")
        inventory = archive_inventory(archive)
        if set(inventory["entries"]) != set(tree) or any(
                row["mode"] != tree[name]["mode"] or row["kind"] != tree[name]["kind"]
                or (row["kind"] == "file" and row["size"] != tree[name]["size"])
                for name, row in inventory["entries"].items()):
            raise AdbError("Android archive did not preserve file names/types/sizes/modes")
        data = {"schema": "mcc-run-as-snapshot-v1", "package": package, "uid": uid,
                "archive_sha256": sha256_file(archive), "excluded": ["lib (provided by APK)"],
                "capture_strategy": strategy,
                "scope": "accessible sandbox files; no keystore extraction or external-storage backup", **inventory}
        with (directory / "snapshot.json").open("x", encoding="utf-8") as output:
            json.dump(data, output, indent=2)
            output.flush(); os.fsync(output.fileno())
        return data

    @staticmethod
    def load(directory):
        directory = Path(directory)
        manifest = directory / "snapshot.json"
        if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 16 * 1024**2:
            raise ValueError("invalid application snapshot manifest")
        data = json.loads(manifest.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("schema") != "mcc-run-as-snapshot-v1":
            raise ValueError("unsupported application snapshot")
        if type(data.get("uid")) is not int or data["uid"] < 10000:
            raise ValueError("invalid application snapshot UID")
        package_name(data["package"])
        inventory = archive_inventory(directory / "data.tar")
        if sha256_file(directory / "data.tar") != data["archive_sha256"]:
            raise ValueError("application snapshot archive hash mismatch")
        if inventory != {key: data[key] for key in ("entries", "data_bytes")}:
            raise ValueError("application snapshot contents changed")
        return data

    def restore(self, directory, *, workdir):
        """Restore after a same-UID APK rollback; never uninstall or pm clear."""
        data = self.load(directory)
        package = data["package"]
        self.client._mutating()
        if self.identity(package) != data["uid"]:
            raise CapabilityError("application UID changed; data restoration refused")
        self.client._shell("am", "force-stop", package)
        with tempfile.TemporaryDirectory(dir=workdir, prefix="data-restore-") as temporary:
            temporary = Path(temporary)
            # A current snapshot also detects unsafe links/special entries before
            # any removal; callers retain a separate durable rollback safety copy.
            current = self.snapshot(package, temporary / "current")
            top = sorted({PurePosixPath(name).parts[0] for name in current["entries"]})
            canonical = temporary / "canonical.tar"
            with _open_archive(Path(directory) / "data.tar") as original, tarfile.open(canonical, "w", format=tarfile.GNU_FORMAT) as output:
                for member in original:
                    name = _member_path(member.name)
                    if name is None:
                        continue
                    clean = tarfile.TarInfo(name)
                    clean.type = tarfile.DIRTYPE if member.isdir() else tarfile.REGTYPE
                    clean.mode = member.mode & 0o777
                    clean.size = member.size if member.isfile() else 0
                    clean.mtime = max(0, int(member.mtime))
                    if member.isfile():
                        with original.extractfile(member) as reader:
                            output.addfile(clean, reader)
                    else:
                        output.addfile(clean)
            for name in top:
                # Single executable, quoted tokens, and run-as confines cwd/UID.
                self.client._run(["shell", "run-as", package, "rm", "-r", "-f", shlex.quote("./" + name)])
            if self._old_tar_compatible(data["entries"]):
                _stream_adb(self.client, ["exec-in", "run-as", package, "tar", "-x", "-f", "-"],
                            temporary / "restore.log", input_path=canonical, limit=65536)
            else:
                self._restore_files(package, canonical, temporary)
            actual = self.snapshot(package, temporary / "verified")
            if actual["entries"] != data["entries"]:
                raise AdbError("restored application files do not match the snapshot")
        return {"restored": True, "package": package, "same_uid": True,
                "files_verified": len(data["entries"]), "hardware_verified": False}
