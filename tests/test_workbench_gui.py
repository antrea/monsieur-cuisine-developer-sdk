"""Actual native panels and worker results; no ADB device is contacted here."""
import json
from pathlib import Path
import tempfile
import time

from gui_process import NativeGuiTestCase


class WorkbenchGuiTests(NativeGuiTestCase):
    def test_native_reference_comparison_and_safe_default_app_controls(self):
        import json
        from pathlib import Path
        import tempfile
        import time
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        from monsieur_cuisine_sdk.workbench import AppManagerPanel, ConformancePanel
        root = tk.Tk()
        app = DesktopApp(root)
        try:
            panels = app.toolkit_panel.panels
            apps = next(p for p in panels if isinstance(p, AppManagerPanel))
            conformance = next(p for p in panels if isinstance(p, ConformancePanel))
            assert not apps.allow_changes.get()
            assert not apps.serial.get()
            apps.run("install")
            assert not apps.busy and "explicitly" in apps.status.get()
            with tempfile.TemporaryDirectory() as temporary:
                data = Path(temporary) / "vectors.jsonl"
                fixture = Path("fixtures/oem/mcc_292_vectors.jsonl")
                data.write_text(fixture.read_text("utf-8").splitlines()[0] + "\n", encoding="utf-8")
                conformance.dataset.set(str(data))
                conformance.buttons[0].invoke()
                deadline = time.monotonic() + 5
                while conformance.busy and time.monotonic() < deadline:
                    root.update(); time.sleep(.01)
                assert conformance.last_result["matched"]
                assert conformance.last_result["vectors"] == 1
                assert "dataset provenance" in conformance.last_result["evidence"]
        finally:
            app.close()
