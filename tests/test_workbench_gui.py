"""Actual native panels and worker results; no ADB device is contacted here."""
import json
from pathlib import Path
import tempfile
import time

from gui_process import NativeGuiTestCase


class WorkbenchGuiTests(NativeGuiTestCase):
    def test_firmware_and_recovery_panels_execute_actual_file_operations(self):
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        from monsieur_cuisine_sdk.workbench import FirmwarePanel, RecoveryPanel
        from test_backup_manager import make_disk, write_session
        root = tk.Tk(); app = DesktopApp(root); app.running = False
        try:
            firmware = next(p for p in app.toolkit_panel.panels if isinstance(p, FirmwarePanel))
            recovery = next(p for p in app.toolkit_panel.panels if isinstance(p, RecoveryPanel))
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                disk = base / "disk.img"; disk.write_bytes(make_disk())
                source = base / "source"; write_session(source, make_disk())
                def wait_result(panel):
                    deadline = time.monotonic() + 10
                    while panel.busy and time.monotonic() < deadline:
                        root.update(); time.sleep(.01)
                    assert not panel.busy
                    assert not panel.last_result.get("error"), panel.last_result
                    return panel.last_result
                firmware.image.set(str(disk)); firmware.hash_content.set(True)
                firmware.buttons[0].invoke()
                assert wait_result(firmware)["type"] == "gpt-disk"
                assert firmware.last_result["sha256"]
                recovery.session.set(str(source)); recovery.destination.set(str(base / "restored"))
                recovery.buttons[0].invoke()
                assert not wait_result(recovery)["physical_execution_enabled"]
                recovery.buttons[1].invoke()
                assert wait_result(recovery)["complete"]
                assert (base / "restored/emmc_user_full.bin").read_bytes() == make_disk()
        finally:
            app.close()

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
