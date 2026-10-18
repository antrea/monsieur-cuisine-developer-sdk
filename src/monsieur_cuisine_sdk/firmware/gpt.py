"""GUID Partition Table reader and validator (UEFI 2.x, section 5.3).

Read-only. Every size taken from the disk is bounded before it is used for a
read, so a damaged or hostile image cannot make the parser allocate gigabytes.
"""
from __future__ import annotations

import struct
import uuid
import zlib
from dataclasses import dataclass, field

SIGNATURE = b"EFI PART"
HEADER_FORMAT = "<8sIIIIQQQQ16sQIII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 92
MAX_ENTRIES = 4096
MAX_ENTRY_SIZE = 4096


@dataclass(frozen=True)
class GptHeader:
    revision: int
    header_size: int
    header_crc: int
    header_crc_ok: bool
    current_lba: int
    backup_lba: int
    first_usable_lba: int
    last_usable_lba: int
    disk_guid: str
    entries_lba: int
    entry_count: int
    entry_size: int
    entries_crc: int


@dataclass(frozen=True)
class GptPartition:
    index: int
    name: str
    type_guid: str
    unique_guid: str
    first_lba: int
    last_lba: int
    attributes: int

    def offset(self, sector: int) -> int:
        return self.first_lba * sector

    def size(self, sector: int) -> int:
        return (self.last_lba - self.first_lba + 1) * sector


@dataclass
class GptTable:
    header: GptHeader
    partitions: list[GptPartition]
    entries_raw: bytes
    entries_crc_ok: bool
    sector: int
    problems: list[str] = field(default_factory=list)

    def by_name(self) -> dict[str, GptPartition]:
        return {p.name: p for p in self.partitions}


def _guid(raw: bytes) -> str:
    return str(uuid.UUID(bytes_le=bytes(raw)))


def parse_header(raw: bytes) -> GptHeader:
    """Parse one GPT header sector. Raises ValueError when it is not a GPT header."""
    if len(raw) < HEADER_SIZE or raw[:8] != SIGNATURE:
        raise ValueError("no GPT signature")
    (_, revision, header_size, header_crc, _reserved, current, backup, first_usable, last_usable,
     disk_guid, entries_lba, count, entry_size, entries_crc) = struct.unpack_from(HEADER_FORMAT, raw)
    if not HEADER_SIZE <= header_size <= len(raw):
        raise ValueError(f"GPT header size {header_size} out of range")
    zeroed = bytearray(raw[:header_size])
    zeroed[16:20] = b"\0\0\0\0"
    return GptHeader(revision, header_size, header_crc, zlib.crc32(zeroed) == header_crc, current, backup,
                     first_usable, last_usable, _guid(disk_guid), entries_lba, count, entry_size, entries_crc)


def parse_entries(raw: bytes, header: GptHeader) -> list[GptPartition]:
    partitions = []
    for index in range(header.entry_count):
        entry = raw[index * header.entry_size:(index + 1) * header.entry_size]
        if len(entry) < 128:
            raise ValueError("GPT entry table truncated")
        if entry[:16] == b"\0" * 16:
            continue
        first, last, attributes = struct.unpack_from("<QQQ", entry, 32)
        name = entry[56:128].decode("utf-16-le", errors="replace").split("\0", 1)[0]
        partitions.append(GptPartition(index, name, _guid(entry[:16]), _guid(entry[16:32]), first, last, attributes))
    return partitions


def read_table(read_at, *, sector: int = 512, header_lba: int = 1, disk_sectors: int | None = None) -> GptTable:
    """Read the GPT whose header is at ``header_lba``.

    ``read_at(offset, length)`` returns bytes (shorter at end of data). When
    ``disk_sectors`` is known, LBAs are checked against the disk size.
    """
    header = parse_header(read_at(header_lba * sector, sector))
    if not 1 <= header.entry_count <= MAX_ENTRIES:
        raise ValueError(f"GPT entry count {header.entry_count} out of range")
    if header.entry_size < 128 or header.entry_size % 128 or header.entry_size > MAX_ENTRY_SIZE:
        raise ValueError(f"GPT entry size {header.entry_size} invalid")
    length = header.entry_count * header.entry_size
    raw = read_at(header.entries_lba * sector, length)
    if len(raw) != length:
        raise ValueError("GPT entry table truncated")
    table = GptTable(header, parse_entries(raw, header), raw, zlib.crc32(raw) == header.entries_crc, sector)
    table.problems.extend(check_table(table, header_lba=header_lba, disk_sectors=disk_sectors))
    return table


def check_table(table: GptTable, *, header_lba: int, disk_sectors: int | None) -> list[str]:
    """Structural checks; returns human-readable problems (empty when sound)."""
    h, problems = table.header, []
    if not h.header_crc_ok:
        problems.append("header CRC32 mismatch")
    if not table.entries_crc_ok:
        problems.append("entry table CRC32 mismatch")
    if h.current_lba != header_lba:
        problems.append(f"header says it is at LBA {h.current_lba}, read from LBA {header_lba}")
    if h.first_usable_lba > h.last_usable_lba:
        problems.append("first usable LBA after last usable LBA")
    if disk_sectors is not None:
        for name, lba in (("backup", h.backup_lba), ("last usable", h.last_usable_lba)):
            if lba >= disk_sectors:
                problems.append(f"{name} LBA {lba} beyond the disk ({disk_sectors} sectors)")
    ordered = sorted(table.partitions, key=lambda p: p.first_lba)
    for p in ordered:
        if p.last_lba < p.first_lba:
            problems.append(f"{p.name}: last LBA before first LBA")
        if p.first_lba < h.first_usable_lba or p.last_lba > h.last_usable_lba:
            problems.append(f"{p.name}: outside the usable LBA range")
    for before, after in zip(ordered, ordered[1:]):
        if after.first_lba <= before.last_lba:
            problems.append(f"{before.name} overlaps {after.name}")
    names = [p.name for p in table.partitions]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"duplicate partition name {name!r}")
    return problems


def gaps(table: GptTable, disk_sectors: int) -> list[tuple[int, int]]:
    """Unallocated LBA ranges (first, last) between LBA 0 and the end of the disk."""
    result, cursor = [], 0
    for p in sorted(table.partitions, key=lambda p: p.first_lba):
        if p.first_lba > cursor:
            result.append((cursor, p.first_lba - 1))
        cursor = max(cursor, p.last_lba + 1)
    if cursor < disk_sectors:
        result.append((cursor, disk_sectors - 1))
    return result


def build_backup(primary_sector: bytes, entries_raw: bytes, header: GptHeader) -> tuple[bytes, int]:
    """Backup header sector content for a primary header, per UEFI 5.3.2.

    Returns (header bytes, backup entries LBA). The backup entry array starts
    right after the last usable LBA. With the common layout (last usable = backup
    LBA - 33) that is immediately before the backup header; MediaTek devices
    keep a larger reserved tail, and the array then starts at the beginning of it.
    """
    entries_sectors = -(-len(entries_raw) // len(primary_sector))
    entries_lba = header.last_usable_lba + 1
    if entries_lba + entries_sectors > header.backup_lba:
        raise ValueError("backup entry array would overlap the backup header")
    raw = bytearray(primary_sector)
    struct.pack_into("<I", raw, 16, 0)
    struct.pack_into("<QQ", raw, 24, header.backup_lba, header.current_lba)
    struct.pack_into("<Q", raw, 72, entries_lba)
    struct.pack_into("<I", raw, 16, zlib.crc32(bytes(raw[:header.header_size])))
    return bytes(raw), entries_lba


def protective_mbr_ok(sector0: bytes) -> bool:
    """True when LBA 0 is a protective MBR (boot signature and a type 0xEE entry)."""
    if len(sector0) < 512 or sector0[510:512] != b"\x55\xaa":
        return False
    return any(sector0[446 + 16 * i + 4] == 0xEE for i in range(4))
