"""Read-only ext2/3/4 filesystem reader, written from the kernel's on-disk format documentation.

Supports what Android 4-9 ``make_ext4fs`` images use: 32- and 64-bit group
descriptors, extent trees (including uninitialized extents and holes), classic
block maps, linear and hashed (htree) directories read linearly, fast and slow
symlinks. It never writes and never follows symlinks. Every count read from
the disk is bounded before use, so a damaged image fails with ValueError.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable, Iterator

SUPERBLOCK_OFFSET = 1024
MAGIC = 0xEF53
INCOMPAT_FILETYPE = 0x0002
INCOMPAT_EXTENTS = 0x0040
INCOMPAT_64BIT = 0x0080
INCOMPAT_FLEX_BG = 0x0200
INCOMPAT_INLINE_DATA = 0x8000
EXTENTS_FL = 0x80000
INLINE_DATA_FL = 0x10000000
EXTENT_MAGIC = 0xF30A
S_IFMT, S_IFDIR, S_IFREG, S_IFLNK = 0o170000, 0o040000, 0o100000, 0o120000
MAX_FILE_READ = 512 * 1024 * 1024
MAX_EXTENT_DEPTH = 5
MAX_DIR_ENTRIES = 1_000_000
CHUNK_BLOCKS = 2048
FILE_TYPES = {1: "file", 2: "dir", 3: "chr", 4: "blk", 5: "fifo", 6: "sock", 7: "symlink"}


@dataclass(frozen=True)
class Superblock:
    inodes_count: int
    blocks_count: int
    free_blocks: int
    free_inodes: int
    first_data_block: int
    block_size: int
    blocks_per_group: int
    inodes_per_group: int
    mount_time: int
    write_time: int
    mount_count: int
    state: int
    errors: int
    creator_os: int
    rev_level: int
    inode_size: int
    feature_compat: int
    feature_incompat: int
    feature_ro_compat: int
    uuid: str
    volume_name: str
    last_mounted: str
    desc_size: int
    last_error_time: int

    @property
    def group_count(self) -> int:
        return -(-(self.blocks_count - self.first_data_block) // self.blocks_per_group)

    @property
    def clean(self) -> bool:
        return bool(self.state & 1) and not self.state & 2

    def as_dict(self) -> dict:
        data = dict(self.__dict__)
        data["group_count"], data["clean"] = self.group_count, self.clean
        data["used_bytes"] = (self.blocks_count - self.free_blocks) * self.block_size
        data["size_bytes"] = self.blocks_count * self.block_size
        return data


@dataclass(frozen=True)
class Inode:
    number: int
    mode: int
    uid: int
    gid: int
    size: int
    atime: int
    ctime: int
    mtime: int
    links: int
    flags: int
    block: bytes

    @property
    def kind(self) -> str:
        return {S_IFDIR: "dir", S_IFREG: "file", S_IFLNK: "symlink"}.get(self.mode & S_IFMT, "other")


def parse_superblock(raw: bytes) -> Superblock:
    if len(raw) < 1024:
        raise ValueError("superblock truncated")
    # Offsets 0x00-0x4F of struct ext4_super_block.
    (inodes, blocks_lo, _r_lo, free_lo, free_inodes, first_data, log_block, _log_cluster, per_group,
     _clusters_per_group, inodes_per_group, mtime, wtime, mnt_count, _max_mnt, magic, state, errors,
     _minor, _lastcheck, _interval, creator_os, rev) = struct.unpack_from("<13I6H4I", raw, 0)
    if magic != MAGIC:
        raise ValueError("no ext2/3/4 magic")
    if log_block > 6:
        raise ValueError(f"block size 2^(10+{log_block}) unsupported")
    inode_size = struct.unpack_from("<H", raw, 0x58)[0] if rev >= 1 else 128
    compat, incompat, ro_compat = struct.unpack_from("<III", raw, 0x5C)
    uuid = raw[0x68:0x78].hex()
    volume = raw[0x78:0x88].split(b"\0", 1)[0].decode("utf-8", errors="replace")
    last_mounted = raw[0x88:0xC8].split(b"\0", 1)[0].decode("utf-8", errors="replace")
    desc_size = struct.unpack_from("<H", raw, 0xFE)[0] if incompat & INCOMPAT_64BIT else 32
    blocks_hi = struct.unpack_from("<I", raw, 0x150)[0] if incompat & INCOMPAT_64BIT else 0
    free_hi = struct.unpack_from("<I", raw, 0x158)[0] if incompat & INCOMPAT_64BIT else 0
    error_time = struct.unpack_from("<I", raw, 0x198)[0]
    if not 128 <= inode_size <= 4096 or inode_size & (inode_size - 1):
        raise ValueError(f"inode size {inode_size} invalid")
    if desc_size not in (32, 64) and not (incompat & INCOMPAT_64BIT and 32 <= desc_size <= 1024):
        raise ValueError(f"group descriptor size {desc_size} invalid")
    if not per_group or not inodes_per_group:
        raise ValueError("zero blocks or inodes per group")
    return Superblock(inodes, blocks_lo | blocks_hi << 32, free_lo | free_hi << 32, free_inodes, first_data,
                      1024 << log_block, per_group, inodes_per_group, mtime, wtime, mnt_count, state, errors,
                      creator_os, rev, inode_size, compat, incompat, ro_compat, uuid, volume, last_mounted,
                      desc_size, error_time)


class Ext4:
    """A read-only ext4 filesystem over ``read_at(offset, length) -> bytes``."""

    def __init__(self, read_at: Callable[[int, int], bytes], *, size: int | None = None):
        self._read_at, self.image_size = read_at, size
        self.sb = parse_superblock(read_at(SUPERBLOCK_OFFSET, 1024))
        supported = INCOMPAT_FILETYPE | 0x0004 | INCOMPAT_EXTENTS | INCOMPAT_64BIT | INCOMPAT_FLEX_BG
        if self.sb.feature_incompat & ~supported:
            raise ValueError("unsupported ext4 incompatible features")
        if size is not None and self.sb.blocks_count * self.sb.block_size > size:
            raise ValueError("filesystem larger than its container")
        if self.sb.group_count > 1 << 22:
            raise ValueError("implausible group count")
        table_block = self.sb.first_data_block + 1
        raw = self.read_blocks(table_block, -(-self.sb.group_count * self.sb.desc_size // self.sb.block_size))
        self._inode_tables = []
        for group in range(self.sb.group_count):
            entry = raw[group * self.sb.desc_size:(group + 1) * self.sb.desc_size]
            low = struct.unpack_from("<I", entry, 8)[0]
            high = struct.unpack_from("<I", entry, 0x28)[0] if self.sb.desc_size >= 64 else 0
            self._inode_tables.append(low | high << 32)

    # -- blocks and inodes ------------------------------------------------
    def read_blocks(self, block: int, count: int = 1) -> bytes:
        size = self.sb.block_size
        if block < 0 or count < 0 or block + count > self.sb.blocks_count or count * size > MAX_FILE_READ:
            raise ValueError(f"block range {block}+{count} outside the filesystem")
        data = self._read_at(block * size, count * size)
        if len(data) != count * size:
            raise ValueError(f"short read at block {block}")
        return data

    def inode(self, number: int) -> Inode:
        if not 1 <= number <= self.sb.inodes_count:
            raise ValueError(f"inode {number} out of range")
        group, index = divmod(number - 1, self.sb.inodes_per_group)
        if group >= len(self._inode_tables):
            raise ValueError("inode group outside the descriptor table")
        offset = self._inode_tables[group] * self.sb.block_size + index * self.sb.inode_size
        raw = self._read_at(offset, self.sb.inode_size)
        if len(raw) < 128:
            raise ValueError(f"inode {number} truncated")
        mode, uid, size_lo, atime, ctime, mtime, _dtime, gid, links = struct.unpack_from("<HHIIIIIHH", raw, 0)
        flags = struct.unpack_from("<I", raw, 0x20)[0]
        size_hi = struct.unpack_from("<I", raw, 0x6C)[0]
        uid_hi, gid_hi = struct.unpack_from("<HH", raw, 0x78)
        return Inode(number, mode, uid | uid_hi << 16, gid | gid_hi << 16, size_lo | size_hi << 32,
                     atime, ctime, mtime, links, flags, raw[0x28:0x28 + 60])

    def _extent_runs(self, node: bytes, depth_left: int) -> Iterator[tuple[int, int, int, bool]]:
        """(logical block, physical block, length, initialized) for each leaf extent."""
        magic, entries, _max, depth = struct.unpack_from("<HHHH", node, 0)
        if magic != EXTENT_MAGIC:
            raise ValueError("bad extent header")
        if depth > MAX_EXTENT_DEPTH or depth_left < 0 or entries > (len(node) - 12) // 12:
            raise ValueError("implausible extent tree")
        for i in range(entries):
            base = 12 + 12 * i
            if depth == 0:
                logical, length, start_hi, start_lo = struct.unpack_from("<IHHI", node, base)
                initialized = length <= 32768
                yield logical, start_lo | start_hi << 32, length if initialized else length - 32768, initialized
            else:
                _logical, leaf_lo, leaf_hi = struct.unpack_from("<IIH", node, base)
                yield from self._extent_runs(self.read_blocks(leaf_lo | leaf_hi << 32), depth_left - 1)

    def _map_runs(self, inode: Inode) -> Iterator[tuple[int, int, int, bool]]:
        """Runs for a classic direct/indirect block map."""
        pointers = struct.unpack_from("<15I", inode.block)
        per_block = self.sb.block_size // 4
        logical = 0
        for p in pointers[:12]:
            if p:
                yield logical, p, 1, True
            logical += 1

        def walk(block, level, start):
            if not block:
                return
            children = struct.unpack(f"<{per_block}I", self.read_blocks(block))
            span = per_block ** (level - 1)
            for i, child in enumerate(children):
                if level == 1:
                    if child:
                        yield start + i, child, 1, True
                else:
                    yield from walk(child, level - 1, start + i * span)

        for level, pointer in enumerate(pointers[12:], 1):
            yield from walk(pointer, level, logical)
            logical += per_block ** level

    def runs(self, inode: Inode) -> list[tuple[int, int, int, bool]]:
        if inode.flags & INLINE_DATA_FL:
            raise ValueError(f"inode {inode.number}: inline data is not supported")
        source = self._extent_runs(inode.block, MAX_EXTENT_DEPTH) if inode.flags & EXTENTS_FL else self._map_runs(inode)
        result = []
        for index, run in enumerate(source):
            if index >= 1_000_000:
                raise ValueError("inode block map exceeds bounded entry count")
            result.append(run)
        result.sort()
        end = 0
        for logical, physical, length, _initialized in result:
            if logical < end or length <= 0 or physical + length > self.sb.blocks_count:
                raise ValueError("overlapping or invalid inode extent")
            end = logical + length
        return result

    def iter_file(self, inode: Inode, *, limit: int = MAX_FILE_READ) -> Iterator[bytes]:
        """File content in order; holes and uninitialized extents read as zeros."""
        if inode.size > limit:
            raise ValueError(f"inode {inode.number}: {inode.size} bytes exceeds the read limit {limit}")
        size, remaining, position = self.sb.block_size, inode.size, 0
        for logical, physical, length, initialized in self.runs(inode):
            start = logical * size
            if start >= inode.size:
                break
            if start > position:
                gap = min(start - position, remaining)
                yield bytes(gap)
                position += gap
                remaining -= gap
            take = min(length * size, remaining)
            if take <= 0:
                break
            done = 0
            while done < take:
                piece = min(take - done, CHUNK_BLOCKS * size)
                if initialized:
                    yield self.read_blocks(physical + done // size, -(-piece // size))[:piece]
                else:
                    yield bytes(piece)
                done += piece
            position += take
            remaining -= take
        if remaining > 0:
            yield bytes(remaining)

    def read_file(self, inode: Inode, *, limit: int = MAX_FILE_READ) -> bytes:
        return b"".join(self.iter_file(inode, limit=limit))

    def readlink(self, inode: Inode) -> str:
        if inode.kind != "symlink":
            raise ValueError(f"inode {inode.number} is not a symlink")
        if inode.size < 60 and not inode.flags & EXTENTS_FL:
            raw = inode.block[:inode.size]
        else:
            raw = self.read_file(inode, limit=4096)
        return raw.decode("utf-8", errors="replace")

    # -- directories ------------------------------------------------------
    def listdir(self, inode: Inode) -> list[tuple[str, int, str]]:
        """[(name, inode number, type)] without '.' and '..'."""
        if inode.kind != "dir":
            raise ValueError(f"inode {inode.number} is not a directory")
        data = self.read_file(inode, limit=64 * 1024 * 1024)
        entries, offset, size = [], 0, self.sb.block_size
        filetype = bool(self.sb.feature_incompat & INCOMPAT_FILETYPE)
        while offset + 8 <= len(data):
            number, rec_len, name_len, file_type = struct.unpack_from("<IHBB", data, offset)
            if rec_len < 8 or offset % size + rec_len > size or offset + rec_len > len(data) or name_len > rec_len - 8:
                raise ValueError(f"directory inode {inode.number}: bad record at {offset}")
            if not filetype:
                name_len |= file_type << 8
                file_type = 0
            if number and name_len:
                name = data[offset + 8:offset + 8 + name_len].decode("utf-8", errors="surrogateescape")
                if "/" in name or "\0" in name:
                    raise ValueError("invalid directory entry name")
                if name not in (".", ".."):
                    entries.append((name, number, FILE_TYPES.get(file_type, "unknown")))
                    if len(entries) > MAX_DIR_ENTRIES:
                        raise ValueError("directory too large")
            offset += rec_len
        return entries

    def lookup(self, path: str) -> Inode:
        """Inode for an absolute path; symlinks along the way are not followed."""
        current = self.inode(2)
        for part in [p for p in path.split("/") if p]:
            match = [n for name, n, _t in self.listdir(current) if name == part]
            if not match:
                raise FileNotFoundError(path)
            current = self.inode(match[0])
        return current

    def walk(self, top: str = "/", *, max_depth: int = 64) -> Iterator[tuple[str, Inode]]:
        """(path, inode) for every entry below ``top`` (depth-first, directories before their content)."""
        seen: set[int] = set()
        stack = [(top.rstrip("/") or "/", self.lookup(top), 0)]
        while stack:
            path, inode, depth = stack.pop()
            yield path, inode
            if inode.kind != "dir" or inode.number in seen or depth >= max_depth:
                continue
            seen.add(inode.number)
            children = sorted(self.listdir(inode), reverse=True)
            for name, number, _type in children:
                child = f"{path.rstrip('/')}/{name}"
                stack.append((child, self.inode(number), depth + 1))
