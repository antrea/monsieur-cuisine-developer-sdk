"""Real private-file imports and independent validation on synthetic disk data."""
import contextlib
import hashlib
import io
import json
import stat
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from monsieur_cuisine_sdk.backup.cli import main
from monsieur_cuisine_sdk.backup.importer import copy_session, import_archive, import_backup, import_raw_image
from monsieur_cuisine_sdk.backup.session import BackupSession, FULL_IMAGE
from monsieur_cuisine_sdk.backup.verify import verify_session
from test_backup_manager import make_disk, write_session


def zip_session(source, archive, prefix="backup/session", extra=None):
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                name = (Path(prefix) / path.relative_to(source)).as_posix()
                output.writestr(name, path.read_bytes())
        for name, value in (extra or {}).items():
            output.writestr(name, value)


class PrivateBackupImports(unittest.TestCase):
    def test_special_files_are_refused_before_zip_detection_or_manifest_reads(self):
        from types import SimpleNamespace
        from monsieur_cuisine_sdk.backup.session import read_manifest
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.bin"; source.write_bytes(b"not a device")
            with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR, st_size=0)):
                with patch("monsieur_cuisine_sdk.backup.importer.zipfile.is_zipfile") as detected:
                    with self.assertRaises(ValueError):
                        import_backup(source, root / "output")
                    detected.assert_not_called()
                with patch.object(Path, "read_text") as read:
                    with self.assertRaises(ValueError):
                        read_manifest(source)
                    read.assert_not_called()

    def test_inapplicable_import_flags_are_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"; write_session(source, make_disk())
            with self.assertRaises(ValueError):
                import_backup(source, root / "output", expected_sha256="0" * 64)

    def test_verified_copy_and_materialized_stage_preserve_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            disk = make_disk()
            write_session(source, disk)
            (source / "hwparam.json").write_text('"private unreferenced metadata"')
            before = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
            copied = copy_session(source, root / "copy")
            self.assertTrue(copied["passed"])
            self.assertFalse(copied["full_image_materialized"])
            self.assertFalse((root / "copy/backup_session/hwparam.json").exists())
            staged = copy_session(source, root / "staged", materialize=True)
            self.assertTrue(staged["full_image_materialized"])
            self.assertEqual((root / "staged/backup_session" / FULL_IMAGE).read_bytes(), disk)
            self.assertTrue(verify_session(root / "staged/backup_session").passed)
            self.assertFalse((root / "staged/backup_session/emmc_boot1.bin").samefile(source / "emmc_boot1.bin"))
            self.assertEqual(before, {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()})
            self.assertNotIn(str(source), json.dumps(staged))

    def test_zip_import_selects_session_and_excludes_unrelated_archive_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            archive = root / "backup.zip"
            zip_session(source, archive, extra={"private-outside-session.txt": b"not selected"})
            result = import_backup(archive, root / "imported")
            self.assertTrue(result["complete"])
            self.assertEqual(result["archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertFalse((root / "imported/private-outside-session.txt").exists())
            self.assertTrue(verify_session(root / "imported/backup_session").passed)
            self.assertEqual(json.loads((root / "imported/import-status.json").read_text())["status"], "complete")

    def test_ambiguous_zip_requires_explicit_session_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            archive = root / "ambiguous.zip"
            with zipfile.ZipFile(archive, "w") as output:
                for prefix in ("one", "two"):
                    for path in source.rglob("*"):
                        if path.is_file():
                            output.write(path, prefix + "/" + path.relative_to(source).as_posix())
            with self.assertRaises(ValueError):
                import_archive(archive, root / "rejected")
            self.assertFalse((root / "rejected").exists())
            self.assertTrue(import_archive(archive, root / "selected", session_member="two")["complete"])

    def test_unsafe_zip_paths_special_files_collisions_and_bounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_sets = [
                {"../escape": b"x"}, {"CON.bin": b"x"}, {"a. /b": b"x"},
                {"a": b"x", "a/b": b"x"}, {"Case": b"x", "case": b"y"},
                {"a//b": b"x"}, {"a/./b": b"x"}, {"a:stream": b"x"},
            ]
            for index, bad in enumerate(bad_sets):
                archive = root / f"bad{index}.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    for name, data in bad.items():
                        output.writestr(name, data)
                with self.assertRaises(ValueError):
                    import_archive(archive, root / f"output{index}")
                self.assertFalse((root / f"output{index}").exists())
            link = zipfile.ZipInfo("symlink")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            archive = root / "link.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(link, "target")
            with self.assertRaises(ValueError):
                import_archive(archive, root / "linked")
            with self.assertRaises(ValueError):
                import_archive(archive, root / "oversize", max_member=1)

    def test_corrupt_import_is_not_reported_complete_and_original_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            (source / "partitions/beta.bin").write_bytes(b"wrong content")
            archive = root / "corrupt.zip"
            zip_session(source, archive)
            before = archive.read_bytes()
            with self.assertRaises(ValueError):
                import_archive(archive, root / "incomplete")
            state = json.loads((root / "incomplete/import-status.json").read_text())
            self.assertEqual(state["status"], "failed")
            self.assertEqual(archive.read_bytes(), before)

    def test_cancelled_extraction_leaves_explicit_incomplete_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            archive = root / "backup.zip"
            zip_session(source, archive)
            stop = False
            def progress(_):
                nonlocal stop
                stop = True
            with self.assertRaises(InterruptedError):
                import_archive(archive, root / "partial", progress=progress, cancelled=lambda: stop)
            self.assertEqual(json.loads((root / "partial/import-status.json").read_text())["status"], "interrupted")
            with self.assertRaises(ValueError):
                import_archive(archive, root / "partial")

    def test_existing_nested_or_low_space_outputs_never_receive_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            for destination in (source, source / "nested"):
                with self.assertRaises(ValueError):
                    copy_session(source, destination)
            self.assertFalse((source / "nested").exists())
            with patch("monsieur_cuisine_sdk.backup.importer.shutil.disk_usage", return_value=type("Usage", (), {"free": 0})()):
                with self.assertRaises(OSError):
                    copy_session(source, root / "no-space")
            self.assertFalse((root / "no-space").exists())

    def test_raw_image_partitions_are_extracted_from_actual_full_disk_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            disk = make_disk()
            write_session(source, disk)
            image = root / "user.bin"
            image.write_bytes(disk)
            result = import_raw_image(image, root / "raw", boot1=source / "emmc_boot1.bin", boot2=source / "emmc_boot2.bin",
                                      expected_sha256=hashlib.sha256(disk).hexdigest())
            self.assertTrue(result["independent_hash_provided"])
            imported = BackupSession.open(root / "raw/backup_session")
            self.assertTrue(imported.has_full_image)
            for name in ("alpha", "beta", "gamma"):
                self.assertEqual(imported.partition_file(name).read_bytes(), (source / "partitions_extracted" / (name + ".bin")).read_bytes())
            self.assertTrue(verify_session(imported.root).passed)

    def test_raw_import_rejects_missing_boot_areas_wrong_hash_and_bad_gpt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            image = root / "disk.bin"
            image.write_bytes(make_disk())
            with self.assertRaises(ValueError):
                import_backup(image, root / "missing-boots")
            with self.assertRaises(ValueError):
                import_raw_image(image, root / "bad-hash", boot1=source / "emmc_boot1.bin", boot2=source / "emmc_boot2.bin", expected_sha256="0" * 64)
            self.assertEqual(json.loads((root / "bad-hash/import-status.json").read_text())["status"], "failed")
            raw = bytearray(image.read_bytes()); raw[-512] ^= 1
            image.write_bytes(raw)
            with self.assertRaises(ValueError):
                import_raw_image(image, root / "bad-gpt", boot1=source / "emmc_boot1.bin", boot2=source / "emmc_boot2.bin")
            self.assertFalse((root / "bad-gpt").exists())

    def test_import_and_stage_cli_execute_real_operations_without_path_disclosure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            write_session(source, make_disk())
            for command, output in (("import-backup", root / "imported"), ("stage", root / "staged")):
                text = io.StringIO()
                with contextlib.redirect_stdout(text):
                    result = main([command, str(source), str(output)])
                self.assertEqual(result, 0)
                self.assertTrue(json.loads(text.getvalue())["complete"])
                self.assertNotIn(str(root), text.getvalue())
            self.assertEqual((root / "staged/backup_session" / FULL_IMAGE).read_bytes(), make_disk())
