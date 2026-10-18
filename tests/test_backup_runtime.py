"""External tool trust/execution boundaries and actual session comparisons.

Synthetic tool ZIPs below exercise host plumbing only. They are not OEM/tool
reference evidence; the owner's real tool is exercised separately in private.
"""
import io
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from monsieur_cuisine_sdk.backup.compare import compare_sessions
from monsieur_cuisine_sdk.backup.runtime import MCCBackupRuntime
from test_backup_manager import make_disk, write_session


def fake_tool(path, members):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("MCCBackup_1.0_tool/MCCBackup_1.0_source.zip", inner.getvalue())


class ExternalToolBoundaries(unittest.TestCase):
    def test_original_process_is_stopped_on_timeout_or_cancel_without_false_success(self):
        from monsieur_cuisine_sdk.backup.importer import copy_session
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"; write_session(source, make_disk())
            copy_session(source, root / "staged", materialize=True)
            archive = root / "synthetic-tool.zip"
            # This is a synthetic process-management fixture, not OEM evidence.
            fake_tool(archive, {"bundle/src/verify_offline.py": b"import time\nprint('synthetic running', flush=True)\ntime.sleep(20)\n"})
            runtime = MCCBackupRuntime(archive)
            with patch.object(runtime, "inspect", return_value={"release_verified": True}):
                runtime.provision(root / "tool")
                real_popen = subprocess.Popen
                children = []
                def launch(*args, **kwargs):
                    child = real_popen(*args, **kwargs)
                    if "-I" in args[0]:
                        children.append(child)
                    return child
                with patch("monsieur_cuisine_sdk.backup.runtime.subprocess.Popen", side_effect=launch):
                    with self.assertRaises(TimeoutError):
                        runtime.offline_verify(root / "tool", root / "staged/backup_session", root / "timeout",
                                               python=sys.executable, timeout=.2)
                    stop = False
                    def progress(_):
                        nonlocal stop
                        stop = True
                    with self.assertRaises(InterruptedError):
                        runtime.offline_verify(root / "tool", root / "staged/backup_session", root / "cancelled",
                                               python=sys.executable, cancelled=lambda: stop, progress=progress)
                self.assertEqual(len(children), 2)
                self.assertTrue(all(child.poll() is not None for child in children))
                self.assertFalse((root / "timeout/VERIFY_REPORT.txt").exists())
                # No surviving redirector descendant may retain the log handle.
                for directory in ("timeout", "cancelled"):
                    (root / directory / "process.log").unlink()

    def test_unknown_distribution_is_never_extracted_or_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "tool.zip"
            fake_tool(original, {"bundle/src/verify_offline.py": b"print('synthetic')"})
            runtime = MCCBackupRuntime(original)
            with self.assertRaises(ValueError):
                runtime.provision(root / "output")
            self.assertFalse((root / "output").exists())

    def test_acquisition_has_an_explicit_gate_before_any_access(self):
        with self.assertRaises(PermissionError):
            MCCBackupRuntime("unused.zip").start_acquisition("unused", "unused")

    def test_provision_hash_validation_and_additional_file_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "tool.zip"
            fake_tool(original, {"bundle/src/verify_offline.py": b"print('synthetic')", "bundle/LICENSE.txt": b"test fixture"})
            runtime = MCCBackupRuntime(original)
            with patch.object(runtime, "inspect", return_value={"release_verified": True}):
                self.assertEqual(runtime.provision(root / "output")["files_verified"], 2)
                (root / "output/extra.py").write_text("unrecognized executable input")
                with self.assertRaises(ValueError):
                    runtime.verify_installation(root / "output")
                (root / "output/extra.py").unlink()
                (root / "output/bundle/src/verify_offline.py").write_text("changed")
                with self.assertRaises(ValueError):
                    runtime.verify_installation(root / "output")

    def test_archive_traversal_is_rejected_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "tool.zip"
            fake_tool(original, {"../escape.py": b"bad"})
            runtime = MCCBackupRuntime(original)
            with patch.object(runtime, "inspect", return_value={"release_verified": True}):
                with self.assertRaises(ValueError):
                    runtime.provision(root / "output")
            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "escape.py").exists())


class BackupComparisons(unittest.TestCase):
    def test_equal_and_different_valid_backups_are_distinguished(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            disk = make_disk()
            write_session(first, disk); write_session(second, disk)
            result = compare_sessions(first, second)
            self.assertTrue(result["same_full_user_area"])
            self.assertTrue(result["same_partition_content"])
            self.assertIsNone(result["model_property_match"])
            third = root / "third"
            changed = bytearray(disk); changed[80 * 512] ^= 1
            write_session(third, bytes(changed))
            result = compare_sessions(first, third)
            self.assertTrue(result["same_layout"])
            self.assertFalse(result["same_full_user_area"])
            self.assertFalse(result["same_partition_content"])
            self.assertTrue(result["both_backups_validated"])
            self.assertEqual(result["hardware_compatibility"], "UNVERIFIED")

    def test_corrupt_backup_never_produces_a_compatibility_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            disk = make_disk()
            write_session(first, disk); write_session(second, disk)
            (second / "partitions_extracted/beta.bin").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                compare_sessions(first, second)
