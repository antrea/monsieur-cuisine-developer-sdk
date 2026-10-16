"""Final acceptance checks across the public facade and the actual desktop."""
from pathlib import Path
import os
import select
import socket
import subprocess
import sys
import time
import unittest

from gui_process import NativeGuiTestCase

from monsieur_cuisine_sdk import DeviceModel, DigitalTwin, replay
from monsieur_cuisine_sdk.scenarios import SCENARIOS, run_scenario


class OfflineAcceptance(unittest.TestCase):
    def test_library_constructs_and_runs_without_tk_or_socket_creation(self):
        code = '''
import socket, sys
from unittest.mock import patch
with patch.object(socket, "socket", side_effect=AssertionError("unexpected socket")):
    from monsieur_cuisine_sdk import DigitalTwin
    for model in ("mcc", "mcs"):
        twin=DigitalTwin(model)
        twin.start_motor(2, "ccw", 60)
        twin.advance(.5)
        assert twin.get_state().actual_speed > 0
        twin.stop_motor()
        twin.advance(5)
        assert twin.get_state().actual_speed == 0
    assert "tkinter" not in sys.modules
    assert "monsieur_cuisine_sdk.android_connection" not in sys.modules
print("OFFLINE PASS")
'''
        result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                text=True, timeout=20, env=os.environ.copy())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OFFLINE PASS', result.stdout)

    def test_all_shared_scenarios_and_replay_for_both_profiles(self):
        for model in DeviceModel:
            for name in SCENARIOS:
                with self.subTest(model=model.value, scenario=name):
                    result = run_scenario(model, name, seed=292)
                    self.assertTrue(result['PASS'], result['checks'])
                    self.assertEqual(replay(result['recording']).get_state().to_dict(),
                                     result['final_state'])


class DesktopSwitchAcceptance(NativeGuiTestCase):
    def test_both_connected_roundtrip_switch_sequences(self):
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp, MODELS
        root = tk.Tk()
        app = DesktopApp(root)
        app.running = False
        clients = []
        try:
            for initial in DeviceModel:
                with self.subTest(initial=initial.value):
                    app.model_var.set(next(label for label, model in MODELS.items()
                                           if model == initial))
                    app.change_model()
                    opposite = DeviceModel.MCS if initial == DeviceModel.MCC else DeviceModel.MCC
                    for selected in (opposite, initial):
                        connection = app.enable_android(port=0)
                        client = socket.create_connection(connection.address, timeout=1)
                        clients.append(client);client.settimeout(1)
                        def wait_for(predicate):
                            deadline = time.monotonic() + 2
                            while not predicate():
                                connection.poll()
                                if time.monotonic() >= deadline:
                                    self.fail('loopback operation did not complete before deadline')
                                time.sleep(.001)
                        wait_for(lambda: connection.client is not None)
                        old = app.twin.profile
                        old_start = old.encode_start(3, 'cw', 60)
                        client.sendall(old_start)
                        wait_for(lambda: bool(select.select([client], [], [], 0)[0]))
                        self.assertTrue(client.recv(4096))
                        app.twin.advance(.2)
                        app.twin.set_faults(delay_seconds=5)
                        app.twin.sample()
                        client.sendall(old_start[:7])
                        wait_for(lambda: app.twin.buffered_bytes == 7)
                        old_generation = app.twin.generation
                        app.model_var.set(next(label for label, model in MODELS.items()
                                               if model == selected))
                        app.change_model()
                        self.assertEqual(client.recv(1), b'')
                        self.assertIsNone(connection.listener)
                        self.assertGreater(app.twin.generation, old_generation)
                        self.assertEqual(app.twin.model, selected)
                        self.assertEqual(app.twin.owner, 'local')
                        self.assertEqual(app.twin.buffered_bytes, 0)
                        self.assertEqual(app.twin.get_state().requested_speed, 0)
                        self.assertEqual(old.state()['requested_speed'], 0)
                        app.twin.advance(6)
                        self.assertEqual(app.twin.get_state().actual_speed, 0)
                        self.assertEqual(app.twin.receive_ready(), [])
                        self.assertEqual((app.twin.get_state().actual_rpm is None),
                                         selected == DeviceModel.MCS)
                    self.assertEqual(app.twin.model, initial)
        finally:
            for client in clients:client.close()
            app.close()


if __name__ == '__main__':
    unittest.main()
