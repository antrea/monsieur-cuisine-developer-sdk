"""Regressions for independent-audit findings in the common API and profiles.

Synthetic software checks only; they do not describe appliance behavior.
"""
import unittest

from monsieur_cuisine_sdk import DigitalTwin, RecordingLimitError, replay
from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, Operation, encode_tx
from monsieur_cuisine_sdk.profiles.mcs import protocol as mcs


def checksum_fixed(raw):
    raw = bytearray(raw)
    raw[13] = sum(raw[:13]) & 0xFF
    return bytes(raw)


class RefusedCommandsAreNotCountedAsAccepted(unittest.TestCase):
    def test_mcc_refusal_is_visible_and_not_counted(self):
        twin = DigitalTwin('mcc', record=False)
        stop_with_speed = bytearray(encode_tx(Operation.STOP)); stop_with_speed[5] = 4
        unknown_operation = bytearray(encode_tx(Operation.STANDARD, speed=2)); unknown_operation[3] = 2
        for raw in (checksum_fixed(stop_with_speed), checksum_fixed(unknown_operation)):
            twin.feed(raw)
        self.assertEqual(twin.command_count, 0)
        refused = [e for e in twin.timeline if e.get('event') == 'rejected_command']
        self.assertEqual(len(refused), 2)
        self.assertIn('rejected without actuation', refused[0]['reason'])
        self.assertEqual(twin.get_state().requested_speed, 0)
        twin.start_motor(2, 'cw')
        self.assertEqual(twin.command_count, 1)

    def test_mcc_tare_and_valid_commands_still_accepted(self):
        twin = DigitalTwin('mcc', record=False)
        twin.start_motor(3, 'ccw', 60)
        twin.set_sensors(weight=250)
        twin.tare()
        state = twin.get_state()
        self.assertEqual((state.weight, state.requested_speed, state.target_temperature), (0, 3, 60))
        self.assertEqual(twin.command_count, 2)


class SetTemperaturePreservesTheRunningCommand(unittest.TestCase):
    def test_mcs_countdown_and_raw_level_are_preserved(self):
        twin = DigitalTwin('mcs', record=False)
        twin.start_motor(2, 'ccw', 60, 120)
        twin.advance(10)
        twin.set_temperature(80)
        state = twin.get_state()
        self.assertEqual(state.target_temperature, 80)
        self.assertEqual(state.requested_speed, 2)
        self.assertEqual(state.requested_direction, 'ccw')
        self.assertAlmostEqual(state.raw['remaining'], 110, places=6)  # deadline kept, not rewritten
        self.assertTrue(state.raw['timer_active'])
        twin.advance(111)
        self.assertEqual(twin.get_state().requested_speed, 0)

    def test_mcs_odd_raw_level_and_function_survive(self):
        twin = DigitalTwin('mcs', record=False)
        twin.feed(mcs.encode_operation(speed_level=5, function=5, temperature_level=0))  # knead, raw 5
        twin.set_temperature(45)
        state = twin.get_state()
        self.assertEqual((state.target_speed, state.raw['function'], state.target_temperature), (5, 5, 45))

    def test_mcc_program_operation_is_preserved(self):
        twin = DigitalTwin('mcc', record=False)
        twin.feed(encode_tx(Operation.KNEAD, speed=3, direction=Direction.CLOCKWISE))
        twin.set_temperature(60)
        controller = twin.get_state().raw['controller']
        self.assertEqual((controller['extended_state'], controller['requested_speed_level']), (5, 3))
        self.assertEqual(twin.get_state().target_temperature, 60)

    def test_idle_set_temperature_uses_each_profiles_host_policy(self):
        for model in ('mcc', 'mcs'):
            with self.subTest(model=model):
                twin = DigitalTwin(model, record=False)
                twin.set_temperature(60)
                state = twin.get_state()
                self.assertEqual((state.requested_speed, state.target_temperature), (1 if model == 'mcc' else 0, 60))
                self.assertTrue(state.heater_on or model == 'mcs')

    def test_invalid_temperature_rejected_before_mutation(self):
        for model in ('mcc', 'mcs'):
            twin = DigitalTwin(model, record=False)
            twin.start_motor(2, 'cw', 60)
            for value in (38, 60.0, True, None):
                with self.subTest(model=model, value=value), self.assertRaises(ValueError):
                    twin.set_temperature(value)
            self.assertEqual(twin.get_state().target_temperature, 60)


class RedTeamTwinRegressions(unittest.TestCase):
    def test_repeated_set_temperature_cannot_extend_the_mcs_countdown(self):
        # R1: re-encoding ceil(remaining) every call used to restart the deadline.
        twin = DigitalTwin('mcs', record=False)
        twin.start_motor(2, 'cw', 60, 10)
        elapsed = 0.0
        while twin.get_state().requested_speed and elapsed < 30:
            twin.set_temperature(80 if int(elapsed * 2) % 2 else 70)
            twin.advance(0.5); elapsed += 0.5
        self.assertAlmostEqual(elapsed, 10, delta=0.6)
        self.assertEqual(twin.get_state().requested_speed, 0)

    def test_new_explicit_countdown_still_replaces_the_running_one(self):
        twin = DigitalTwin('mcs', record=False)
        twin.start_motor(2, 'cw', 60, 30)
        twin.advance(5)
        twin.start_motor(2, 'cw', 60, 60)
        self.assertEqual(twin.get_state().raw['remaining'], 60)

    def test_truncated_recording_starts_fresh_on_model_switch(self):
        # R9: the old model's truncated trace must not stay attached to the new model.
        twin = DigitalTwin('mcc', max_actions=6, on_recording_full='continue')
        for _ in range(10):
            twin.advance(.05)
        self.assertTrue(twin.recording['truncated'])
        twin.switch_model('mcs')
        self.assertEqual(twin.recording['model'], 'mcs')
        self.assertNotIn('truncated', twin.recording)
        self.assertTrue(twin.record_enabled)

    def test_new_session_keeps_record_false(self):
        twin = DigitalTwin('mcc', record=False)
        twin.new_session('mcs')
        self.assertFalse(twin.record_enabled)

    def test_more_malformed_recordings_raise_value_error(self):
        import json, os, tempfile
        good = DigitalTwin('mcc').recording
        with self.assertRaises(ValueError):
            replay({**good, 'parameters': []})
        path = os.path.join(tempfile.mkdtemp(), 'deep.json')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('{"schema": "monsieur-cuisine-recording-v1", "x": ' + '[' * 100000 + ']' * 100000 + '}')
        with self.assertRaises(ValueError):
            replay(path)


class MethodologyRegressions(unittest.TestCase):
    def test_cli_json_depth_is_bounded_before_the_platform_decoder(self):
        from unittest.mock import patch
        from monsieur_cuisine_sdk import cli
        with patch.object(cli.json, 'loads', side_effect=AssertionError('decoder reached')):
            for opening, closing in (('[', ']'), ('{"x":', '}')):
                with self.subTest(container=opening), self.assertRaises(RecursionError):
                    cli._loads_bounded(opening * (cli.MAX_JSON_DEPTH + 1) + '0' + closing * (cli.MAX_JSON_DEPTH + 1))

    def test_cli_json_depth_ignores_string_brackets_and_escaped_quotes(self):
        import json
        from monsieur_cuisine_sdk import cli
        value = {'text': '[' * 2000 + '\\"' + '}' * 2000, 'nested': [{'ok': True}]}
        self.assertEqual(cli._loads_bounded(json.dumps(value)), value)
        with self.assertRaises(json.JSONDecodeError):
            cli._loads_bounded('{"broken": }')

    def test_stress_oracle_still_fails_under_python_optimize(self):
        # RT-M: bare asserts vanished under -O and a broken twin reported PASS.
        import os, subprocess, sys
        from pathlib import Path
        code = ("import dataclasses, json\n"
                "from monsieur_cuisine_sdk import scenarios\n"
                "real = scenarios.DigitalTwin.get_state\n"
                "scenarios.DigitalTwin.get_state = lambda self: dataclasses.replace(real(self), actual_speed=-1)\n"
                "print(json.dumps(scenarios.run_stress('mcc', count=3)['PASS']))\n")
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        done = subprocess.run([sys.executable, '-O', '-c', code], env=environment, capture_output=True,
                              text=True, timeout=120)
        self.assertEqual(done.stdout.strip(), 'false', done.stderr)

    def test_cli_reports_deeply_nested_json_as_an_error(self):
        import json, os, subprocess, sys, tempfile
        from pathlib import Path
        path = os.path.join(tempfile.mkdtemp(), 'deep.json')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('[' * 100000 + ']' * 100000)
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        done = subprocess.run([sys.executable, '-m', 'monsieur_cuisine_sdk.cli', '--model', 'mcc', 'replay', path],
                              env=environment, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 2, done.stderr[-500:])
        self.assertEqual(json.loads(done.stderr)['error'], 'RecursionError')


class InteractiveRecordingPolicy(unittest.TestCase):
    def test_default_policy_still_stops_at_capacity(self):
        twin = DigitalTwin('mcc', max_actions=4)
        twin.start_motor(2)
        with self.assertRaises(RecordingLimitError):
            for _ in range(10):
                twin.advance(.05)
        self.assertTrue(twin.recording_full)
        self.assertEqual(twin.get_state().requested_speed, 0)

    def test_continue_policy_truncates_recording_and_keeps_simulating(self):
        for model in ('mcc', 'mcs'):
            with self.subTest(model=model):
                twin = DigitalTwin(model, max_actions=6, on_recording_full='continue')
                twin.start_motor(2, 'cw')
                for _ in range(40):
                    twin.advance(.05)
                    twin.sample()
                state = twin.get_state()
                self.assertFalse(twin.recording_full)
                self.assertTrue(twin.recording['truncated'])
                self.assertEqual(state.requested_speed, 2)
                self.assertGreater(state.actual_speed, 0)
                self.assertLessEqual(len(twin.recording['actions']), 6)
                replay(twin.recording)  # the recorded prefix still replays exactly
                twin.stop_motor()
                twin.new_session()
                self.assertEqual(twin.on_recording_full, 'continue')
                self.assertNotIn('truncated', twin.recording)

    def test_policy_is_validated(self):
        with self.assertRaises(ValueError):
            DigitalTwin('mcc', on_recording_full='ignore')


class EntryPointsAndReplayErrors(unittest.TestCase):
    def test_legacy_cli_modules_run_instead_of_exiting_silently(self):
        import json, os, subprocess, sys
        from pathlib import Path
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        for module, model in (('mcc_tools.cli', 'MCC'), ('mcs_tools.cli', 'MCS')):
            with self.subTest(module=module):
                done = subprocess.run([sys.executable, '-m', module, 'capabilities'], env=environment,
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(json.loads(done.stdout)['model'], model)

    def test_malformed_recordings_raise_value_error(self):
        twin = DigitalTwin('mcc')
        twin.start_motor(2)
        twin.sample()
        good = twin.recording
        missing_seed = {key: value for key, value in good.items() if key != 'seed'}
        bad_arguments = {**good, 'actions': [dict(good['actions'][0], operation='sample', input={'unexpected': 1})]}
        for recording in (missing_seed, bad_arguments, {**good, 'max_actions': None}):
            with self.assertRaises(ValueError):
                replay(recording)


class FastReconnect(unittest.TestCase):
    def test_reconnect_right_after_last_frames_is_accepted(self):
        # Red-team A6: the old peer's final frames were read first, its EOF only on
        # the next poll, so the new client was rejected after a completed handshake.
        import socket, time
        from monsieur_cuisine_sdk.android_connection import AndroidConnection, ConnectionConfig
        for model in ('mcc', 'mcs'):
            with self.subTest(model=model):
                twin = DigitalTwin(model, record=False)
                connection = AndroidConnection(twin, ConnectionConfig(port=0)).start()
                try:
                    first = socket.create_connection(connection.address, timeout=1)
                    connection.poll()
                    self.assertEqual(twin.owner, 'remote')
                    first.sendall(twin.profile.encode_stop())
                    first.close()
                    second = socket.create_connection(connection.address, timeout=1)
                    time.sleep(.1)
                    connection.poll()
                    self.assertEqual(connection.rejected_clients, 0)
                    self.assertEqual(connection.status()['status'], 'Connected')
                    second.sendall(twin.profile.encode_start(2, 'cw', 0))
                    time.sleep(.1)
                    connection.poll()
                    self.assertEqual(twin.get_state().requested_speed, 2)
                    second.close()
                finally:
                    connection.close()


if __name__ == '__main__':
    unittest.main()
