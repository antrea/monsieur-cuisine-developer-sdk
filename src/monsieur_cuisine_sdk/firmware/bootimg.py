"""Android boot image reader (header versions 0-2, as used by Android 6-10 devices).

Read-only. Splits kernel, ramdisk and second stage, strips the MediaTek
512-byte wrapper when present, and lists the gzip-compressed "newc" cpio
ramdisk without extracting it to disk.
"""
from __future__ import annotations

import gzip
import io
import struct
import zlib
from dataclasses import dataclass

from .mtk import MTK_HEADER_SIZE, parse_mtk_header

BOOT_MAGIC = b"ANDROID!"
MAX_RAMDISK = 64 * 1024 * 1024


@dataclass(frozen=True)
class BootImage:
    kernel_size: int
    kernel_addr: int
    ramdisk_size: int
    ramdisk_addr: int
    second_size: int
    tags_addr: int
    page_size: int
    header_version: int
    os_version: int
    name: str
    cmdline: str
    sha1_id: str

    def sections(self) -> dict[str, tuple[int, int]]:
        """{section: (offset, size)} inside the image."""
        page = self.page_size
        def pages(n):
            return -(-n // page) * page
        kernel = page
        ramdisk = kernel + pages(self.kernel_size)
        second = ramdisk + pages(self.ramdisk_size)
        return {"kernel": (kernel, self.kernel_size), "ramdisk": (ramdisk, self.ramdisk_size),
                "second": (second, self.second_size)}


def parse_boot_image(raw: bytes) -> BootImage:
    if raw[:8] != BOOT_MAGIC or len(raw) < 1632:
        raise ValueError("not an Android boot image")
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, _second_addr, tags_addr, page_size,
     header_version, os_version) = struct.unpack_from("<10I", raw, 8)
    if page_size not in (2048, 4096, 8192, 16384):
        raise ValueError(f"unsupported page size {page_size}")
    name = raw[48:64].split(b"\0", 1)[0].decode("ascii", errors="replace")
    cmdline = raw[64:576].split(b"\0", 1)[0].decode("ascii", errors="replace")
    sha1_id = raw[576:608].hex()
    extra = raw[608:1632].split(b"\0", 1)[0].decode("ascii", errors="replace")
    image = BootImage(kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, tags_addr, page_size,
                      header_version if header_version < 16 else 0, os_version, name, cmdline + extra, sha1_id)
    for section, (offset, size) in image.sections().items():
        if offset + size > len(raw):
            raise ValueError(f"{section} extends past the image")
    return image


def section(raw: bytes, image: BootImage, name: str) -> bytes:
    offset, size = image.sections()[name]
    return raw[offset:offset + size]


def unwrap_mtk(payload: bytes) -> tuple[str | None, bytes]:
    """(MTK header name, inner payload) — or (None, payload) when there is no MTK wrapper."""
    header = parse_mtk_header(payload[:MTK_HEADER_SIZE])
    if header is None:
        return None, payload
    return header.name, payload[MTK_HEADER_SIZE:MTK_HEADER_SIZE + header.size]


def decompress_ramdisk(payload: bytes) -> bytes:
    if payload[:2] != b"\x1f\x8b":
        raise ValueError("ramdisk is not gzip-compressed")
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        while block := stream.read(1024 * 1024):
            out.write(block)
            if out.tell() > MAX_RAMDISK:
                raise ValueError("ramdisk larger than the decompression limit")
    return out.getvalue()


@dataclass(frozen=True)
class CpioEntry:
    name: str
    mode: int
    size: int
    data_offset: int

    @property
    def kind(self) -> str:
        return {0o040000: "dir", 0o100000: "file", 0o120000: "symlink"}.get(self.mode & 0o170000, "other")


def list_cpio(archive: bytes) -> list[CpioEntry]:
    """Entries of a "newc" (070701) cpio archive, stopping at TRAILER!!!."""
    entries, offset = [], 0
    while offset + 110 <= len(archive):
        if archive[offset:offset + 6] not in (b"070701", b"070702"):
            raise ValueError(f"bad cpio magic at {offset}")
        fields = [int(archive[offset + 6 + 8 * i:offset + 14 + 8 * i], 16) for i in range(13)]
        mode, size, name_size = fields[1], fields[6], fields[11]
        name_start = offset + 110
        name = archive[name_start:name_start + name_size - 1].decode("utf-8", errors="replace")
        data = -(-(name_start + name_size) // 4) * 4
        if name == "TRAILER!!!":
            break
        if data + size > len(archive):
            raise ValueError(f"cpio entry {name!r} truncated")
        entries.append(CpioEntry(name, mode, size, data))
        offset = -(-(data + size) // 4) * 4
    return entries


def cpio_read(archive: bytes, entry: CpioEntry) -> bytes:
    return archive[entry.data_offset:entry.data_offset + entry.size]


def crc32(data: bytes) -> str:
    return f"{zlib.crc32(data):08x}"
