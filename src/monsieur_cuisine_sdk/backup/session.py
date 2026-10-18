"""Model of an eMMC backup session folder as written by MCC Backup 1.x (or compatible tools).

Only the documented output layout is read; the GPLv3 tool itself is never
imported. Layout::

    SHA256SUMS.txt                    "<sha256>  <relative path>" for every data file
    emmc_user_full.bin                optional: the whole user area (often left out of archives)
    emmc_boot1.bin, emmc_boot2.bin    eMMC boot areas
    gpt_primary.bin                   first bytes of the user area (protective MBR + primary GPT)
    partitions/<name>.bin             partitions read directly from the device
    partitions_extracted/<name>.bin   partitions cut from the full image (+ its own SHA256SUMS.txt)
    session.json, commands.txt, engine_log.txt, handshake_log.txt   tool metadata
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

FULL_IMAGE = "emmc_user_full.bin"
GPT_PRIMARY = "gpt_primary.bin"
BOOT_AREAS = ("emmc_boot1.bin", "emmc_boot2.bin")
MANIFEST = "SHA256SUMS.txt"
EXTRACTED = "partitions_extracted"
DIRECT = "partitions"
READ_ONLY_COMMANDS = frozenset({"printgpt", "r", "rl", "rf", "rs", "ro"})
_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


def safe_relative(text: str) -> PurePosixPath:
    """A manifest path that stays inside its folder; raises ValueError otherwise."""
    clean = text.strip().replace("\\", "/")
    # Check the raw components: PurePosixPath would silently normalize "a//b" and "a/./b".
    raw_parts = clean.split("/")
    if not clean or clean.startswith("/") or ":" in raw_parts[0] or any(p in ("", ".", "..") for p in raw_parts):
        raise ValueError(f"unsafe manifest path {text!r}")
    return PurePosixPath(clean)


def read_manifest(path: Path) -> dict[str, str]:
    """Parse a sha256sum-style manifest into {relative posix path: lowercase hex}."""
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(f"{path.name}: manifest larger than {MAX_MANIFEST_BYTES} bytes")
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        match = _SUM_LINE.match(line)
        if not match:
            raise ValueError(f"{path.name}:{number}: not a '<sha256>  <path>' line")
        relative = safe_relative(match.group(2)).as_posix()
        if relative in entries:
            raise ValueError(f"{path.name}:{number}: duplicate entry {relative}")
        entries[relative] = match.group(1).lower()
    return entries


@dataclass
class BackupSession:
    root: Path
    manifest: dict[str, str]
    extracted_manifest: dict[str, str]
    metadata: dict
    commands: list[str]
    problems: list[str] = field(default_factory=list)

    @classmethod
    def open(cls, folder) -> "BackupSession":
        root = Path(folder).resolve()
        if not root.is_dir():
            raise ValueError(f"{root} is not a folder")
        problems = []
        manifest = read_manifest(root / MANIFEST) if (root / MANIFEST).is_file() else {}
        if not manifest:
            problems.append(f"{MANIFEST} missing or empty")
        extracted_path = root / EXTRACTED / MANIFEST
        extracted = read_manifest(extracted_path) if extracted_path.is_file() else {}
        metadata = {}
        if (root / "session.json").is_file():
            try:
                metadata = json.loads((root / "session.json").read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as error:
                problems.append(f"session.json unreadable: {error}")
        commands = []
        if (root / "commands.txt").is_file():
            commands = [line.strip() for line in (root / "commands.txt").read_text(encoding="utf-8").splitlines()
                        if line.strip()]
        elif isinstance(metadata.get("commands"), list):
            commands = [str(c) for c in metadata["commands"]]
        return cls(root, manifest, extracted, metadata, commands, problems)

    def path(self, relative: str) -> Path:
        target = (self.root / safe_relative(relative)).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"{relative} escapes the session folder")
        return target

    @property
    def has_full_image(self) -> bool:
        return (self.root / FULL_IMAGE).is_file()

    def partition_file(self, name: str, *, prefer: str = EXTRACTED) -> Path | None:
        for sub in (prefer, DIRECT if prefer == EXTRACTED else EXTRACTED):
            candidate = self.root / sub / f"{name}.bin"
            if candidate.is_file():
                return candidate
        return None

    def non_read_commands(self) -> list[str]:
        """Commands in the session log that are not plain flash reads."""
        return [c for c in self.commands if c.split(" ", 1)[0] not in READ_ONLY_COMMANDS]
