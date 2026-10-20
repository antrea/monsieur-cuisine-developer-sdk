"""Privacy-minimized inventory of local backup files, without APK introspection."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..firmware import ext4, gpt
from .image import RawImage
from .session import BackupSession, GPT_PRIMARY

BUILD_KEYS = frozenset({"ro.build.version.release", "ro.build.version.sdk",
                        "ro.build.version.incremental", "ro.product.model",
                        "ro.product.manufacturer", "ro.product.device", "ro.product.board", "ro.hardware"})
PERSONAL = frozenset({"userdata", "cache"})
DEVICE_UNIQUE = frozenset({"nvram", "nvdata", "protect1", "protect2", "proinfo", "persist", "secro", "seccfg"})


@dataclass
class InventoryReport:
    partitions: list[dict] = field(default_factory=list)
    build: dict = field(default_factory=dict)
    apps: list[dict] = field(default_factory=list)
    userdata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return {"schema": "mcc-backup-inventory-v1", "read_only": True,
                "identifiers_included": False, "apk_contents_inspected": False,
                "partitions": self.partitions, "build": self.build, "apps": self.apps,
                "userdata": self.userdata, "warnings": self.warnings}


def privacy_class(name):
    return "personal" if name in PERSONAL else "device-unique" if name in DEVICE_UNIQUE else "firmware"


def filesystem_info(view):
    """Read fixed superblock metadata only, without volume UUID/name/mount paths."""
    sb = ext4.parse_superblock(view.read_at(1024, 1024))
    if not 0 <= sb.free_blocks <= sb.blocks_count or sb.blocks_count * sb.block_size > view.size:
        raise ValueError("invalid filesystem allocation counters")
    return {"type": "ext4", "size_bytes": sb.blocks_count * sb.block_size,
            "used_bytes": (sb.blocks_count - sb.free_blocks) * sb.block_size,
            "free_bytes": sb.free_blocks * sb.block_size, "block_size": sb.block_size,
            "clean": sb.clean}


def inventory_session(folder, *, progress=None, cancelled=lambda: False):
    session = BackupSession.open(folder)
    primary = RawImage(session.path(GPT_PRIMARY))
    table = gpt.read_table(primary.read_at)
    if table.problems:
        raise ValueError("invalid primary GPT; verify the backup before inventory")
    result = InventoryReport()
    for part in table.partitions:
        if cancelled():
            raise ValueError("inventory cancelled")
        row = {"name": part.name, "bytes": part.size(512), "privacy": privacy_class(part.name),
               "present": False, "content": "missing"}
        source = session.partition_file(part.name)
        if source is not None:
            row["present"] = True
            view = RawImage(source)
            if progress:
                progress("Inspecting partition " + part.name)
            try:
                info = filesystem_info(view)
                row["content"] = "ext4"
                if part.name == "userdata":
                    result.userdata = info  # never enumerate personal files
            except ValueError:
                head = view.read_at(0, 8)
                row["content"] = "android-boot" if head == b"ANDROID!" else "raw"
            if part.name == "system" and row["content"] == "ext4":
                _system_inventory(view, result, progress, cancelled)
        result.partitions.append(row)
    return result


def _system_inventory(view, result, progress, cancelled):
    fs = ext4.Ext4(view.read_at, size=view.size)
    try:
        node = fs.lookup("/build.prop")
        if node.kind != "file":
            raise ValueError("build properties must be a regular file")
        text = fs.read_file(node, limit=256 * 1024).decode("utf-8", errors="replace")
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() in BUILD_KEYS:
                result.build[key.strip()] = value.strip()[:256]
    except FileNotFoundError:
        result.warnings.append("system build.prop unavailable")
    for top in ("/app", "/priv-app"):
        try:
            fs.lookup(top)
        except FileNotFoundError:
            continue
        groups = {}
        for index, (path, node) in enumerate(fs.walk(top)):
            if cancelled():
                raise ValueError("inventory cancelled")
            if index >= 100000:
                raise ValueError("system application inventory entry bound exceeded")
            if node.kind != "file":
                continue
            components = path.removeprefix(top + "/").split("/")
            group = groups.setdefault(components[0], {"folder": top + "/" + components[0],
                                                     "bytes": 0, "files": [], "hash": hashlib.sha256()})
            digest = hashlib.sha256()
            if progress:
                progress("Hashing system application " + components[0])
            for chunk in fs.iter_file(node):
                if cancelled():
                    raise ValueError("inventory cancelled")
                digest.update(chunk)
            relative = "/".join(components[1:]) or components[0]
            # Tree digest commits to relative filename, byte length and file hash.
            file_hash = digest.hexdigest()
            group["hash"].update(relative.encode("utf-8") + b"\0" + str(node.size).encode() + b"\0" + bytes.fromhex(file_hash))
            group["files"].append({"name": relative, "bytes": node.size, "sha256": file_hash})
            group["bytes"] += node.size
        for group in groups.values():
            group["sha256"] = group.pop("hash").hexdigest()
            result.apps.append(group)
