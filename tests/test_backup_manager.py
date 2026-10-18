"""Backup & Recovery Manager and Firmware Lab parsers on small synthetic inputs (no device, no real backup)."""
import gzip
import hashlib
import io
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from monsieur_cuisine_sdk.backup.image import CompositeImage, RawImage, Segment, sha256_image
from monsieur_cuisine_sdk.backup.session import BackupSession, read_manifest, safe_relative
from monsieur_cuisine_sdk.backup.verify import compose_user_area, verify_session
from monsieur_cuisine_sdk.firmware import bootimg, ext4, gpt, mtk

SECTOR = 512
PARTS = [("alpha", 40, 47), ("beta", 48, 63), ("gamma", 64, 95)]


def make_disk(sectors=160, tail_reserved=32):
    """Protective MBR + GPT (MediaTek-style reserved tail when tail_reserved > 33)."""
    table = bytearray(128 * 128)
    for i, (name, first, last) in enumerate(PARTS):
        base = i * 128
        table[base:base + 16] = bytes(range(1, 17))
        table[base + 16:base + 32] = hashlib.md5(name.encode()).digest()
        struct.pack_into("<QQQ", table, base + 32, first, last, 0)
        table[base + 56:base + 56 + 2 * len(name)] = name.encode("utf-16-le")
    table = bytes(table)
    backup_lba = sectors - 1
    last_usable = backup_lba - tail_reserved - 1

    def header(current, alternate, entries_lba):
        raw = bytearray(SECTOR)
        struct.pack_into("<8sIIIIQQQQ16sQIII", raw, 0, b"EFI PART", 0x10000, 92, 0, 0, current, alternate, 34,
                         last_usable, b"\x11" * 16, entries_lba, 128, 128, zlib.crc32(table))
        struct.pack_into("<I", raw, 16, zlib.crc32(bytes(raw[:92])))
        return bytes(raw)

    disk = bytearray(sectors * SECTOR)
    disk[446 + 4] = 0xEE
    disk[510:512] = b"\x55\xaa"
    disk[SECTOR:2 * SECTOR] = header(1, backup_lba, 2)
    disk[2 * SECTOR:2 * SECTOR + len(table)] = table
    for index, (name, first, last) in enumerate(PARTS):
        disk[first * SECTOR:(last + 1) * SECTOR] = bytes([index + 1]) * ((last - first + 1) * SECTOR)
    disk[(last_usable + 1) * SECTOR:(last_usable + 1) * SECTOR + len(table)] = table
    disk[backup_lba * SECTOR:] = header(backup_lba, 1, last_usable + 1)
    return bytes(disk)


def write_session(root: Path, disk: bytes, *, commands=("printgpt", "rf emmc_user_full.bin")):
    (root / "partitions").mkdir(parents=True)
    (root / "partitions_extracted").mkdir()
    (root / "gpt_primary.bin").write_bytes(disk[:34 * SECTOR])
    sums, extracted = [], []
    for name, first, last in PARTS:
        data = disk[first * SECTOR:(last + 1) * SECTOR]
        (root / "partitions_extracted" / f"{name}.bin").write_bytes(data)
        (root / "partitions" / f"{name}.bin").write_bytes(data)
        extracted.append(f"{hashlib.sha256(data).hexdigest()}  {name}.bin")
        sums.append(f"{hashlib.sha256(data).hexdigest()}  partitions/{name}.bin")
    for area in ("emmc_boot1.bin", "emmc_boot2.bin"):
        data = b"EMMC_BOOT\0" + bytes(0x200 - 10) + b"BRLYT" + bytes(4096) if area.endswith("1.bin") else bytes(4096)
        (root / area).write_bytes(data)
        sums.append(f"{hashlib.sha256(data).hexdigest()}  {area}")
    sums.append(f"{hashlib.sha256(disk[:34 * SECTOR]).hexdigest()}  gpt_primary.bin")
    sums.append(f"{hashlib.sha256(disk).hexdigest()}  emmc_user_full.bin")
    (root / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    (root / "partitions_extracted" / "SHA256SUMS.txt").write_text("\n".join(extracted) + "\n", encoding="ascii")
    (root / "commands.txt").write_text("\n".join(commands) + "\n", encoding="ascii")


def status(report, check_id):
    return next(c.status for c in report.checks if c.id == check_id)


class Manifest(unittest.TestCase):
    def test_paths_must_stay_inside_the_session(self):
        for bad in ("../x.bin", "/etc/passwd", "C:" + "/x", "a//b", "a/./b", "a/../b", ""):
            with self.assertRaises(ValueError, msg=bad):
                safe_relative(bad)
        self.assertEqual(safe_relative("partitions\\boot.bin").as_posix(), "partitions/boot.bin")

    def test_manifest_parsing_rejects_garbage_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SHA256SUMS.txt"
            digest = "a" * 64
            path.write_text(f"{digest}  one.bin\n{digest} *two.bin\n\n", encoding="ascii")
            self.assertEqual(read_manifest(path), {"one.bin": digest, "two.bin": digest})
            path.write_text(f"{digest}  one.bin\n{digest}  one.bin\n", encoding="ascii")
            with self.assertRaises(ValueError):
                read_manifest(path)
            path.write_text("not a hash line\n", encoding="ascii")
            with self.assertRaises(ValueError):
                read_manifest(path)
            path.write_text(f"{digest}  ../escape.bin\n", encoding="ascii")
            with self.assertRaises(ValueError):
                read_manifest(path)


class Composite(unittest.TestCase):
    def test_reads_span_segments_and_fill_gaps_with_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "p.bin"
            source.write_bytes(b"ABCDEFGH")
            image = CompositeImage(20, [Segment(2, 4, source, 2, label="file"), Segment(10, 3, data=b"xyz")])
            self.assertEqual(image.read_at(0, 20), b"\0\0CDEF\0\0\0\0xyz\0\0\0\0\0\0\0")
            self.assertEqual(image.read_at(4, 8), b"EF\0\0\0\0xy")
            self.assertEqual(image.read_at(18, 10), b"\0\0")
            self.assertEqual(sha256_image(image, chunk=3), hashlib.sha256(image.read_at(0, 20)).hexdigest())

    def test_overlap_and_out_of_range_segments_are_refused(self):
        with self.assertRaises(ValueError):
            CompositeImage(10, [Segment(0, 5, data=b"aaaaa"), Segment(4, 2, data=b"bb")])
        with self.assertRaises(ValueError):
            CompositeImage(10, [Segment(8, 5, data=b"ccccc")])
        with self.assertRaises(ValueError):
            CompositeImage(10, [Segment(0, 3, data=b"dd")])

    def test_raw_window_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.bin"
            path.write_bytes(bytes(range(16)))
            window = RawImage(path, 4, 8)
            self.assertEqual(window.read_at(0, 100), bytes(range(4, 12)))
            with self.assertRaises(ValueError):
                RawImage(path, 10, 10)


class Gpt(unittest.TestCase):
    def setUp(self):
        self.disk = make_disk()
        self.read = lambda offset, length: self.disk[offset:offset + length]

    def test_primary_and_backup_tables_parse_and_agree(self):
        primary = gpt.read_table(self.read, header_lba=1, disk_sectors=len(self.disk) // SECTOR)
        self.assertEqual([p.name for p in primary.partitions], ["alpha", "beta", "gamma"])
        self.assertTrue(primary.header.header_crc_ok and primary.entries_crc_ok)
        self.assertEqual(primary.problems, [])
        backup = gpt.read_table(self.read, header_lba=primary.header.backup_lba)
        self.assertEqual(backup.entries_raw, primary.entries_raw)
        self.assertTrue(gpt.protective_mbr_ok(self.disk[:SECTOR]))

    def test_rebuilt_backup_header_matches_the_disk(self):
        primary = gpt.read_table(self.read)
        header, entries_lba = gpt.build_backup(self.disk[SECTOR:2 * SECTOR], primary.entries_raw, primary.header)
        backup_lba = primary.header.backup_lba
        self.assertEqual(entries_lba, primary.header.last_usable_lba + 1)
        self.assertEqual(header, self.disk[backup_lba * SECTOR:(backup_lba + 1) * SECTOR])

    def test_damage_is_reported(self):
        damaged = bytearray(self.disk)
        damaged[2 * SECTOR + 40] ^= 1          # entry table byte
        table = gpt.read_table(lambda o, n: bytes(damaged[o:o + n]))
        self.assertIn("entry table CRC32 mismatch", table.problems)
        damaged = bytearray(self.disk)
        damaged[SECTOR + 40] ^= 1              # header byte
        self.assertIn("header CRC32 mismatch", gpt.read_table(lambda o, n: bytes(damaged[o:o + n])).problems)

    def test_hostile_sizes_are_bounded(self):
        hostile = bytearray(self.disk)
        struct.pack_into("<I", hostile, SECTOR + 80, 10_000_000)   # entry count
        with self.assertRaises(ValueError):
            gpt.read_table(lambda o, n: bytes(hostile[o:o + n]))
        with self.assertRaises(ValueError):
            gpt.parse_header(b"NOT A GPT" + bytes(100))

    def test_gaps_cover_everything_outside_partitions(self):
        table = gpt.read_table(self.read)
        self.assertEqual(gpt.gaps(table, 160), [(0, 39), (96, 159)])


class VerifySession(unittest.TestCase):
    def test_lossless_partition_set_passes_including_reconstruction(self):
        disk = make_disk()
        with tempfile.TemporaryDirectory() as tmp:
            write_session(Path(tmp), disk)
            report = verify_session(tmp, identify=False)
            self.assertTrue(report.passed, [c for c in report.checks if c.status == "FAIL"])
            self.assertEqual(status(report, "full_image.reconstruction"), "PASS")
            self.assertEqual(status(report, "partitions.cross_read"), "PASS")
            self.assertEqual(status(report, "session.read_only"), "PASS")

    def test_reconstruction_detects_data_outside_partitions(self):
        disk = bytearray(make_disk())
        disk[36 * SECTOR] = 0x5A               # unallocated area the pieces do not carry
        with tempfile.TemporaryDirectory() as tmp:
            write_session(Path(tmp), bytes(disk))
            report = verify_session(tmp, identify=False)
            self.assertEqual(status(report, "full_image.reconstruction"), "FAIL")

    def test_tampered_partition_and_write_command_fail(self):
        disk = make_disk()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_session(root, disk, commands=("printgpt", "w boot boot.bin"))
            path = root / "partitions_extracted" / "beta.bin"
            data = bytearray(path.read_bytes())
            data[0] ^= 0xFF
            path.write_bytes(bytes(data))
            report = verify_session(tmp, identify=False)
            self.assertFalse(report.passed)
            self.assertEqual(status(report, "extracted.hashes"), "FAIL")
            self.assertEqual(status(report, "partitions.cross_read"), "FAIL")
            self.assertEqual(status(report, "session.read_only"), "FAIL")

    def test_missing_partition_is_a_completeness_failure(self):
        disk = make_disk()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_session(root, disk)
            (root / "partitions_extracted" / "gamma.bin").unlink()
            (root / "partitions" / "gamma.bin").unlink()
            report = verify_session(tmp, identify=False)
            self.assertEqual(status(report, "completeness.partitions"), "FAIL")

    def test_composed_image_equals_the_disk(self):
        disk = make_disk()
        with tempfile.TemporaryDirectory() as tmp:
            write_session(Path(tmp), disk)
            session = BackupSession.open(tmp)
            primary = RawImage(Path(tmp) / "gpt_primary.bin")
            table = gpt.read_table(primary.read_at)
            image = compose_user_area(session, table, primary.read_at(SECTOR, SECTOR))
            self.assertEqual(image.read_at(0, image.size), disk)


class BootAndMtkImages(unittest.TestCase):
    @staticmethod
    def cpio(entries):
        out = bytearray()
        for name, mode, data in entries + [("TRAILER!!!", 0, b"")]:
            encoded = name.encode() + b"\0"
            fields = [1, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
            out += b"070701" + b"".join(f"{v:08x}".encode() for v in fields) + encoded
            out += bytes(-len(out) % 4) + data
            out += bytes(-len(out) % 4)
        return bytes(out)

    def test_android_boot_image_with_mtk_wrapped_ramdisk(self):
        page = 2048
        kernel = b"K" * 3000
        ramdisk = gzip.compress(self.cpio([("init.rc", 0o100644, b"service x\n"), ("sbin", 0o040755, b"")]))
        wrapped = mtk.MTK_MAGIC + struct.pack("<I", len(ramdisk)) + b"ROOTFS".ljust(32, b"\0")
        wrapped = wrapped.ljust(512, b"\xff") + ramdisk
        header = bytearray(page)
        header[:8] = bootimg.BOOT_MAGIC
        struct.pack_into("<10I", header, 8, len(kernel), 0x80008000, len(wrapped), 0x84000000, 0, 0, 0x8E000000,
                         page, 0, 0)
        header[64:64 + 9] = b"bootopt=x"
        image = bytes(header) + kernel.ljust(4096, b"\0") + wrapped.ljust(-(-len(wrapped) // page) * page, b"\0")
        parsed = bootimg.parse_boot_image(image)
        self.assertEqual(parsed.cmdline, "bootopt=x")
        name, payload = bootimg.unwrap_mtk(bootimg.section(image, parsed, "ramdisk"))
        self.assertEqual(name, "ROOTFS")
        entries = bootimg.list_cpio(bootimg.decompress_ramdisk(payload))
        self.assertEqual([(e.name, e.kind) for e in entries], [("init.rc", "file"), ("sbin", "dir")])
        archive = bootimg.decompress_ramdisk(payload)
        self.assertEqual(bootimg.cpio_read(archive, entries[0]), b"service x\n")

    def test_truncated_boot_image_is_refused(self):
        header = bytearray(2048)
        header[:8] = bootimg.BOOT_MAGIC
        struct.pack_into("<10I", header, 8, 10_000, 0, 0, 0, 0, 0, 0, 2048, 0, 0)
        with self.assertRaises(ValueError):
            bootimg.parse_boot_image(bytes(header))

    def test_mtk_header_sequence_and_preloader(self):
        one = mtk.MTK_MAGIC + struct.pack("<I", 4) + b"lk".ljust(32, b"\0")
        raw = one.ljust(512, b"\0") + b"DATA"
        self.assertEqual(mtk.mtk_images(raw), [{"offset": 0, "name": "lk", "size": 4}])
        self.assertIsNone(mtk.parse_mtk_header(b"\0" * 64))
        info = mtk.parse_preloader(b"EMMC_BOOT" + bytes(0x1F7) + b"BRLYT" + bytes(64))
        self.assertTrue(info.emmc_boot)
        self.assertEqual(info.brlyt_offset, 0x200)


class Ext4Superblock(unittest.TestCase):
    """Field decoding and rejection paths; the full reader is checked against 7-Zip on a real image (docs)."""

    def superblock(self, **changes):
        raw = bytearray(1024)
        values = dict(inodes=64, blocks=1024, free=100, free_inodes=10, first=1, log=0, per_group=8192,
                      inodes_per_group=64, magic=0xEF53, state=1, rev=1, inode_size=256)
        values.update(changes)
        struct.pack_into("<IIIIIII", raw, 0, values["inodes"], values["blocks"], 0, values["free"],
                         values["free_inodes"], values["first"], values["log"])
        struct.pack_into("<I", raw, 0x20, values["per_group"])
        struct.pack_into("<I", raw, 0x28, values["inodes_per_group"])
        struct.pack_into("<HH", raw, 0x38, values["magic"], values["state"])
        struct.pack_into("<I", raw, 0x4C, values["rev"])
        struct.pack_into("<H", raw, 0x58, values["inode_size"])
        raw[0x78:0x7E] = b"system"
        return bytes(raw)

    def test_fields(self):
        sb = ext4.parse_superblock(self.superblock())
        self.assertEqual((sb.block_size, sb.blocks_count, sb.free_blocks, sb.inode_size, sb.volume_name),
                         (1024, 1024, 100, 256, "system"))
        self.assertTrue(sb.clean)
        self.assertEqual(sb.group_count, 1)

    def test_rejections(self):
        for changes in ({"magic": 0x1234}, {"log": 9}, {"inode_size": 100}, {"per_group": 0}):
            with self.assertRaises(ValueError, msg=changes):
                ext4.parse_superblock(self.superblock(**changes))
        with self.assertRaises(ValueError):
            ext4.parse_superblock(b"\0" * 100)

    def test_container_smaller_than_filesystem_is_refused(self):
        image = bytes(1024) + self.superblock() + bytes(4096)
        with self.assertRaises(ValueError):
            ext4.Ext4(lambda o, n: image[o:o + n], size=len(image))


if __name__ == "__main__":
    unittest.main()
