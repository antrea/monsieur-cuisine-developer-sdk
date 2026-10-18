"""Independent offline backup/CLI/privacy and fake-ADB transaction tests."""
import contextlib
import io
import json
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from monsieur_cuisine_sdk.backup.cli import main
from monsieur_cuisine_sdk.backup.external import MCCBackupAdapter
from monsieur_cuisine_sdk.backup.inventory import InventoryReport, _system_inventory, inventory_session, privacy_class
from monsieur_cuisine_sdk.backup.session import BackupSession
from monsieur_cuisine_sdk.backup.verify import verify_session
from monsieur_cuisine_sdk.firmware.ext4 import Ext4, Inode, EXTENTS_FL
from monsieur_cuisine_sdk.usb import ApplicationSandbox, ReadOnlyADB, application_plan
from test_backup_manager import make_disk, write_session


class BackupInventory(unittest.TestCase):
    def test_partition_inventory_and_cli_do_not_modify_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'session'; root.mkdir()
            write_session(root, make_disk())
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            data = inventory_session(root).to_dict()
            self.assertEqual(len(data['partitions']), 3)
            self.assertFalse(data['identifiers_included'])
            for command in ('verify', 'inventory', 'report'):
                output = io.StringIO()
                with contextlib.redirect_stdout(output): self.assertEqual(main([command, str(root)]), 0)
                self.assertNotIn(str(root), output.getvalue())
                self.assertNotIn('disk_guid', output.getvalue())
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(privacy_class('userdata'), 'personal')
            self.assertEqual(privacy_class('nvram'), 'device-unique')

    def test_output_must_be_new_and_outside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'session'; root.mkdir(); write_session(root, make_disk())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['inventory', str(root), '--output', str(root / 'report.json')]), 2)
            destination = Path(directory) / 'result.json'
            self.assertEqual(main(['inventory', str(root), '--output', str(destination)]), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['inventory', str(root), '--output', str(destination)]), 2)

    def test_system_allowlist_and_opaque_app_hashing(self):
        class Node:
            def __init__(self, size=3, kind='file'): self.size, self.kind = size, kind
        class Filesystem:
            def __init__(self, *a, **kw): pass
            def lookup(self, path): return Node()
            def read_file(self, node, **kw):
                return b'ro.build.version.release=6.0\nro.serialno=PERSONAL\nro.product.model=MCC\nnet.mac=SECRET\n'
            def walk(self, path): return iter([(path + '/Example/base.apk', Node())])
            def iter_file(self, node): return iter([b'APK'])
        class View:
            size = 1024
            def read_at(self, *a): raise AssertionError('fake filesystem owns reads')
        result = InventoryReport()
        with patch('monsieur_cuisine_sdk.backup.inventory.ext4.Ext4', Filesystem):
            _system_inventory(View(), result, None, lambda: False)
        encoded = json.dumps(result.to_dict())
        self.assertNotIn('PERSONAL', encoded); self.assertNotIn('SECRET', encoded)
        self.assertEqual(result.build['ro.build.version.release'], '6.0')
        self.assertEqual(result.apps[0]['bytes'], 3)
        self.assertEqual(len(result.apps[0]['sha256']), 64)

    def test_cancel_and_malformed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write_session(root, make_disk())
            (root / 'session.json').write_text('[]', encoding='utf-8')
            self.assertEqual(BackupSession.open(root).metadata, {})
            with self.assertRaises(ValueError): inventory_session(root, cancelled=lambda: True)
            with self.assertRaises(ValueError): verify_session(root, cancelled=lambda: True)
            with self.assertRaises(ValueError): BackupSession.open(root).partition_file('../escape')

    def test_external_archive_is_never_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'tool.zip'
            with zipfile.ZipFile(archive, 'w') as handle: handle.writestr('README.md', 'test-only archive')
            with patch('subprocess.run', side_effect=AssertionError('tool execution forbidden')):
                report = MCCBackupAdapter(archive).inspect()
            self.assertFalse(report['release_verified']); self.assertFalse(report['executed'])
            with zipfile.ZipFile(archive, 'w') as handle: handle.writestr('../escape', 'x')
            with self.assertRaises(ValueError): MCCBackupAdapter(archive).inspect()


class USBSafeTools(unittest.TestCase):
    def test_plan_cli_writes_utf8_and_rehearses_without_adb(self):
        from monsieur_cuisine_sdk.usb import main as usb_main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); apk = root / 'sample.apk'; apk.write_bytes(b'opaque')
            output = root / 'plan.json'
            self.assertEqual(usb_main(['plan', str(apk), '--package', 'org.example.app',
                                       '--minimum-sdk', '23', '--output', str(output)]), 0)
            self.assertEqual(json.loads(output.read_text('utf-8'))['package'], 'org.example.app')
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(usb_main(['rehearse', str(output)]), 0)
            self.assertTrue(json.loads(capture.getvalue())['rollback_matches_snapshot'])

    def test_diagnostics_allow_only_selected_read_commands(self):
        commands = []
        def fake(arguments, **kwargs):
            commands.append(arguments[1:])
            value = 'device' if arguments[1:] == ['get-state'] else '6.0'
            return subprocess.CompletedProcess(arguments, 0, value, '')
        adb = ReadOnlyADB('fake-adb', runner=fake)
        self.assertTrue(adb.diagnose()['read_only'])
        for bad in (['install', 'app.apk'], ['shell', 'settings', 'put', 'x', 'y'], ['reboot'],
                    ['shell', 'getprop', 'ro.serialno'], ['devices']):
            with self.assertRaises(ValueError): adb._read(bad)
        self.assertEqual(len(commands), 5)

    def test_offline_install_launcher_and_rollback_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'sample.apk'; apk.write_bytes(b'opaque test data')
            plan = application_plan(apk, 'org.example.app', minimum_sdk=23)
            sandbox = ApplicationSandbox()
            with self.assertRaises(ValueError): sandbox.apply(plan)
            baseline = sandbox.snapshot(); sandbox.apply(plan)
            sandbox.select_launcher('org.example.app')
            self.assertEqual(sandbox.rollback(), baseline)
            self.assertEqual(sandbox.launcher, 'de.silpion.mc2')
            self.assertFalse(plan['signatures_checked'])
            incompatible = application_plan(apk, 'org.example.app', minimum_sdk=35)
            with self.assertRaises(ValueError): sandbox.apply(incompatible)
            with self.assertRaises(ValueError): application_plan(apk, 'de.silpion.mc2', minimum_sdk=23)


class HostileImageBounds(unittest.TestCase):
    def test_overlapping_extents_are_rejected_before_file_content_is_read(self):
        from types import SimpleNamespace
        fs = Ext4.__new__(Ext4); fs.sb = SimpleNamespace(blocks_count=1000)
        block = bytearray(60)
        struct.pack_into('<HHHH', block, 0, 0xF30A, 2, 4, 0)
        struct.pack_into('<IHHI', block, 12, 0, 3, 0, 10)
        struct.pack_into('<IHHI', block, 24, 2, 3, 0, 20)
        node = Inode(2, 0o100644, 0, 0, 1024, 0, 0, 0, 1, EXTENTS_FL, bytes(block))
        with self.assertRaises(ValueError): fs.runs(node)

    def test_hashes_cancel_between_chunks_and_refuse_zero_chunk(self):
        from monsieur_cuisine_sdk.backup.image import RawImage, sha256_image, sha256_file
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'sample.bin'; file.write_bytes(b'12345678')
            with self.assertRaises(ValueError): sha256_file(file, cancelled=lambda: True, chunk=2)
            with self.assertRaises(ValueError): sha256_image(RawImage(file), cancelled=lambda: True)
            with self.assertRaises(ValueError): sha256_file(file, chunk=0)


if __name__ == '__main__': unittest.main()
