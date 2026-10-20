"""MediaTek container headers found in MT65xx firmware images (read-only identification).

* The 512-byte "MTK header" (magic 88 16 88 58) that wraps lk, logo and the
  kernel/ramdisk inside an Android boot image: magic, payload size, 32-byte name.
* The eMMC boot-area preloader: an "EMMC_BOOT" record followed by a "BRLYT"
  boot-ROM layout record, and the GFH "MMM" file-info header of the preloader.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

MTK_MAGIC = b"\x88\x16\x88\x58"
MTK_HEADER_SIZE = 512


@dataclass(frozen=True)
class MtkHeader:
    name: str
    size: int

    @property
    def payload_offset(self) -> int:
        return MTK_HEADER_SIZE


def parse_mtk_header(raw: bytes) -> MtkHeader | None:
    """The MTK header at the start of ``raw``, or None."""
    if len(raw) < 40 or raw[:4] != MTK_MAGIC:
        return None
    size, = struct.unpack_from("<I", raw, 4)
    name = raw[8:40].split(b"\0", 1)[0].decode("ascii", errors="replace")
    return MtkHeader(name, size)


def mtk_images(raw: bytes, *, limit: int = 64) -> list[dict]:
    """Consecutive MTK-header images (as packed in lk/logo partitions)."""
    images, offset = [], 0
    while len(images) < limit:
        header = parse_mtk_header(raw[offset:offset + MTK_HEADER_SIZE])
        if header is None or offset + MTK_HEADER_SIZE + header.size > len(raw):
            break
        images.append({"offset": offset, "name": header.name, "size": header.size})
        offset += MTK_HEADER_SIZE + header.size
    return images


@dataclass(frozen=True)
class PreloaderInfo:
    emmc_boot: bool
    brlyt_offset: int | None
    gfh_offset: int | None
    gfh_file_version: int | None
    gfh_file_type: int | None
    gfh_load_address: int | None
    gfh_file_length: int | None


def parse_preloader(boot1: bytes) -> PreloaderInfo:
    """Identify the MediaTek preloader layout at the start of the eMMC boot1 area."""
    emmc_boot = boot1[:9] == b"EMMC_BOOT"
    brlyt = boot1.find(b"BRLYT", 0, 0x1000)
    gfh = boot1.find(b"MMM\x01", 0, 0x10000)
    version = file_type = load = length = None
    if gfh >= 0 and len(boot1) >= gfh + 0x38:
        # GFH_FILE_INFO: magic(3) version(1) size(2) type(2) "FILE_INFO"(12) file_ver(4) file_type(2)
        # flash_dev(1) sig_type(1) load_addr(4) file_len(4) max_size(4) content_offset(4) ...
        if boot1[gfh + 8:gfh + 17] == b"FILE_INFO":
            version, file_type = struct.unpack_from("<IH", boot1, gfh + 20)
            load, length = struct.unpack_from("<II", boot1, gfh + 28)
    return PreloaderInfo(emmc_boot, brlyt if brlyt >= 0 else None, gfh if gfh >= 0 else None,
                         version, file_type, load, length)
