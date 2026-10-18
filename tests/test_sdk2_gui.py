"""Real native Backup tab operations on small synthetic local sessions."""
from pathlib import Path
import tempfile
import time

from gui_process import NativeGuiTestCase
from test_backup_manager import make_disk, write_session


class BackupDesktop(NativeGuiTestCase):
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
