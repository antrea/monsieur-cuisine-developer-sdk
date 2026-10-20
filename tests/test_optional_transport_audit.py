"""Protect zero-dependency startup while permitting one opt-in serial backend."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_release import audit


class OptionalTransportAudit(unittest.TestCase):
    def test_optional_import_cannot_move_to_module_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "src/monsieur_cuisine_sdk/hardware.py"
            path.parent.mkdir(parents=True)
            path.write_text("class SerialTransport:\n    def open(self):\n        from serial import Serial\n", encoding="utf-8")
            self.assertTrue(audit(root, project_checks=False)["passed"])
            path.write_text("import serial\nclass SerialTransport:\n    def open(self):\n        pass\n", encoding="utf-8")
            result = audit(root, project_checks=False)
            self.assertFalse(result["passed"])
            self.assertTrue(any(i.get("module") == "serial" for i in result["issues"]))

    def test_import_and_construction_need_no_serial_package_or_device(self):
        code = "import sys; from monsieur_cuisine_sdk.hardware import SerialTransport; SerialTransport('explicit-unused-port'); assert 'serial' not in sys.modules"
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
