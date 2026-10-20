"""Explicit deletion of SDK-created backup outputs: markers, bounds, links, completeness and the CLI."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from monsieur_cuisine_sdk.backup import cleanup
from monsieur_cuisine_sdk.backup.cleanup import describe_output, discard_output
from monsieur_cuisine_sdk.backup.cli import main
from test_backup_manager import make_disk, write_session


def make_junction(link: Path, target: Path):
    """Create a Windows directory junction (no privilege needed); skip elsewhere."""
    if os.name != "nt":
        raise unittest.SkipTest("directory junctions exist only on Windows")
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                          capture_output=True, text=True, timeout=30)
    if done.returncode or not link.exists():
        raise unittest.SkipTest("could not create a junction: " + done.stdout + done.stderr)


def remove_junction(link: Path):
    # rmdir on a junction removes only the reparse point, never the target's content.
    if os.path.lexists(link):
        os.rmdir(link)


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


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

    def test_junction_detection_does_not_depend_on_path_is_junction(self):
        # Python 3.11 has no Path.is_junction(); detection must come from lstat attributes.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "target"; target.mkdir()
            link = base / "link"
            make_junction(link, target)
            try:
                self.assertTrue(cleanup._is_link(link))
                self.assertFalse(cleanup._is_link(target))
                with patch.object(Path, "is_junction", create=True, new=lambda self: False):
                    self.assertTrue(cleanup._is_link(link))
            finally:
                remove_junction(link)

    def test_root_junction_to_a_marked_output_is_refused_and_nothing_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = make_output(base, "target", "failed")
            (target / "sentinel.txt").write_text("keep", encoding="utf-8")
            link = base / "link"
            make_junction(link, target)
            try:
                before = snapshot(target)
                with self.assertRaises(ValueError):
                    describe_output(link)
                with self.assertRaises(ValueError):
                    discard_output(link)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["discard", str(link), "--yes"]), 2)
                self.assertEqual(before, snapshot(target))
            finally:
                remove_junction(link)

    def test_nested_junction_to_a_sibling_is_refused_before_any_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = make_output(base, "output", "failed")
            sibling = base / "sibling"; sibling.mkdir()
            (sibling / "sentinel.txt").write_text("outside the output", encoding="utf-8")
            link = output / "backup_session" / "nested"
            make_junction(link, sibling)
            try:
                before_output, before_sibling = snapshot(output), snapshot(sibling)
                with self.assertRaises(ValueError):
                    discard_output(output)
                self.assertEqual(before_sibling, snapshot(sibling))
                self.assertEqual(before_output, snapshot(output))   # refusal deletes nothing inside either
            finally:
                remove_junction(link)

    def test_folder_swapped_for_a_junction_after_enumeration_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = make_output(base, "output", "failed")
            outside = base / "outside"; outside.mkdir()
            (outside / "boot.bin").write_bytes(b"outside sentinel")
            partitions = output / "backup_session" / "partitions"
            original = cleanup._enumerate

            def swap_after_enumeration(directory, cancelled):
                result = original(directory, cancelled)
                for item in partitions.iterdir():
                    os.chmod(item, stat.S_IWRITE | stat.S_IREAD); item.unlink()
                partitions.rmdir()
                make_junction(partitions, outside)
                return result

            try:
                with patch.object(cleanup, "_enumerate", swap_after_enumeration):
                    with self.assertRaises(ValueError):
                        discard_output(output)
                self.assertEqual((outside / "boot.bin").read_bytes(), b"outside sentinel")
            finally:
                remove_junction(partitions)

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
