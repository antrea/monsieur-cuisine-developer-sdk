"""Verified recovery planning and resumable restoration to NEW image files only.

There is deliberately no block-device/flash executor. The image transaction
creates its own output in a new directory, journals each durable chunk, verifies
the existing prefix on resume, and validates the final full-area digest.
Integrity of that file is distinct from a physically bootable/recoverable MCC.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from .backup.image import RawImage, sha256_file
from .backup.session import BackupSession, FULL_IMAGE, GPT_PRIMARY, BOOT_AREAS
from .backup.verify import compose_user_area, verify_session
from .firmware import gpt


def _atomic_json(path, data):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".recovery-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, sort_keys=True, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def user_area(session):
    primary = RawImage(session.path(GPT_PRIMARY))
    table = gpt.read_table(primary.read_at)
    if table.problems:
        raise ValueError("invalid backup GPT")
    image = RawImage(session.path(FULL_IMAGE)) if session.has_full_image else compose_user_area(session, table, primary.read_at(512, 512))
    return image, table


def prepare_restore_plan(folder, *, progress=None, cancelled=lambda: False):
    """Validate the source and prepare a non-executable physical restore plan."""
    session = BackupSession.open(folder)
    verification = verify_session(folder, progress=progress, cancelled=cancelled)
    if not verification.passed:
        raise ValueError("backup validation failed; no recovery output prepared")
    expected = session.manifest.get(FULL_IMAGE)
    if expected is None:
        raise ValueError("a recorded full-area SHA-256 is required")
    image, table = user_area(session)
    operations = [{"area": "user", "bytes": image.size, "sha256": expected}]
    for name in BOOT_AREAS:
        path = session.path(name)
        operations.append({"area": name, "bytes": path.stat().st_size,
                           "sha256": sha256_file(path, cancelled=cancelled)})
    names = {part.name for part in table.partitions}
    required = {"boot", "recovery", "system", "userdata", "lk"}
    return {"schema": "mcc-recovery-plan-v1", "source_verified": True,
            "source_manifest_sha256": sha256_file(session.path("SHA256SUMS.txt")),
            "user_area_bytes": image.size, "user_area_sha256": expected,
            "operations": operations,
            "partitions": [{"name": p.name, "offset": p.offset(512), "bytes": p.size(512)} for p in table.partitions],
            "mcc_required_partitions_present": required.issubset(names),
            "missing_mcc_partitions": sorted(required - names),
            "physical_execution_enabled": False, "hardware_compatibility": "UNVERIFIED",
            "restorability": "UNVERIFIED: no physical recovery performed",
            "limitations": ["RPMB is absent", "target board/storage identity must be checked independently",
                            "factory reset is not firmware restoration", "no guarantee of recovery from every brick"]}


class ImageRecovery:
    """Resumable copy of a verified full user area into a newly created folder.

    This is a real file restoration, not a fake hardware writer. Incomplete
    output must never be consumed without checking journal status and SHA-256.
    A power loss between data fsync and ledger fsync can leave one uncommitted
    tail; resume validates it against source before truncating that tail.
    """
    def __init__(self, folder, output_directory, *, chunk_bytes=1024 * 1024):
        if type(chunk_bytes) is not int or not 512 <= chunk_bytes <= 16 * 1024**2:
            raise ValueError("recovery chunk must be 512 bytes..16 MiB")
        self.session = BackupSession.open(folder)
        self.directory = Path(output_directory).resolve()
        if self.directory.is_relative_to(self.session.root):
            raise ValueError("recovery output must be outside the immutable source session")
        self.chunk_bytes = chunk_bytes
        self.image, self.table = user_area(self.session)
        if (self.image.size + chunk_bytes - 1) // chunk_bytes > 100000:
            raise ValueError("choose larger chunks for this image")
        self.output = self.directory / FULL_IMAGE
        self.journal = self.directory / "image-transaction.json"
        self.ledger = self.directory / "durable-chunks.jsonl"

    def prepare(self, *, progress=None, cancelled=lambda: False):
        if self.directory.exists():
            raise ValueError("select a NEW output directory")
        plan = prepare_restore_plan(self.session.root, progress=progress, cancelled=cancelled)
        self.directory.mkdir()
        _atomic_json(self.directory / "restore-plan.json", plan)
        _atomic_json(self.journal, {"schema": "mcc-image-recovery-v1", "status": "prepared",
                                  "bytes": self.image.size, "sha256": plan["user_area_sha256"],
                                  "source_manifest_sha256": plan["source_manifest_sha256"], "chunk_bytes": self.chunk_bytes})
        with self.output.open("xb"):
            pass
        with self.ledger.open("x", encoding="utf-8"):
            pass
        return plan

    def _load(self):
        for path in (self.journal, self.ledger, self.output):
            if path.is_symlink() or not path.is_file():
                raise ValueError("recovery state contains a missing or linked file")
        if self.journal.stat().st_size > 65536 or self.ledger.stat().st_size > 32 * 1024**2:
            raise ValueError("recovery journal exceeds bounds")
        state = json.loads(self.journal.read_text("utf-8"))
        if (state.get("schema") != "mcc-image-recovery-v1" or state.get("chunk_bytes") != self.chunk_bytes
                or state.get("bytes") != self.image.size or state.get("sha256") != self.session.manifest.get(FULL_IMAGE)
                or state.get("source_manifest_sha256") != sha256_file(self.session.path("SHA256SUMS.txt"))):
            raise ValueError("recovery state/source identity mismatch")
        return state

    def execute(self, *, max_chunks=None, cancelled=lambda: False, progress=None):
        """Restore/resume the new regular file; never accept a device path."""
        if max_chunks is not None and (type(max_chunks) is not int or max_chunks < 1):
            raise ValueError("max_chunks must be positive")
        state = self._load()
        if state["status"] == "complete":
            digest = sha256_file(self.output, cancelled=cancelled)
            if digest != state["sha256"] or self.output.stat().st_size != self.image.size:
                raise ValueError("completed recovery image no longer matches its reference")
            return {"complete": True, "bytes": self.image.size, "sha256": digest,
                    "physical_writes": 0, "hardware_restoration_verified": False}
        # r+b never creates or truncates a path. fstat rejects block/character
        # devices before any write even if an output name was replaced externally.
        with self.output.open("r+b") as output:
            output_stat = os.fstat(output.fileno())
            if not stat.S_ISREG(output_stat.st_mode) or output_stat.st_nlink != 1:
                raise ValueError("only a private regular recovery image without hard links may be written")
            committed = 0
            valid_ledger_bytes = 0
            torn_ledger = False
            with self.ledger.open("rb") as ledger:
                for count, line in enumerate(ledger, 1):
                    if count > 100000 or len(line) > 1024:
                        raise ValueError("invalid recovery ledger")
                    if not line.endswith(b"\n"):
                        torn_ledger = True
                        break
                    entry = json.loads(line)
                    length = entry["bytes"]
                    if (type(length) is not int or not 0 < length <= self.chunk_bytes
                            or entry["offset"] != committed or committed + length > self.image.size):
                        raise ValueError("recovery ledger geometry mismatch")
                    raw = output.read(length)
                    if len(raw) != length or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                        raise ValueError("recovery prefix differs from durable ledger")
                    if raw != self.image.read_at(committed, length):
                        raise ValueError("source content changed after recovery began")
                    committed += length
                    valid_ledger_bytes += len(line)
                    if cancelled():
                        return {"complete": False, "bytes": committed, "resumable": True, "physical_writes": 0}
            tail = output.read(self.chunk_bytes + 1)
            if tail:
                if len(tail) > self.chunk_bytes or tail != self.image.read_at(committed, len(tail)):
                    raise ValueError("uncommitted output tail differs from the source")
                output.truncate(committed)
            if torn_ledger:
                with self.ledger.open("r+b") as ledger:
                    ledger.truncate(valid_ledger_bytes)
                    ledger.flush(); os.fsync(ledger.fileno())
            output.seek(committed)
            state["status"] = "restoring"
            _atomic_json(self.journal, state)
            written = 0
            with self.ledger.open("a", encoding="utf-8", newline="\n") as ledger:
                while committed < self.image.size:
                    if cancelled() or (max_chunks is not None and written >= max_chunks):
                        state["status"] = "interrupted"
                        _atomic_json(self.journal, state)
                        return {"complete": False, "bytes": committed, "resumable": True, "physical_writes": 0}
                    raw = self.image.read_at(committed, min(self.chunk_bytes, self.image.size - committed))
                    if not raw:
                        raise ValueError("short source read during file restoration")
                    output.write(raw); output.flush(); os.fsync(output.fileno())
                    ledger.write(json.dumps({"offset": committed, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}) + "\n")
                    ledger.flush(); os.fsync(ledger.fileno())
                    committed += len(raw); written += 1
                    if progress:
                        progress(committed, self.image.size)
        digest = sha256_file(self.output, cancelled=cancelled)
        if digest != state["sha256"]:
            state["status"] = "failed"
            _atomic_json(self.journal, state)
            raise ValueError("restored file failed full-area SHA-256")
        state["status"] = "complete"
        _atomic_json(self.journal, state)
        return {"complete": True, "bytes": self.image.size, "sha256": digest,
                "physical_writes": 0, "hardware_restoration_verified": False}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Recovery plans and resumable restoration to NEW regular files only")
    parser.add_argument("command", choices=("plan", "image"))
    parser.add_argument("session", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--chunk-mib", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            if args.destination.resolve().is_relative_to(args.session.resolve()):
                raise ValueError("plan must not modify the source session")
            plan = prepare_restore_plan(args.session)
            with args.destination.open("x", encoding="utf-8") as output:
                json.dump(plan, output, indent=2)
            result = plan
        else:
            recovery = ImageRecovery(args.session, args.destination, chunk_bytes=args.chunk_mib * 1024**2)
            if not args.resume:
                recovery.prepare()
            result = recovery.execute()
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError):
        print(json.dumps({"error": "recovery preflight/resume rejected; no device writer is available", "completed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
