"""Real file restore transactions on synthetic images; never device writes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from monsieur_cuisine_sdk.recovery import ImageRecovery, prepare_restore_plan
from test_backup_manager import make_disk, write_session


class ImageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.disk = make_disk()
        write_session(self.source, self.disk)
        self.recovery = ImageRecovery(self.source, self.root / "restored", chunk_bytes=1024)

    def test_plan_reports_hardware_gaps_and_restore_matches_entire_image(self):
        plan = self.recovery.prepare()
        self.assertTrue(plan["source_verified"])
        self.assertFalse(plan["physical_execution_enabled"])
        self.assertFalse(plan["mcc_required_partitions_present"])
        self.assertIn("RPMB is absent", plan["limitations"])
        result = self.recovery.execute()
        self.assertTrue(result["complete"])
        self.assertEqual(self.recovery.output.read_bytes(), self.disk)
        self.assertEqual(result["sha256"], hashlib.sha256(self.disk).hexdigest())
        self.assertEqual(result["physical_writes"], 0)
        self.assertEqual(json.loads(self.recovery.journal.read_text())["status"], "complete")

    def test_resume_after_durable_chunks_and_verify_again(self):
        self.recovery.prepare()
        result = self.recovery.execute(max_chunks=3)
        self.assertFalse(result["complete"])
        self.assertEqual(result["bytes"], 3072)
        resumed = ImageRecovery(self.source, self.recovery.directory, chunk_bytes=1024)
        self.assertTrue(resumed.execute()["complete"])
        self.assertTrue(resumed.execute()["complete"])
        self.assertEqual(resumed.output.read_bytes(), self.disk)

    def test_power_loss_after_data_before_complete_ledger_record(self):
        self.recovery.prepare()
        self.recovery.execute(max_chunks=2)
        with self.recovery.output.open("ab") as output:
            output.write(self.disk[2048:3072])
        with self.recovery.ledger.open("ab") as ledger:
            ledger.write(b'{"offset":2048,"bytes":1024,')
        self.assertTrue(self.recovery.execute()["complete"])
        self.assertEqual(self.recovery.output.read_bytes(), self.disk)

    def test_corrupt_prefix_refuses_resume_without_overwriting(self):
        self.recovery.prepare()
        self.recovery.execute(max_chunks=2)
        with self.recovery.output.open("r+b") as output:
            output.write(b"bad!")
        before = self.recovery.output.read_bytes()
        with self.assertRaises(ValueError):
            self.recovery.execute()
        self.assertEqual(self.recovery.output.read_bytes(), before)

    def test_uncommitted_foreign_tail_is_not_truncated(self):
        self.recovery.prepare()
        self.recovery.execute(max_chunks=2)
        with self.recovery.output.open("ab") as output:
            output.write(b"not source bytes")
        before = self.recovery.output.read_bytes()
        with self.assertRaises(ValueError):
            self.recovery.execute()
        self.assertEqual(self.recovery.output.read_bytes(), before)

    def test_never_overwrite_source_or_existing_output_directory(self):
        with self.assertRaises(ValueError):
            ImageRecovery(self.source, self.source / "output")
        self.recovery.directory.mkdir()
        with self.assertRaises(ValueError):
            self.recovery.prepare()
        self.assertFalse(self.recovery.output.exists())

    def test_source_tampering_fails_preflight(self):
        partition = self.source / "partitions_extracted/beta.bin"
        partition.write_bytes(b"x" * partition.stat().st_size)
        with self.assertRaises(ValueError):
            self.recovery.prepare()
        self.assertFalse(self.recovery.directory.exists())

    def test_wrong_ledger_geometry_and_source_manifest_are_rejected(self):
        self.recovery.prepare()
        self.recovery.execute(max_chunks=1)
        row = json.loads(self.recovery.ledger.read_text())
        row["offset"] = 1
        self.recovery.ledger.write_text(json.dumps(row) + "\n")
        with self.assertRaises(ValueError):
            self.recovery.execute()

    def test_hard_link_cannot_turn_new_image_into_source_overwrite(self):
        self.recovery.prepare()
        self.recovery.output.unlink()
        other = self.root / "do-not-modify.bin"
        other.write_bytes(self.disk)
        os.link(other, self.recovery.output)
        with self.assertRaises(ValueError):
            self.recovery.execute()
        self.assertEqual(other.read_bytes(), self.disk)

    def test_complete_image_can_be_verified_read_only_after_external_staging(self):
        self.recovery.prepare()
        self.recovery.execute()
        linked = self.root / "legacy-input.bin"
        os.link(self.recovery.output, linked)
        self.assertTrue(self.recovery.execute()["complete"])
        self.assertEqual(linked.read_bytes(), self.disk)
