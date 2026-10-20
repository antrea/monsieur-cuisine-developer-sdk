"""Real-widget regressions for desktop usability findings of the independent audit.

Each case runs in its own process (gui_process). Synthetic data only.
"""
import gc
import unittest

from gui_process import NativeGuiTestCase
from monsieur_cuisine_sdk import DigitalTwin


class DesktopUsabilityRegressions(NativeGuiTestCase):
    def setUp(self):
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        self.root = tk.Tk()
        self.app = DesktopApp(self.root)
        self.app.running = False
        self.root.update()

    def tearDown(self):
        if self.app is not None:self.app.close()
        self.app = self.root = None
        gc.collect()

    def test_default_desktop_twin_truncates_recording_instead_of_stopping(self):
        self.assertEqual(self.app.twin.on_recording_full, 'continue')
        self.app.twin.new_session()
        self.assertEqual(self.app.twin.on_recording_full, 'continue')

    def test_window_fits_the_screen_and_status_line_stays_mapped(self):
        self.root.update()
        self.assertLessEqual(self.root.winfo_height(), self.root.winfo_screenheight())
        self.root.geometry(f"{self.root.minsize()[0]}x{self.root.minsize()[1]}")
        self.root.update()
        labels = [w for w in self.app.notebook.master.winfo_children()
                  if w.winfo_class() == 'TLabel' and str(w.cget('textvariable')) == str(self.app.message)]
        self.assertEqual(len(labels), 1)
        label = labels[0]
        self.assertTrue(label.winfo_ismapped())
        self.assertLessEqual(label.winfo_rooty() + label.winfo_height(),
                             self.root.winfo_rooty() + self.root.winfo_height() + 1)

    def test_protocol_monitor_keeps_scroll_and_selection_and_follows_tail(self):
        twin = self.app.twin
        self.app.notebook.select(self.app._tab_frames['Protocol Monitor'])
        self.root.update()
        twin.start_motor(2, 'cw')
        for _ in range(200):
            twin.advance(.05); twin.sample()
        self.app.refresh(); self.root.update()
        console = self.app.console
        self.assertGreaterEqual(console.yview()[1], .999, 'live view should follow the newest frame')
        console.yview_moveto(0.2); self.root.update()
        position = console.yview()[0]
        top_line = console.get('@0,0 linestart', '@0,0 lineend')
        for _ in range(60):  # the 400-frame ring is full: old lines are dropped
            twin.advance(.05); twin.sample()
            self.app.refresh(); self.root.update()
        self.assertAlmostEqual(console.yview()[0], position, delta=.02)
        self.assertEqual(console.get('@0,0 linestart', '@0,0 lineend'), top_line,
                         'text under a reader scrolled away from the tail must not move')
        console.yview_moveto(1.0); self.root.update()
        twin.advance(.05); twin.sample(); self.app.refresh(); self.root.update()
        self.assertGreaterEqual(console.yview()[1], .999, 'returning to the bottom resumes following')
        console.tag_add('sel', '1.0', '1.10')
        twin.advance(.05); twin.sample()
        self.app.refresh()
        self.assertTrue(console.tag_ranges('sel'), 'refresh must not clear the user selection')

    def test_partial_frame_and_disconnected_link_are_not_reported_as_applied(self):
        stop = self.app.twin.profile.encode_stop()
        self.app.action(lambda: self.app.twin.feed(stop[:7]), sends=True)
        self.assertIn('Partial frame', self.app.message.get())
        self.app.action(lambda: self.app.twin.feed(stop[7:]), sends=True)
        self.assertIn('Applied', self.app.message.get())
        self.app.twin.set_faults(disconnected=True)
        self.app.action(self.app.stop_motor, sends=True)
        self.assertIn('disconnected', self.app.message.get())
        self.app.sensor_vars['lid_open'].set(True)
        self.app.action(self.app.inject_sensors)
        self.assertIn('Applied', self.app.message.get())  # sensors work with the link down

    def test_sensor_entries_start_from_the_model_and_tare_allows_reinjection(self):
        twin = self.app.twin
        self.assertEqual(self.app.sensor_vars['temperature'].get(), str(round(twin.get_state().temperature)))
        self.app.sensor_vars['temperature'].set('25')
        self.app.action(self.app.inject_sensors)
        self.assertEqual(twin.get_state().temperature, 25)
        self.app.sensor_vars['weight'].set('500')
        self.app.action(self.app.inject_sensors)
        self.app.action(self.app.tare, sends=True)
        self.assertEqual(twin.get_state().weight, 0)
        self.app.sensor_vars['weight'].set('500')
        self.app.action(self.app.inject_sensors)
        self.assertEqual(twin.get_state().weight, 500)

    def test_sensor_injection_only_sends_edited_fields(self):
        twin = self.app.twin
        twin.start_motor(1, 'cw', 60)
        twin.advance(20)
        before = twin.get_state()
        self.app.sensor_vars['lid_open'].set(True)
        self.app.action(self.app.inject_sensors)
        after = twin.get_state()
        self.assertTrue(after.lid_open)
        self.assertEqual(after.temperature, before.temperature)
        self.assertEqual(after.weight, before.weight)
        self.app.action(self.app.inject_sensors)
        self.assertIn('No sensor field', self.app.message.get())

    def test_quarantined_or_refused_input_is_reported(self):
        stop = self.app.twin.profile.encode_stop()
        self.app.hex_var.set(stop.hex() + 'aa')
        self.app.action(lambda: self.app.twin.feed(bytes.fromhex(self.app.hex_var.get())))
        self.assertIn('Applied', self.app.message.get())  # the valid STOP ran; the trailing byte waits
        bad = bytearray(stop); bad[5] = 4; bad[13] = sum(bad[:13]) & 0xFF
        self.app.action(lambda: self.app.twin.feed(bytes(bad)))
        self.assertIn('refused', self.app.message.get())
        self.app.action(lambda: self.app.twin.feed(b'\x00\x01\x02'))
        self.assertIn('Input not executed', self.app.message.get())


if __name__ == '__main__':
    unittest.main()
