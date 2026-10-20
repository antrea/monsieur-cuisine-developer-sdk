"""Explicit deletion of SDK-created backup outputs: markers, bounds, links, completeness and the CLI."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from monsieur_cuisine_sdk.backup.cleanup import describe_output, discard_output
from monsieur_cuisine_sdk.backup.cli import main
from test_backup_manager import make_disk, write_session


def make_output(base: Path, name: str, status: str, *, kind="import") -> Path:
    directory = base / name
    (directory / "backup_session" / "partitions").mkdir(parents=True)
    (directory / "backup_session" / "partitions" / "boot.bin").write_bytes(b"x" * 4096)
    (directory / "backup_session" / "SHA256SUMS.txt").write_bytes(b"")
    if kind == "import":
        marker = {"schema": "mcc-backup-import-v1", "status": status}
        (directory / "import-status.json").write_text(json.dumps(marker), encoding="utf-8")
    else:
        marker = {"schema": "mcc-image-recovery-v1", "status": status, "bytes": 1}
        (directory / "image-transaction.json").write_text(json.dumps(marker), encoding="utf-8")
    return directory


class DiscardOutputs(unittest.TestCase):
    def test_incomplete_import_is_removed_and_source_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"; write_session(source, make_disk())
            before = sorted(p.relative_to(source).as_posix() for p in source.rglob("*"))
            output = make_output(base, "import", "failed")
            read_only = output / "backup_session" / "partitions" / "boot.bin"
            os.chmod(read_only, stat.S_IREAD)
            self.assertEqual(describe_output(output)["kind"], "import")
            expected_bytes = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
            result = discard_output(output)
            self.assertFalse(output.exists())
            self.assertEqual((result["removed_files"], result["removed_bytes"], result["directory_removed"]),
                             (3, expected_bytes, True))
            self.assertGreaterEqual(expected_bytes, 4096)
            self.assertEqual(before, sorted(p.relative_to(source).as_posix() for p in source.rglob("*")))

    def test_complete_outputs_need_explicit_consent_and_recovery_marker_is_recognized(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = make_output(base, "recovery", "complete", kind="recovery")
            self.assertEqual(describe_output(output)["kind"], "recovery")
            with self.assertRaises(ValueError):
                discard_output(output)
            self.assertTrue(output.exists())
            self.assertTrue(discard_output(output, include_complete=True)["directory_removed"])

    def test_sessions_plain_folders_and_bad_markers_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            session = base / "session"; write_session(session, make_disk())
            with self.assertRaises(ValueError):
                discard_output(session)
            plain = base / "plain"; plain.mkdir(); (plain / "file.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                discard_output(plain)
            wrong = make_output(base, "wrong", "failed")
            (wrong / "import-status.json").write_text(json.dumps({"schema": "other"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                discard_output(wrong)
            self.assertTrue(session.exists() and plain.exists() and wrong.exists())
            with self.assertRaises(ValueError):
                discard_output(base / "missing")

    def test_links_inside_the_output_block_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = make_output(base, "linked", "interrupted")
            outside = base / "outside.bin"; outside.write_bytes(b"precious")
            try:
                os.symlink(outside, output / "backup_session" / "link.bin")
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links are not available to this user")
            with self.assertRaises(ValueError):
                discard_output(output)
            self.assertTrue(outside.exists() and (output / "backup_session" / "partitions" / "boot.bin").exists())

    def test_cancellation_keeps_the_remainder(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = make_output(Path(tmp), "cancel", "failed")
            with self.assertRaises(InterruptedError):
                discard_output(output, cancelled=lambda: True)
            self.assertTrue(output.exists())

    def test_cli_describes_without_yes_and_deletes_with_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = make_output(Path(tmp), "cli", "failed")
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(main(["discard", str(output)]), 0)
            described = json.loads(captured.getvalue())
            self.assertFalse(described["deleted"])
            self.assertNotIn(str(output), captured.getvalue())
            self.assertTrue(output.exists())
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(main(["discard", str(output), "--yes"]), 0)
            self.assertTrue(json.loads(captured.getvalue())["directory_removed"])
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["discard", str(output), "--yes"]), 2)


class DiscardButton(unittest.TestCase):
    def test_panel_button_refuses_sources_and_deletes_incomplete_output(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception:
            self.skipTest("no Tk display")
        from monsieur_cuisine_sdk.backup.gui import BackupPanel
        try:
            panel = BackupPanel(root)
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                session = base / "session"; write_session(session, make_disk())
                panel.destination.set(str(session)); panel.discard(confirm=True)
                self.assertTrue(session.exists()); self.assertIn("nothing deleted", panel.status.get())
                complete = make_output(base, "done", "complete")
                panel.destination.set(str(complete)); panel.discard(confirm=True)
                self.assertTrue(complete.exists()); self.assertIn("complete", panel.status.get())
                partial = make_output(base, "partial", "interrupted")
                panel.destination.set(str(partial)); panel.discard(confirm=False)
                self.assertTrue(partial.exists())
                panel.discard(confirm=True)
                self.assertFalse(partial.exists()); self.assertTrue(panel.last_result["directory_removed"])
            panel.close()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
