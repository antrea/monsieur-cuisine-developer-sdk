"""Host archive/pipe safety and explicitly synthetic Android update faults."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import shlex
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from monsieur_cuisine_sdk.adb import AdbError, ApkMetadata, CapabilityError
from monsieur_cuisine_sdk.android_data import RunAsData, archive_inventory, _stream_adb
from monsieur_cuisine_sdk.transactions import AppTransaction
from test_adb_transactions import FakeAndroid


def write_tar(path, data):
    with tarfile.open(path, "w") as archive:
        for name, value in data.items():
            item = tarfile.TarInfo(name); item.mode = 0o600; item.size = len(value)
            archive.addfile(item, io.BytesIO(value))


class DataArchives(unittest.TestCase):
    def test_file_capture_preserves_raw_exec_arguments_and_archive_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); work = root / "work"; work.mkdir()
            name = "files/space é ' " + "a" * 110
            tree = {name: {"kind": "file", "size": 6, "mode": 0o600, "mtime": 1700000000}}
            commands = []
            def transfer(client, command, target, **kwargs):
                commands.append(command)
                Path(target).write_bytes(b"before")
                return 6
            with patch("monsieur_cuisine_sdk.android_data._stream_adb", side_effect=transfer):
                RunAsData(object())._capture_files("org.example.debug", tree, root / "data.tar", work)
            self.assertEqual(commands[0][-1], "./" + name)
            self.assertEqual(archive_inventory(root / "data.tar")["entries"][name]["sha256"], hashlib.sha256(b"before").hexdigest())

    def test_extended_tar_header_is_bounded_before_standard_parser_allocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.tar"
            item = tarfile.TarInfo("long-name"); item.type = tarfile.GNUTYPE_LONGNAME; item.size = 1024**3
            path.write_bytes(item.tobuf(format=tarfile.GNU_FORMAT))
            with patch("monsieur_cuisine_sdk.android_data.tarfile.open") as opened:
                with self.assertRaises(ValueError):
                    archive_inventory(path)
                opened.assert_not_called()

    def test_nul_inventory_preserves_unicode_newlines_and_shell_metacharacters(self):
        with tempfile.TemporaryDirectory() as temporary:
            special = "files/name ' ; $() `\n é.txt"
            names = [".", "./lib", "./files", "./" + special]
            modes = {"./files": stat.S_IFDIR | 0o700, "./" + special: stat.S_IFREG | 0o600}
            class Client:
                def _run(self, arguments):
                    self.received = shlex.split(" ".join(arguments[6:]))
                    return "\n\n".join(f"{modes[name]:x}:{5 if name in modes and 'name ' in name else 0}:1700000000" for name in self.received)
            client = Client()
            def binary(_client, _command, output, **kwargs):
                Path(output).write_bytes(b"\0".join(name.encode("utf-8") for name in names) + b"\0")
            with patch("monsieur_cuisine_sdk.android_data._stream_adb", side_effect=binary):
                tree = RunAsData(client)._tree("org.example.debug", Path(temporary) / "tree")
            self.assertEqual(set(tree), {"files", special})
            self.assertEqual(client.received, ["./files", "./" + special])
            self.assertEqual(tree[special]["kind"], "file")

    def test_actual_archive_inventory_and_snapshot_hash_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_tar(root / "data.tar", {"./files/state with spaces.txt": b"before", "shared_prefs/test.xml": b"<prefs/>"})
            inventory = archive_inventory(root / "data.tar")
            self.assertEqual(inventory["entries"]["files/state with spaces.txt"]["sha256"], hashlib.sha256(b"before").hexdigest())
            metadata = {"schema": "mcc-run-as-snapshot-v1", "package": "org.example.debug", "uid": 10050,
                        "archive_sha256": hashlib.sha256((root / "data.tar").read_bytes()).hexdigest(), **inventory}
            (root / "snapshot.json").write_text(json.dumps(metadata))
            self.assertEqual(RunAsData.load(root)["entries"], inventory["entries"])
            (root / "data.tar").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                RunAsData.load(root)

    def test_long_and_unicode_tar_members_are_preserved_as_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data.tar"
            values = {"files/" + "a" * 140: b"long", "files/state é.txt": b"unicode"}
            write_tar(path, values)
            actual = archive_inventory(path)
            self.assertEqual(set(actual["entries"]), set(values))
            for name, value in values.items():
                self.assertEqual(actual["entries"][name]["sha256"], hashlib.sha256(value).hexdigest())

    def test_traversal_links_privileged_modes_duplicates_and_collisions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "data.tar"
            for name in ("../escape", "/" + "outside", "files/../escape", "lib/native.so"):
                write_tar(archive, {name: b"x"})
                with self.assertRaises(ValueError, msg=name):
                    archive_inventory(archive)
            for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
                with tarfile.open(archive, "w") as output:
                    item = tarfile.TarInfo("files/link"); item.type = kind; item.linkname = "outside"
                    output.addfile(item)
                with self.assertRaises(ValueError):
                    archive_inventory(archive)
            with tarfile.open(archive, "w") as output:
                item = tarfile.TarInfo("executable"); item.mode = 0o4755
                output.addfile(item)
            with self.assertRaises(ValueError):
                archive_inventory(archive)
            write_tar(archive, {"parent": b"x", "parent/child": b"y"})
            with self.assertRaises(ValueError):
                archive_inventory(archive)

    def test_binary_process_is_drained_bounded_and_stopped_on_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            children = []
            class Client:
                executable = "synthetic-adb"
                serial = "synthetic-target"
                server_port = 5039
                script = ""
                @staticmethod
                def process_factory(command, **kwargs):
                    child = subprocess.Popen([sys.executable, "-I", "-c", Client.script], **kwargs)
                    children.append(child)
                    return child
            Client.script = "import sys;sys.stdout.buffer.write(bytes(range(256)));sys.stdout.flush()"
            self.assertEqual(_stream_adb(Client(), ["fixture"], root / "complete", timeout=5), 256)
            self.assertEqual((root / "complete").read_bytes(), bytes(range(256)))
            Client.script = "import sys;sys.stdout.buffer.write(b'x'*200000);sys.stdout.flush()"
            with self.assertRaises(ValueError):
                _stream_adb(Client(), ["fixture"], root / "oversize", limit=1000, timeout=5)
            Client.script = "import time;time.sleep(20)"
            with self.assertRaises(TimeoutError):
                _stream_adb(Client(), ["fixture"], root / "timeout", timeout=.2)
            self.assertTrue(all(child.poll() is not None for child in children))


class FakeUpdateAndroid(FakeAndroid):
    """Only host transaction logic; Android Package Manager proof is separate."""
    def __init__(self):
        super().__init__()
        self.apk = b"synthetic APK version one"
        self.app_data = {"files/settings.txt": b"before", "shared_prefs/config.xml": b"before"}
        self.uid = 10050
        self.replacements = []

    def _mutating(self):
        pass

    def _user_package(self, package):
        if package == "android":
            raise PermissionError("system app")

    def save_installed_apk(self, package, destination):
        Path(destination).write_bytes(self.apk)
        return Path(destination)

    def installed_apk_hashes(self, package, **_):
        return [hashlib.sha256(self.apk).hexdigest()]

    def replace_apk(self, apk, metadata, *, debug_downgrade=False):
        self.apk = Path(apk).read_bytes()
        self.replacements.append(debug_downgrade)
        return {"updated": True}


class FakeRunAsData(RunAsData):
    def identity(self, package):
        return self.client.uid

    def snapshot(self, package, destination):
        destination = Path(destination); destination.mkdir()
        write_tar(destination / "data.tar", self.client.app_data)
        data = {"schema": "mcc-run-as-snapshot-v1", "package": package, "uid": self.client.uid,
                "archive_sha256": hashlib.sha256((destination / "data.tar").read_bytes()).hexdigest(),
                "scope": "synthetic host transaction data", **archive_inventory(destination / "data.tar")}
        (destination / "snapshot.json").write_text(json.dumps(data))
        return data

    def restore(self, directory, *, workdir):
        data = self.load(directory)
        with tarfile.open(Path(directory) / "data.tar", "r:") as archive:
            self.client.app_data = {item.name: archive.extractfile(item).read() for item in archive if item.isfile()}
        return {"restored": True}


class UpdateTransactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = FakeUpdateAndroid()
        self.before = ApkMetadata("org.example.existing", 23, "1", hashlib.sha256(self.client.apk).hexdigest(), len(self.client.apk), None, True)
        self.apk = self.root / "version2.apk"; self.apk.write_bytes(b"synthetic APK version two")
        self.after = ApkMetadata(self.before.package, 23, "2", hashlib.sha256(self.apk.read_bytes()).hexdigest(), self.apk.stat().st_size, None, True)
        self.original_data = deepcopy(self.client.app_data)
        self.transaction = AppTransaction(self.client, self.root / "journal"); self.transaction.begin()
        self.data_patch = patch("monsieur_cuisine_sdk.android_data.RunAsData", FakeRunAsData)
        self.data_patch.start(); self.addCleanup(self.data_patch.stop)
        self.inspect_patch = patch("monsieur_cuisine_sdk.transactions.inspect_apk", return_value=self.before)
        self.inspect_patch.start(); self.addCleanup(self.inspect_patch.stop)

    def test_update_rollback_restores_apk_and_data_without_uninstall(self):
        result = self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        self.assertTrue(result["backup_verified"])
        self.client.app_data = {"files/settings.txt": b"after", "files/new-only": b"new"}
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.apk, b"synthetic APK version one")
        self.assertEqual(self.client.app_data, self.original_data)
        self.assertEqual(self.client.replacements, [False, True])
        self.assertFalse(self.client.removed)
        self.assertTrue(resumed.rollback()["rollback_verified"])

    def test_crash_after_forward_package_replacement_is_recovered(self):
        def crash():
            raise InterruptedError("after successful Android replacement")
        self.transaction._applied = crash
        with self.assertRaises(InterruptedError):
            self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        self.assertTrue(self.transaction.data["actions"][0]["snapshot_ready"])
        self.client.app_data["files/settings.txt"] = b"after"
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.app_data, self.original_data)

    def test_resume_after_downgrade_before_data_restore(self):
        self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        self.client.app_data["files/settings.txt"] = b"after"
        original = self.client.replace_apk
        def crash(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs.get("debug_downgrade"):
                raise InterruptedError("after downgrade before data restore")
            return result
        self.client.replace_apk = crash
        with self.assertRaises(InterruptedError):
            self.transaction.rollback()
        self.client.replace_apk = original
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.app_data, self.original_data)
        self.assertEqual(len(resumed.data["actions"][0]["rollback_data_copies"]), 2)

    def test_external_apk_change_and_uid_change_stop_before_restoration(self):
        self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        self.client.apk = b"external app replacement"
        self.client.app_data["files/settings.txt"] = b"external data"
        with self.assertRaises(AdbError):
            self.transaction.rollback()
        self.assertEqual(self.client.app_data["files/settings.txt"], b"external data")
        self.client.apk = self.apk.read_bytes(); self.client.uid += 1
        with self.assertRaises(AdbError):
            self.transaction.rollback()
        self.assertEqual(self.client.replacements, [False])

    def test_failed_snapshot_leaves_old_apk_and_recoverable_intent(self):
        with patch.object(FakeRunAsData, "snapshot", side_effect=CapabilityError("no app-data access")):
            with self.assertRaises(CapabilityError):
                self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        self.assertFalse(self.client.replacements)
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.app_data, self.original_data)

    def test_non_debuggable_and_corrupt_data_snapshots_never_trigger_downgrade(self):
        production = ApkMetadata(self.after.package, 23, "2", self.after.sha256, self.after.size, None, False)
        with self.assertRaises(CapabilityError):
            self.transaction.update(self.apk, production, aapt="synthetic-aapt")
        self.assertFalse(self.transaction.data["actions"])
        self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        action = self.transaction.data["actions"][0]
        (self.transaction._local(action["snapshot"]) / "before-data/data.tar").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.transaction.rollback()
        self.assertEqual(self.client.replacements, [False])

    def test_snapshot_manifest_cannot_redirect_restoration_into_another_package(self):
        self.transaction.update(self.apk, self.after, aapt="synthetic-aapt")
        action = self.transaction.data["actions"][0]
        path = self.transaction._local(action["snapshot"]) / "before-data/snapshot.json"
        data = json.loads(path.read_text()); data["package"] = "org.example.other"
        path.write_text(json.dumps(data))
        with self.assertRaises(AdbError):
            self.transaction.rollback()
        self.assertEqual(self.client.replacements, [False])
