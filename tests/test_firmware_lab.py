"""Bounded image metadata and a tiny independent, synthetic ARM ELF fixture."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from monsieur_cuisine_sdk.firmware.lab import inspect_image, inspect_elf
from test_backup_manager import make_disk


def arm_elf():
    data = bytearray(52)
    text_offset = len(data); data.extend(bytes.fromhex("1eff2fe1"))  # ARM bx lr
    strings_offset = len(data); strings = b"\0Java_test\0"; data.extend(strings)
    data.extend(bytes(-len(data) % 4))
    symbols_offset = len(data)
    symbols = bytes(16) + struct.pack("<IIIBBH", 1, 0x1000, 4, 0x12, 0, 1)
    data.extend(symbols)
    names_offset = len(data); names = b"\0.text\0.dynstr\0.dynsym\0.shstrtab\0"; data.extend(names)
    data.extend(bytes(-len(data) % 4)); sections_offset = len(data)
    def section(name, kind, flags, address, offset, size, link=0, info=0, alignment=1, entry_size=0):
        return struct.pack("<10I", names.find(name) if name else 0, kind, flags, address, offset, size, link, info, alignment, entry_size)
    data.extend(bytes(40))
    data.extend(section(b".text", 1, 6, 0x1000, text_offset, 4, alignment=4))
    data.extend(section(b".dynstr", 3, 0, 0, strings_offset, len(strings)))
    data.extend(section(b".dynsym", 11, 0, 0, symbols_offset, len(symbols), link=2, info=1, alignment=4, entry_size=16))
    data.extend(section(b".shstrtab", 3, 0, 0, names_offset, len(names)))
    data[:16] = b"\x7fELF\x01\x01\x01" + bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH", data, 16, 3, 40, 1, 0, 0, sections_offset, 0x5000000, 52, 0, 0, 40, 5, 4)
    return bytes(data)


class FirmwareInspectionTests(unittest.TestCase):
    def test_gpt_and_elf_metadata_exclude_machine_identifiers(self):
        with tempfile.TemporaryDirectory() as temporary:
            disk = Path(temporary) / "disk.img"
            disk.write_bytes(make_disk())
            report = inspect_image(disk, hash_content=True)
            self.assertEqual(report["type"], "gpt-disk")
            self.assertTrue(report["partitions"])
            self.assertNotIn("disk_guid", report)
            elf = Path(temporary) / "test.so"
            elf.write_bytes(arm_elf())
            self.assertEqual(inspect_image(elf)["architecture"], "ARM")
            self.assertFalse(inspect_image(elf)["identifiers_included"])

    def test_directories_and_truncated_boot_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                inspect_image(temporary)
            image = Path(temporary) / "boot.img"
            image.write_bytes(b"ANDROID!" + bytes(100))
            with self.assertRaises(ValueError):
                inspect_image(image)

    @unittest.skipUnless(importlib.util.find_spec("elftools") and importlib.util.find_spec("capstone"), "optional analysis extra not installed")
    def test_actual_disassembly_of_independent_synthetic_arm_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.so"
            path.write_bytes(arm_elf())
            report = inspect_elf(path)
            self.assertEqual(len(report["functions"]), 1)
            function = report["functions"][0]
            self.assertEqual(function["symbol"], "Java_test")
            self.assertEqual(function["file_offset"], 52)
            self.assertEqual(function["address"], 0x1000)
            self.assertEqual(function["instructions"][0]["mnemonic"], "bx")
            self.assertEqual(function["instructions"][0]["operands"], "lr")
