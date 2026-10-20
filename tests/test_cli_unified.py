"""Exercise the public offline CLI against both actual profile implementations."""
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.cli import main


class UnifiedCliTests(unittest.TestCase):
    def invoke(self, model, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(["--model", model, *map(str, arguments)])
        return status, json.loads(output.getvalue()) if output.getvalue() else None, errors.getvalue()

    def test_model_is_explicit_and_version_is_unified(self):
        for args, expected in ((["capabilities"], 2), (["--version"], 0)):
            result = subprocess.run([sys.executable, "-B", "-m", "monsieur_cuisine_sdk.cli", *args],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, expected, result.stderr)
            if expected == 0:
                from monsieur_cuisine_sdk import __version__
                self.assertEqual(result.stdout.strip(), __version__)

    def test_capabilities_import_without_tk_or_socket(self):
        for model in ("mcc", "mcs"):
            result = subprocess.run([sys.executable, "-B", "-c",
                "import sys; from monsieur_cuisine_sdk.cli import main; "
                f"status=main(['--model','{model}','capabilities']); "
                "assert status==0; assert 'tkinter' not in sys.modules; assert 'socket' not in sys.modules"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_common_build_decode_and_inspect_use_selected_bytes(self):
        for model, size in (("mcc", 15), ("mcs", 39)):
            status, built, errors = self.invoke(model, "build", "start", "--speed", 2, "--temperature", 60)
            self.assertEqual(status, 0, errors)
            self.assertEqual(len(bytes.fromhex(built["hex"])), size)
            status, decoded, errors = self.invoke(model, "decode", built["hex"], "--direction", "tx")
            self.assertEqual(status, 0, errors)
            self.assertEqual(decoded["model"], model)
            status, inspected, errors = self.invoke(model, "inspect", "--hex", built["hex"], "--direction", "tx")
            self.assertEqual(status, 0, errors)
            self.assertTrue(inspected["inspection"])

    def test_profile_specific_fields_fail_explicitly(self):
        for model, args in (("mcc", ("build", "start", "--duration", 1)),
                            ("mcc", ("build", "start", "--temperature", 40)),
                            ("mcc", ("build", "query")), ("mcc", ("build", "ota")),
                            ("mcs", ("build", "tx")),
                            ("mcc", ("build", "tx", "--speed", 3)),
                            ("mcc", ("conformance", "--corpus", "envelope"))):
            with self.subTest(model=model, args=args):
                status, result, errors = self.invoke(model, *args)
                self.assertEqual(status, 2)
                self.assertIsNone(result)
                self.assertIn("message", json.loads(errors))
        self.assertEqual(self.invoke("mcs", "build", "start", "--temperature", 40, "--duration", 1)[0], 0)

    def test_native_builders_retain_distinct_ota_and_operation_shapes(self):
        self.assertEqual(self.invoke("mcc", "build", "tx", "--params", '{"operation":"turbo","speed":10}')[0], 0)
        self.assertEqual(self.invoke("mcs", "build", "manual", "--params", '{"speed":2,"seconds":12}')[0], 0)
        status, built, errors = self.invoke("mcs", "build", "ota", "--params", '{"subcommand":2,"data_hex":"0102"}')
        self.assertEqual(status, 0, errors)
        self.assertEqual(len(bytes.fromhex(built["hex"])), 269)
        self.assertEqual(built["decoded"]["opcode"], "FE02")

    def test_wrong_profile_and_conflicting_sources_rejected(self):
        built = self.invoke("mcc", "build", "stop")[1]["hex"]
        self.assertEqual(self.invoke("mcs", "decode", built, "--direction", "tx")[0], 2)
        self.assertEqual(self.invoke("mcc", "decode", built, "--hex", built)[0], 2)

    def test_stream_validation_retains_recovered_frame_and_noise_failure(self):
        for model in ("mcc", "mcs"):
            built = self.invoke(model, "build", "stop")[1]["hex"]
            with tempfile.TemporaryDirectory(prefix="mc-cli-") as folder:
                path = Path(folder) / "stream.bin"
                path.write_bytes(b"noise" + bytes.fromhex(built))
                status, result, errors = self.invoke(model, "validate", "--file", path, "--input-format", "binary", "--direction", "tx")
                self.assertEqual(status, 1, errors)
                self.assertEqual(result["frame_count"], 1)
                self.assertTrue(result["issues"])

    def test_record_replay_and_csv_preserve_units_for_both_profiles(self):
        with tempfile.TemporaryDirectory(prefix="mc-record-") as folder:
            for model in ("mcc", "mcs"):
                path, csv_path = Path(folder) / (model + ".json"), Path(folder) / (model + ".csv")
                status, recorded, errors = self.invoke(model, "record", "--file", path, "--seconds", 0.2)
                self.assertEqual(status, 0, errors)
                status, replayed, errors = self.invoke(model, "replay", path)
                self.assertEqual(status, 0, errors)
                self.assertEqual(replayed["state"], recorded["state"])
                status, result, errors = self.invoke(model, "telemetry", path, "--input-format", "recording", "--csv", csv_path)
                self.assertEqual(status, 0, errors)
                self.assertTrue(result["rows"])
                expected_unit = "rpm" if model == "mcc" else "raw_motor_level"
                self.assertEqual(result["rows"][0]["speed_unit"], expected_unit)
                with csv_path.open(newline="", encoding="utf-8") as stream:
                    self.assertEqual(next(csv.DictReader(stream))["model"], model)
                other = "mcs" if model == "mcc" else "mcc"
                self.assertEqual(self.invoke(other, "replay", path)[0], 2)

    def test_corrupt_recording_expectation_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="mc-invalid-") as folder:
            path = Path(folder) / "session.json"
            self.assertEqual(self.invoke("mcc", "record", "--file", path, "--seconds", 0)[0], 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["actions"][0]["rx_hex"][0] = "00"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(self.invoke("mcc", "replay", path)[0], 2)

    def test_record_capacity_saves_the_valid_disarmed_trace(self):
        class ShortRecording(DigitalTwin):
            def __init__(self, *args, **kwargs):
                kwargs["max_actions"] = 4
                super().__init__(*args, **kwargs)
        with tempfile.TemporaryDirectory(prefix="mc-capacity-") as folder:
            path = Path(folder) / "ended.json"
            with patch("monsieur_cuisine_sdk.api.DigitalTwin", ShortRecording):
                status, result, errors = self.invoke("mcc", "record", "--file", path, "--seconds", 1)
            self.assertEqual(status, 1, errors)
            self.assertIsNotNone(result["ended"])
            self.assertTrue(path.exists())
            self.assertEqual(result["state"]["requested_speed"], 0)
            self.assertEqual(self.invoke("mcc", "replay", path)[0], 0)

    def test_jsonl_analysis_handles_each_profile(self):
        with tempfile.TemporaryDirectory(prefix="mc-jsonl-") as folder:
            for model in ("mcc", "mcs"):
                twin = DigitalTwin(model)
                rx = twin.sample()[0]
                path = Path(folder) / (model + ".jsonl")
                path.write_text(json.dumps({"time": 0, "direction": "rx", "hex": rx.hex()}) + "\n", encoding="utf-8")
                status, result, errors = self.invoke(model, "analyze", path, "--input-format", "jsonl")
                self.assertEqual(status, 0, errors)
                self.assertEqual(result["frame_count"], 1)

    def test_expected_corruption_in_valid_recording_remains_visible(self):
        with tempfile.TemporaryDirectory(prefix="mc-corrupt-rx-") as folder:
            for model in ("mcc", "mcs"):
                twin = DigitalTwin(model)
                twin.set_faults(corrupt_next=1)
                twin.sample()
                path = Path(folder) / (model + ".json")
                twin.save(path)
                status, result, errors = self.invoke(model, "analyze", path, "--input-format", "recording")
                self.assertEqual(status, 1, errors)
                self.assertFalse(result["valid"])
                self.assertTrue(result["issues"])

    def test_separate_frozen_conformance_corpora(self):
        for model, corpus, count in (("mcc", "operational", 8), ("mcs", "operational", 900), ("mcs", "envelope", 900)):
            status, result, errors = self.invoke(model, "conformance", "--corpus", corpus)
            self.assertEqual(status, 0, errors)
            self.assertEqual(result["count"], count)
            self.assertTrue(result["passed"])

    def test_scenario_and_stress_use_common_model_selector(self):
        for model in ("mcc", "mcs"):
            for args in (("scenario", "start_stop"), ("simulate", "start_stop"), ("stress", "--count", 2)):
                status, result, errors = self.invoke(model, *args)
                self.assertEqual(status, 0, errors)
                self.assertTrue(result.get("PASS", result.get("passed")))


if __name__ == "__main__":
    unittest.main()
