"""Independent adversarial review of common lifecycle, framing and actual Tk/TCP.

All inputs are original synthetic protocol data; these are software checks only.
"""
from copy import deepcopy
import gc
import json
import queue
import socket
import threading
import time
import unittest
from unittest.mock import patch
import weakref

from monsieur_cuisine_sdk import DigitalTwin, DeviceModel, OwnershipError, RecordingLimitError, replay
from monsieur_cuisine_sdk.profiles.mcs import protocol as mcs

MODELS = ('mcc', 'mcs')


class SharedCoreIndependentReview(unittest.TestCase):
    def test_sensor_batch_and_invalid_start_are_atomic_for_both_models(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                initial = twin.get_state()
                for values in ({'weight': 123, 'firmware': -1}, {'temperature': 90, 'ntc_present': 1},
                               {'error_code': 3, 'unrecognized': True}):
                    with self.assertRaises(ValueError):twin.set_sensors(**values)
                    self.assertEqual(twin.get_state(), initial)
                for args in ((11, 'cw', 60), (3, 'sideways', 60), (3, 'cw', 61)):
                    with self.assertRaises(ValueError):twin.start_motor(*args)
                    self.assertEqual(twin.get_state(), initial)
                self.assertEqual(twin.recording['actions'], [])

    def test_fault_batch_validation_does_not_clear_an_existing_partial_frame(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                tx = twin.profile.encode_start(3, 'cw', 60)
                twin.feed(tx[:7])
                checkpoint = twin._checkpoint()
                count = len(twin.recording['actions'])
                with self.assertRaises(ValueError):twin.set_faults(disconnected=True, delay_seconds=float('nan'))
                self.assertEqual(twin._checkpoint(), checkpoint)
                self.assertEqual(len(twin.recording['actions']), count)

    def test_fractional_clock_conservation_for_both_native_grids(self):
        for model in MODELS:
            with self.subTest(model=model):
                a, b = DigitalTwin(model, record=False), DigitalTwin(model, record=False)
                for twin in (a, b):twin.start_motor(3, 'cw', 60)
                a.advance(.001)
                for _ in range(10):b.advance(.0001)
                self.assertEqual(a.now_ns, 1_000_000)
                self.assertEqual(a.get_state(), b.get_state())

    def test_fractional_mcs_tick_budget_counts_only_completed_native_ticks(self):
        twin = DigitalTwin('mcs', record=False)
        twin._total_ticks = 999999
        twin.advance(1e-9)
        twin.advance(1e-9)
        self.assertEqual(twin._total_ticks, 999999)
        self.assertEqual(twin.profile.native.engine._ticks, 0)
        self.assertEqual(twin.now_ns, 2)

    def test_foreign_complete_commands_cannot_actuate_selected_model(self):
        for selected, foreign in (('mcc', 'mcs'), ('mcs', 'mcc')):
            with self.subTest(selected=selected):
                twin = DigitalTwin(selected)
                raw = DigitalTwin(foreign, record=False).profile.encode_start(3, 'cw', 60)
                for byte in raw:twin.feed(bytes([byte]))
                self.assertEqual(twin.get_state().requested_speed, 0)
                self.assertEqual(twin.command_count, 0)
                self.assertGreater(twin.stream.rejected, 0)

    def test_nested_mcc_command_is_quarantined_in_valid_and_corrupt_mcs_ota(self):
        for selected in MODELS:
            for size in (0, 4097, 5026, 65536):
                if selected == 'mcs' and size == 0:continue
                for corrupt in (False, True):
                    with self.subTest(selected=selected, size=size, corrupt=corrupt):
                        twin = DigitalTwin(selected, record=False)
                        nested = twin.profile.encode_start(3, 'cw', 60)
                        if size:
                            # Generic MCS envelopes can occupy the complete u16
                            # wire range, beyond the selected parser's 4096 cap.
                            payload = b'\x12\x34' + nested
                            outer = bytearray(mcs.pack(payload + b'\0' * (size - 9 - len(payload))))
                        else:
                            outer = bytearray(mcs.encode_ota(2, data=nested))
                        self.assertEqual(mcs.parse_frame(outer).raw, bytes(outer))
                        if corrupt:outer[-1] ^= 1
                        stride = 7 if not size else 257
                        for offset in range(0, len(outer), stride):
                            twin.feed(outer[offset:offset + stride])
                            if size:self.assertLessEqual(twin.buffered_bytes, 3)
                        self.assertEqual(twin.get_state().requested_speed, 0)
                        self.assertEqual(twin.command_count, 0)
                        self.assertEqual(twin.buffered_bytes, 0)
                        self.assertEqual(twin.stream.discard_remaining, 0)
                        twin.feed(nested)
                        self.assertEqual(twin.get_state().requested_speed, 3)
        # Reset and recording checkpoints retain the bounded discard state.
        for selected in MODELS:
            twin = DigitalTwin(selected)
            nested = twin.profile.encode_start(3, 'cw', 60)
            outer = mcs.pack(b'\x12\x34' + nested + b'\0' * 5000)
            twin.feed(outer[:11])
            self.assertEqual(twin.buffered_bytes, 3)
            self.assertEqual(twin.stream.discard_remaining, len(outer) - 11)
            restored = replay(twin.recording)
            self.assertEqual(restored._checkpoint(), twin._checkpoint())
            for current in (twin, restored):
                current.feed(outer[11:] + nested)
                self.assertEqual(current.command_count, 1)
                self.assertEqual(current.get_state().requested_speed, 3)
                current.feed(outer[:11])
                current.disarm()
                self.assertEqual(current.stream.discard_remaining, 0)
                self.assertEqual(current.buffered_bytes, 0)
                current.feed(nested)
                self.assertEqual(current.get_state().requested_speed, 3)
                current.feed(outer[:11])
                current.switch_model('mcs' if selected == 'mcc' else 'mcc')
                self.assertEqual(current.stream.discard_remaining, 0)
                self.assertEqual(current.buffered_bytes, 0)
                self.assertEqual(current.get_state().requested_speed, 0)
                current.feed(current.profile.encode_start(3, 'cw', 60))
                self.assertEqual(current.get_state().requested_speed, 3)

    def test_own_corrupt_frame_does_not_actuate_and_valid_tail_recovers(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                good = twin.profile.encode_start(3, 'cw', 60)
                bad = bytearray(good)
                bad[-2 if model == 'mcc' else -1] ^= 1
                twin.feed(b'noise' + bad)
                self.assertEqual(twin.get_state().requested_speed, 0)
                twin.feed(good)
                self.assertEqual(twin.get_state().requested_speed, 3)

    def test_fault_drop_corrupt_delay_and_replay_match_binary_outputs(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                emitted = []
                twin.subscribe_rx(lambda raw, generation: emitted.append((raw, generation)))
                twin.set_faults(drop_next=1)
                self.assertEqual(twin.start_motor(3, 'cw', 60), [])
                self.assertEqual(twin.get_state().requested_speed, 3)
                twin.set_faults(corrupt_next=1, delay_seconds=.2)
                self.assertEqual(twin.sample(), [])
                twin.advance(.1)
                self.assertEqual(emitted, [])
                twin.advance(.1)
                self.assertEqual(len(emitted), 1)
                raw, generation = emitted[0]
                self.assertEqual(generation, twin.generation)
                with self.assertRaises(ValueError):twin.profile.feed_frame(raw)
                result = replay(json.loads(json.dumps(twin.recording)))
                self.assertEqual(result.get_state(), twin.get_state())

    def test_due_time_order_and_disarm_discard_old_pending_replies(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                seen = []
                twin.subscribe_rx(lambda raw, generation: seen.append(raw))
                twin.set_faults(delay_seconds=2)
                twin.sample()
                twin.advance(.1)
                twin.set_faults(delay_seconds=.1)
                twin.sample()
                twin.advance(.1)
                self.assertEqual(len(seen), 1)
                twin.disarm()
                twin.advance(3)
                self.assertEqual(len(seen), 1)
                self.assertEqual(twin._pending_bytes, 0)

    def test_disconnect_fault_and_disarm_remove_old_input_fragments(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                raw = twin.profile.encode_start(3, 'cw', 60)
                twin.feed(raw[:8])
                twin.set_faults(disconnected=True)
                twin.set_faults(disconnected=False)
                twin.feed(raw[8:])
                self.assertEqual(twin.get_state().requested_speed, 0)
                twin.disarm()
                twin.feed(raw)
                self.assertEqual(twin.get_state().requested_speed, 3)

    def test_owner_identity_and_mutation_thread_are_enforced(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                owner = object()
                twin.claim(owner)
                with self.assertRaises(OwnershipError):twin.start_motor(3)
                twin.start_motor(3, owner=owner)
                twin.set_sensors(error_code=3)
                self.assertEqual(twin.get_state().error_code, 3)
                failures = []
                def wrong_thread():
                    try:twin.advance(.1)
                    except RuntimeError:failures.append(True)
                worker = threading.Thread(target=wrong_thread)
                worker.start();worker.join(2)
                self.assertEqual(failures, [True])
                twin.disarm();twin.release(owner)
                self.assertEqual(twin.owner, 'local')

    def test_invalid_model_switch_keeps_current_session_and_targets(self):
        for model, other in (('mcc', 'mcs'), ('mcs', 'mcc')):
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                twin.start_motor(3)
                before = twin.get_state()
                hooks = []
                twin.before_switch(lambda: hooks.append(True))
                with self.assertRaises(ValueError):twin.switch_model(other, parameters={'unknown': 1})
                self.assertEqual(twin.get_state(), before)
                self.assertEqual(hooks, [])

    def test_model_switch_invalidates_delays_fragments_and_generation(self):
        for model, other in (('mcc', 'mcs'), ('mcs', 'mcc')):
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                seen = []
                twin.subscribe_rx(lambda raw, generation: seen.append(generation))
                twin.set_faults(delay_seconds=2)
                twin.start_motor(3)
                twin.feed(twin.profile.encode_start(4, 'cw', 60)[:8])
                twin.switch_model(other)
                twin.advance(3)
                self.assertEqual(seen, [])
                self.assertEqual(twin.generation, 1)
                self.assertEqual(twin.buffered_bytes, 0)
                self.assertEqual(twin.get_state().requested_speed, 0)
                twin.sample()
                self.assertEqual(seen, [1])
                self.assertEqual(replay(twin.recording).get_state(), twin.get_state())

    def test_recording_capacity_requests_stop_and_remains_replayable(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model, max_actions=4)
                twin.start_motor(3)
                twin.advance(.2)
                twin.sample()
                with self.assertRaises(RecordingLimitError):twin.start_motor(4)
                self.assertEqual(twin.get_state().requested_speed, 0)
                self.assertGreater(twin.get_state().actual_speed, 0)
                self.assertEqual(len(twin.recording['actions']), 4)
                self.assertEqual(replay(twin.recording).get_state(), twin.get_state())

    def test_stop_at_capacity_and_capacity_model_switch_remain_available(self):
        for model, other in (('mcc', 'mcs'), ('mcs', 'mcc')):
            with self.subTest(model=model):
                twin = DigitalTwin(model, max_actions=2)
                twin.start_motor(3)
                self.assertEqual(twin.stop_motor(), [])
                self.assertTrue(twin.recording_full)
                self.assertEqual(twin.get_state().requested_speed, 0)
                old_trace = deepcopy(twin.recording)
                twin.switch_model(other)
                self.assertEqual(twin.model.value, other)
                self.assertEqual(twin.generation, 1)
                self.assertEqual(twin.get_state().requested_speed, 0)
                self.assertEqual(twin.last_recording, old_trace)
                self.assertEqual(replay(old_trace).get_state().requested_speed, 0)

    def test_observer_reentrant_switch_cannot_relabel_old_frames_or_break_replay(self):
        twin = DigitalTwin('mcs')
        seen = []
        def switch_during_notification(raw, generation):
            try:twin.switch_model('mcc')
            except (RuntimeError, ValueError):pass  # explicit rejection is a valid policy
        twin.subscribe_rx(switch_during_notification)
        twin.subscribe_rx(lambda raw, generation: seen.append((len(raw), generation)))
        twin.sample()
        self.assertEqual(seen, [(48, 0)])
        self.assertEqual(replay(twin.recording).get_state(), twin.get_state())

    def test_observer_failure_does_not_erase_an_applied_command_from_recording(self):
        twin = DigitalTwin('mcs')
        def failing_observer(raw, generation):raise RuntimeError('observer failed')
        twin.subscribe_rx(failing_observer)
        try:twin.start_motor(3)
        except RuntimeError:pass
        self.assertEqual(twin.get_state().requested_speed, 3)
        self.assertEqual(replay(twin.recording).get_state(), twin.get_state())

    def test_delayed_output_quota_is_bounded_and_stops_target(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model, max_pending_bytes=269)
                twin.set_faults(delay_seconds=100)
                twin.start_motor(3)
                for _ in range(12):
                    twin.sample()
                    if twin.overflow:break
                self.assertTrue(twin.overflow)
                self.assertEqual(twin._pending_bytes, 0)
                self.assertEqual(twin.get_state().requested_speed, 0)

    def test_invalid_input_size_cannot_mutate_parser_or_recording(self):
        for model in MODELS:
            twin = DigitalTwin(model)
            before = twin._checkpoint()
            with self.assertRaises(ValueError):twin.feed(b'\0' * 65537)
            self.assertEqual(twin._checkpoint(), before)
            self.assertEqual(twin.recording['actions'], [])

    def test_recording_preflight_rejects_late_invalid_sensor_before_work(self):
        twin = DigitalTwin('mcs')
        twin.advance(.1)
        twin.set_sensors(weight=10)
        recording = deepcopy(twin.recording)
        recording['actions'][-1]['input'] = {'firmware': -1}
        with patch.object(DigitalTwin, 'advance', side_effect=AssertionError('physics ran before preflight')):
            with self.assertRaises(ValueError):replay(recording)

    def test_replay_corruption_and_cancellation_do_not_modify_original(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model)
                twin.start_motor(3)
                twin.advance(.2)
                before = twin.get_state()
                changed = deepcopy(twin.recording)
                changed['actions'][0]['rx_hex'] = []
                with self.assertRaises(ValueError):replay(changed)
                with self.assertRaisesRegex(ValueError, 'cancel'):replay(twin.recording, cancelled=lambda: True)
                self.assertEqual(twin.get_state(), before)

    def test_mcs_wire_timer_expires_without_restart(self):
        twin = DigitalTwin('mcs')
        twin.start_motor(3, duration=1)
        twin.advance(1.2)
        self.assertEqual(twin.get_state().requested_speed, 0)
        twin.advance(1)
        self.assertEqual(twin.get_state().actual_speed, 0)


class SharedTcpIndependentReview(unittest.TestCase):
    def make_connection(self, model, **config):
        from monsieur_cuisine_sdk.android_connection import AndroidConnection, ConnectionConfig
        twin = DigitalTwin(model)
        bridge = AndroidConnection(twin, ConnectionConfig(port=0, **config)).start()
        self.addCleanup(bridge.close)
        client = socket.create_connection(bridge.address, timeout=1)
        client.settimeout(.2)
        self.addCleanup(client.close)
        self.pump(bridge)
        return twin, bridge, client

    @staticmethod
    def pump(bridge, count=5):
        for _ in range(count):bridge.poll();time.sleep(.001)

    def test_extra_controller_stop_reconnect_and_switch_close(self):
        for model, other in (('mcc', 'mcs'), ('mcs', 'mcc')):
            with self.subTest(model=model):
                twin, bridge, client = self.make_connection(model)
                client.sendall(twin.profile.encode_start(3, 'cw', 60))
                self.pump(bridge)
                self.assertTrue(client.recv(4096))
                self.assertEqual(twin.get_state().requested_speed, 3)
                with self.assertRaises(OwnershipError):twin.start_motor(4)
                with socket.create_connection(bridge.address, timeout=1) as extra:
                    extra.settimeout(.2)
                    self.pump(bridge)
                    self.assertEqual(extra.recv(1), b'')
                client.close()
                with socket.create_connection(bridge.address, timeout=1) as replacement:
                    replacement.settimeout(.2)
                    self.pump(bridge)
                    self.assertEqual(twin.get_state().requested_speed, 0)
                    twin.switch_model(other)
                    self.assertEqual(replacement.recv(1), b'')
                self.assertIsNone(bridge.listener)
                self.assertEqual(twin.owner, 'local')

    def test_fragment_timeout_discards_previous_session_and_releases_owner(self):
        from monsieur_cuisine_sdk.android_connection import AndroidConnection, ConnectionConfig
        for model in MODELS:
            with self.subTest(model=model):
                now = [0.0]
                twin = DigitalTwin(model)
                bridge = AndroidConnection(twin, ConnectionConfig(port=0, fragment_timeout=.1), clock=lambda: now[0]).start()
                try:
                    with socket.create_connection(bridge.address, timeout=1) as client:
                        client.settimeout(.2)
                        self.pump(bridge)
                        client.sendall(twin.profile.encode_start(3, 'cw', 60)[:8])
                        self.pump(bridge)
                        self.assertGreater(twin.buffered_bytes, 0)
                        now[0] = .2
                        self.pump(bridge)
                        self.assertEqual(client.recv(1), b'')
                        self.assertEqual(twin.owner, 'local')
                        self.assertEqual(twin.buffered_bytes, 0)
                        self.assertEqual(twin.get_state().requested_speed, 0)
                        self.assertEqual(twin.stream.discard_remaining, 0)
                    # A huge declared frame holds only its header but must still
                    # trigger the same fragment timeout and release quarantine.
                    with socket.create_connection(bridge.address, timeout=1) as client:
                        client.settimeout(.2)
                        self.pump(bridge)
                        nested = twin.profile.encode_start(3, 'cw', 60)
                        outer = mcs.pack(b'\x12\x34' + nested + b'\0' * 5000)
                        client.sendall(outer[:11])
                        self.pump(bridge)
                        self.assertEqual(twin.buffered_bytes, 3)
                        self.assertGreater(twin.stream.discard_remaining, 4096)
                        now[0] = .4
                        self.pump(bridge)
                        self.assertEqual(client.recv(1), b'')
                        self.assertEqual(twin.owner, 'local')
                        self.assertEqual(twin.buffered_bytes, 0)
                        self.assertEqual(twin.stream.discard_remaining, 0)
                        self.assertEqual(twin.get_state().requested_speed, 0)
                finally:bridge.close()

    def test_tcp_response_output_quota_disconnects_and_disarms(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin, bridge, client = self.make_connection(model, max_output=269)
                raw = twin.profile.encode_start(3, 'cw', 60)
                client.sendall(raw * 30)
                self.pump(bridge)
                self.assertEqual(twin.owner, 'local')
                self.assertEqual(twin.get_state().requested_speed, 0)
                self.assertEqual(bridge.status()['clients'], 0)
                self.assertLessEqual(bridge.status()['pending_bytes'], 269)

    def test_recording_capacity_cannot_prevent_listener_or_client_cleanup(self):
        from monsieur_cuisine_sdk.android_connection import AndroidConnection, ConnectionConfig
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model, max_actions=4)
                bridge = AndroidConnection(twin, ConnectionConfig(port=0)).start()
                try:
                    with socket.create_connection(bridge.address, timeout=1) as client:
                        client.settimeout(.2)
                        self.pump(bridge)  # accept records one disarm action
                        client.sendall(twin.profile.encode_start(3, 'cw', 60))
                        self.pump(bridge)
                        self.assertTrue(client.recv(4096))
                        twin.advance(.2)
                        client.sendall(twin.profile.encode_start(4, 'cw', 60))
                        self.pump(bridge)
                        self.assertEqual(client.recv(1), b'')
                        self.assertTrue(twin.recording_full)
                        self.assertEqual(twin.owner, 'local')
                        self.assertEqual(twin.get_state().requested_speed, 0)
                    bridge.close()
                    self.assertIsNone(bridge.listener)
                    self.assertEqual(replay(twin.recording).get_state(), twin.get_state())
                finally:bridge.close()


from gui_process import NativeGuiTestCase


class SharedGuiIndependentReview(NativeGuiTestCase):
    def setUp(self):
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        self.root = tk.Tk()
        self.app = DesktopApp(self.root, DigitalTwin('mcc', record=False))
        self.app.running = False
        self.root.update()

    def tearDown(self):
        if self.app is not None:self.app.close()
        self.app = self.root = None
        gc.collect()

    def test_closed_gui_without_worker_is_collectible_on_owner_thread(self):
        reference = weakref.ref(self.app)
        self.app.close()
        self.app = self.root = None
        gc.collect()
        self.assertIsNone(reference())

    def test_cancelled_worker_does_not_retain_closed_tk_application(self):
        started, finish = threading.Event(), threading.Event()
        def work(cancelled):
            started.set()
            finish.wait(3)  # a bounded operation currently between cancellation checks
            return {'done': True}
        previous_threads = set(threading.enumerate())
        self.app._run_job(work)
        self.assertTrue(started.wait(1))
        workers = [t for t in threading.enumerate() if t not in previous_threads]
        reference = weakref.ref(self.app)
        retained = None
        try:
            self.app.close()
            self.app = self.root = None
            gc.collect()
            retained_by_worker = reference() is not None
            # Keep any surviving Tk object on this thread until the worker exits.
            # This prevents a failing regression from finalizing Tcl on the worker.
            retained = reference()
        finally:
            finish.set()
            for worker in workers:worker.join(2)
            retained = None
            gc.collect()
        self.assertFalse(retained_by_worker, 'background worker retains the closed Tk application')

    def test_actual_widgets_show_explicit_model_units_and_fresh_switch_state(self):
        from monsieur_cuisine_sdk.gui import MODELS
        self.assertEqual(len(self.app.notebook.tabs()), 11)
        self.app.twin.start_motor(3)
        self.app.twin.advance(.5)
        self.app.refresh()
        self.assertIn('RPM', self.app.values['speed'].get())
        self.app.model_var.set(next(label for label, model in MODELS.items() if model == DeviceModel.MCS))
        self.app.change_model()
        self.assertEqual(self.app.twin.get_state().requested_speed, 0)
        self.assertIn('raw level', self.app.values['speed'].get())
        self.assertNotIn('RPM', self.app.values['speed'].get())

    def test_stale_worker_result_cannot_replace_new_session_view(self):
        app = self.app
        old_token, old_generation = app._job, app.twin.generation
        app.new_session()
        app.running = False
        app._results.put_nowait((old_token, old_generation, {'stale': 'must not show'}))
        app.poll()
        self.assertNotIn('must not show', app.scenario_output.get('1.0', 'end'))

    def test_gui_emergency_stop_disconnects_remote_and_prevents_restart(self):
        app = self.app
        connection = app.enable_android(port=0)
        with socket.create_connection(connection.address, timeout=1) as client:
            client.settimeout(.2)
            SharedTcpIndependentReview.pump(connection)
            client.sendall(app.twin.profile.encode_start(3, 'cw', 60))
            SharedTcpIndependentReview.pump(connection)
            self.assertTrue(client.recv(4096))
            app.twin.advance(.5)
            self.assertGreater(app.twin.get_state().actual_speed, 0)
            app.stop_motor()
            self.assertEqual(client.recv(1), b'')
        self.assertEqual(app.twin.owner, 'local')
        self.assertEqual(app.twin.get_state().requested_speed, 0)
        app.twin.advance(3)
        self.assertEqual(app.twin.get_state().actual_speed, 0)


if __name__ == '__main__':unittest.main()
