"""Real native Backup tab operations on small synthetic local sessions."""
from pathlib import Path
import tempfile
import time

from gui_process import NativeGuiTestCase
from test_backup_manager import make_disk, write_session


class BackupDesktop(NativeGuiTestCase):
    def test_real_import_stage_compare_and_protected_export_widgets(self):
        import tkinter as tk
        from unittest.mock import patch
        from monsieur_cuisine_sdk.gui import DesktopApp
        from test_backup_importer import zip_session
        root = tk.Tk(); app = DesktopApp(root); app.running = False
        try:
            panel = app.backup_panel
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                source = base / "source"; write_session(source, make_disk())
                archive = base / "input.zip"; zip_session(source, archive)
                def wait_result():
                    deadline = time.monotonic() + 10
                    while panel.busy and time.monotonic() < deadline:
                        root.update(); time.sleep(.01)
                    self.assertFalse(panel.busy)
                    self.assertIsInstance(panel.last_result, dict, panel.status.get())
                panel.folder.set(str(archive)); panel.destination.set(str(base / "imported"))
                panel.buttons[3].invoke(); wait_result()
                self.assertTrue(panel.last_result["complete"])
                panel.folder.set(str(source)); panel.destination.set(str(base / "staged"))
                panel.buttons[4].invoke(); wait_result()
                self.assertEqual((base / "staged/backup_session/emmc_user_full.bin").read_bytes(), make_disk())
                second = base / "imported/backup_session"
                panel.second.set(str(second))
                panel.buttons[2].invoke(); wait_result()
                self.assertTrue(panel.last_result["same_partition_content"])
                self.assertTrue(panel.last_result["same_full_user_area"])
                # Editing the entry after completion cannot remove export
                # protection from either source captured by the operation.
                panel.folder.set(str(base / "changed-entry")); panel.second.set("")
                forbidden = second / "report.json"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(forbidden)):
                    panel.export()
                self.assertFalse(forbidden.exists())
                self.assertIn("rejected", panel.status.get())
        finally:
            app.close()

    def test_real_panel_verifies_inventories_and_exports_no_private_paths(self):
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        root = tk.Tk(); app = DesktopApp(root); app.running = False
        try:
            panel = app.backup_panel
            with tempfile.TemporaryDirectory() as directory:
                session = Path(directory); write_session(session, make_disk())
                panel.folder.set(str(session))
                for operation in ('verify', 'inventory'):
                    panel.start(operation)
                    deadline = time.monotonic() + 10
                    while panel.busy and time.monotonic() < deadline:
                        root.update(); time.sleep(.01)
                    self.assertFalse(panel.busy)
                    self.assertIsInstance(panel.last_result, dict)
                    self.assertNotIn(str(session), panel.output.get('1.0', 'end'))
                self.assertIn('Backup', app._tab_frames)
        finally:
            app.close()
