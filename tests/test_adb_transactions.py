"""ADB host regressions with explicit fake backend; not Android/OEM evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from monsieur_cuisine_sdk.adb import AdbClient, AdbError, ApkMetadata, CapabilityError, inspect_apk, package_name
from monsieur_cuisine_sdk.transactions import AppTransaction


class FakeAndroid:
    """Deterministic transaction fault model; real Android tests are separate."""
    target_digest = "virtual-target"
    serial = "fake-android"

    def __init__(self):
        self.installed = {"android", "org.example.existing"}
        self.homes = ["org.example.existing/.Home"]
        self.settings = {("system", "screen_brightness"): "100", ("system", "screen_off_timeout"): "60000"}
        self.apk_hash = None
        self.removed = []

    def diagnose(self):
        return {"sdk": 23}

    def packages(self, **_):
        return sorted(self.installed)

    def home_preferences(self):
        return self.homes.copy()

    def read_setting(self, namespace, key):
        return self.settings[(namespace, key)]

    def write_setting(self, namespace, key, value):
        self.settings[(namespace, key)] = str(value)

    def install(self, apk, metadata):
        self.installed.add(metadata.package)
        self.apk_hash = metadata.sha256
        return {"installed": True}

    def installed_apk_hashes(self, package, **_):
        return [self.apk_hash]

    def uninstall(self, package):
        self.installed.remove(package)
        self.removed.append(package)

    def start_activity(self, component):
        return {"started": True}

    def select_home(self, component):
        self.homes = [component]


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.client = FakeAndroid()
        self.metadata = ApkMetadata("org.example.added", 23, "1", "1" * 64, 1, None)
        self.transaction = AppTransaction(self.client, self.folder / "journal")
        self.transaction.begin()

    def test_real_journal_roundtrip_multiple_settings_and_idempotent_rollback(self):
        before = deepcopy(self.client.settings)
        self.transaction.install("synthetic.apk", self.metadata)
        self.transaction.setting("system", "screen_brightness", 101)
        self.transaction.setting("system", "screen_brightness", 102)
        self.transaction.home("org.example.added/.Home")
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.settings, before)
        self.assertEqual(self.client.homes, ["org.example.existing/.Home"])
        self.assertEqual(resumed.data["status"], "rolled-back")
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.removed, [self.metadata.package])

    def test_crash_after_install_before_commit_is_compensated(self):
        def crash():
            raise InterruptedError("simulated interruption")
        self.transaction._applied = crash
        with self.assertRaises(InterruptedError):
            self.transaction.install("synthetic.apk", self.metadata)
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertEqual(resumed.data["actions"][0]["phase"], "intent")
        self.assertTrue(resumed.rollback()["rollback_verified"])

    def test_external_apk_change_stops_rollback_without_removing_it(self):
        self.transaction.install("synthetic.apk", self.metadata)
        self.client.apk_hash = "2" * 64
        with self.assertRaises(AdbError):
            self.transaction.rollback()
        self.assertIn(self.metadata.package, self.client.installed)
        self.assertFalse(self.client.removed)

    def test_external_setting_change_is_not_overwritten(self):
        self.transaction.setting("system", "screen_brightness", 101)
        self.client.settings[("system", "screen_brightness")] = "222"
        with self.assertRaises(AdbError):
            self.transaction.rollback()
        self.assertEqual(self.client.settings[("system", "screen_brightness")], "222")

    def test_existing_apps_never_become_rollback_removal_candidates(self):
        existing = ApkMetadata("org.example.existing", 23, "1", "1" * 64, 1, None)
        with self.assertRaises(CapabilityError):
            self.transaction.install("synthetic.apk", existing)
        self.assertFalse(self.transaction.data["actions"])

    def test_corrupt_journal_and_wrong_target_are_rejected(self):
        raw = self.transaction.path.read_bytes()
        self.transaction.path.write_bytes(raw.replace(b'"status": "open"', b'"status": "bad!"'))
        with self.assertRaises(ValueError):
            AppTransaction(self.client, self.transaction.directory).load()
        self.transaction.path.write_bytes(raw)
        self.client.target_digest = "another-device"
        with self.assertRaises(ValueError):
            AppTransaction(self.client, self.transaction.directory).load()

    def test_resume_interrupted_rollback(self):
        self.transaction.install("synthetic.apk", self.metadata)
        original = self.client.uninstall
        def crash(package):
            original(package)
            raise InterruptedError("external uninstall completed before journal commit")
        self.client.uninstall = crash
        with self.assertRaises(InterruptedError):
            self.transaction.rollback()
        self.client.uninstall = original
        resumed = AppTransaction(self.client, self.transaction.directory).load()
        self.assertTrue(resumed.rollback()["rollback_verified"])
        self.assertEqual(self.client.removed, [self.metadata.package])


class AdbBackendTests(unittest.TestCase):
    def test_android_system_package_is_enumerated_but_protected(self):
        commands = []
        def runner(argv, **kwargs):
            commands.append(argv)
            output = "device\n" if argv[-1] == "get-state" else "package:android\npackage:org.example.user\n"
            return subprocess.CompletedProcess(argv, 0, output, "")
        client = AdbClient("adb", serial="emulator-5580", application_changes=True, runner=runner)
        self.assertEqual(client.packages(kind="system"), ["android", "org.example.user"])
        with self.assertRaises(PermissionError):
            client.uninstall("android")
        self.assertFalse(any("uninstall" in command for command in commands))

    def test_explicit_target_and_change_opt_in_are_required(self):
        with self.assertRaises(ValueError):
            AdbClient("adb", serial="")
        commands = []
        client = AdbClient("adb", serial="emulator-5580", runner=lambda *a, **k: commands.append(a))
        with self.assertRaises(PermissionError):
            client.uninstall("org.example.user")
        self.assertFalse(commands)
        for value in ("a;reboot", "org.example.$HOME", "org.example/a b"):
            with self.assertRaises(ValueError):
                package_name(value)

    def test_apk_manifest_is_read_not_inferred_from_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "renamed.apk"
            apk.write_bytes(b"opaque synthetic APK bytes")
            def runner(argv, **kwargs):
                self.assertEqual(argv[1:3], ["dump", "badging"])
                return subprocess.CompletedProcess(argv, 0, "package: name='org.example.test' versionCode='7'\nsdkVersion:'23'\nlaunchable-activity: name='org.example.test.Home'\n", "")
            metadata = inspect_apk(apk, aapt="aapt", runner=runner)
            self.assertEqual(metadata.package, "org.example.test")
            self.assertEqual(metadata.minimum_sdk, 23)
            self.assertEqual(metadata.sha256, hashlib.sha256(apk.read_bytes()).hexdigest())

    def test_api23_home_capability_is_reported_without_fake_success(self):
        def runner(argv, **_):
            return subprocess.CompletedProcess(argv, 0, "device" if argv[-1] == "get-state" else "pm install pm uninstall", "")
        client = AdbClient("adb", serial="emulator-5580", application_changes=True, runner=runner)
        with self.assertRaises(CapabilityError):
            client.select_home("org.example.test/.Home")
