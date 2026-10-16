"""Regressions for independently reproduced baseline MCS defects."""
import threading
import unittest
from unittest.mock import patch

from monsieur_cuisine_sdk.profiles.mcs import MCSProfile
from monsieur_cuisine_sdk.profiles.mcs import protocol as p
from monsieur_cuisine_sdk.profiles.mcs.simulation import DigitalTwin, ModelParameters, replay
from monsieur_cuisine_sdk.profiles.mcs.simulation.limits import MAX_PENDING, SimulationCancelled
from monsieur_cuisine_sdk.profiles.mcs.simulation.scenarios import run_scenario


class McsProfileRegressions(unittest.TestCase):
    def test_tare_response_has_current_overload_state(self):
        twin = DigitalTwin()
        twin.sensors(mass=6000)
        self.assertEqual(twin.state.scale_state, 4)
        rx = twin.transact(p.encode_operation(opcode=0x0803, scale_mode=1))
        result = p.decode_telemetry(rx)
        self.assertEqual((result.weight, result.scale_state), (0, 0))
        self.assertFalse(result.state & 4)

    def test_unsafe_parameters_rejected_at_construction(self):
        for values in ({'noise_grams': 1e10}, {'heating_rate': 1e308}, {'cooling_coefficient': 1e6},
                       {'timeline_limit': 100001}):
            with self.subTest(values=values), self.assertRaises(ValueError):ModelParameters(**values)

    def test_response_encoding_failure_rolls_back_command_and_sequence(self):
        twin = DigitalTwin(record=True)
        twin.state.weight = 1 << 32  # test externally corrupted native state
        before = twin.state.snapshot()
        with self.assertRaises(p.ProtocolError):twin.transact(p.encode_manual(speed=4))
        self.assertEqual(twin.state.snapshot(), before)
        self.assertEqual(twin.board.sequence.value, 0)
        self.assertEqual(twin.recording['actions'], [])

    def test_saturation_is_explicit_and_wire_safe(self):
        twin = DigitalTwin(parameters=ModelParameters(tick_seconds=1, heating_rate=1000, overtemperature=1000))
        twin.sensors(temperature=249)
        twin.transact(p.encode_manual(temperature=130))
        twin.state.target_temperature = 255
        twin.advance(1)
        self.assertEqual(twin.state.temperature, 1000)
        self.assertTrue(twin.state.temperature_saturated)
        self.assertEqual(p.decode_telemetry(twin.board.telemetry()).actual_temperature, 1000)

    def test_pending_reply_limit_rejects_before_actuation(self):
        twin = DigitalTwin()
        twin.faults(delay_seconds=1000)
        for _ in range(MAX_PENDING):twin.transact(p.encode_operation(opcode=0x0801))
        before = twin.state.snapshot()
        sequence = twin.board.sequence.value
        with self.assertRaisesRegex(ValueError, 'queue is full'):twin.transact(p.encode_manual(speed=4))
        self.assertEqual(twin.state.snapshot(), before)
        self.assertEqual(twin.board.sequence.value, sequence)
        self.assertEqual(len(twin.board.pending), MAX_PENDING)
        twin.disarm()
        self.assertEqual(twin.board.pending, [])

    def test_unknown_subtype_remains_opaque(self):
        raw = p.pack(p.parse_frame(p.encode_manual()).payload, subtype=9)
        decoded = p.decode(raw, direction='tx')
        self.assertEqual(decoded['fields'], {})
        self.assertEqual(decoded['semantics'], 'UNKNOWN')
        self.assertEqual(decoded['payload_hex'], p.parse_frame(raw).payload.hex())
        with self.assertRaises(ValueError):p.decode_command(raw)

    def test_parser_rejects_nonfinite_and_noninteger_options(self):
        for args in ({'timeout': float('nan')}, {'timeout': float('inf')}, {'timeout': True}, {'max_frame': 4096.5}):
            with self.subTest(args=args), self.assertRaises(ValueError):p.StreamParser(**args)

    def test_parser_time_validation_precedes_buffer_mutation(self):
        parser = p.StreamParser()
        prefix = p.encode_manual()[:12]
        parser.feed(prefix, now=0)
        for value in (float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):parser.expire(now=value)
            with self.assertRaises(ValueError):parser.feed(b'\0', now=value)
            self.assertEqual(bytes(parser.buffer), prefix)

    def test_invalid_countdown_is_not_compatible_typed_profile(self):
        payload = bytearray(p.parse_frame(p.encode_manual()).payload)
        payload[18] = 60
        raw = p.pack(payload)
        self.assertEqual(p.detect_profile(raw, direction='tx')['compatible_layouts'], [])
        with self.assertRaises(ValueError):p.decode_command(raw)

    def test_excessive_scenario_ticks_rejected_before_advance(self):
        with patch.object(DigitalTwin, 'advance', side_effect=AssertionError('work ran')):
            with self.assertRaisesRegex(ValueError, 'work budget'):
                run_scenario({'format_version': 1, 'duration': 1e8, 'sample_period': 1e8})

    def test_scenario_validates_late_operations_before_any_advance(self):
        with patch.object(DigitalTwin, 'advance', side_effect=AssertionError('work ran')):
            with self.assertRaisesRegex(ValueError, 'unsupported scenario action'):
                run_scenario({'format_version': 1, 'duration': 10,
                              'events': [{'at': 10, 'action': 'unknown'}]})

    def test_scenario_rounded_sample_count_is_bounded(self):
        with self.assertRaisesRegex(ValueError, 'excessive samples'):
            run_scenario({'format_version': 1, 'duration': .00014, 'sample_period': 1.49e-9})

    def test_replay_preflight_rejects_work_and_unknown_actions_before_execution(self):
        recording = DigitalTwin(record=True).recording
        recording['actions'] = [{'kind': 'advance', 'arguments': {'seconds': 1}, 'result': {}},
                                {'kind': 'advance', 'arguments': {'seconds': 1e8}, 'result': {}}]
        with patch.object(DigitalTwin, 'advance', side_effect=AssertionError('work ran')):
            with self.assertRaisesRegex(ValueError, 'work budget'):replay(recording)
        recording['actions'][-1] = {'kind': 'arbitrary', 'arguments': {}, 'result': None}
        with patch.object(DigitalTwin, 'advance', side_effect=AssertionError('work ran')):
            with self.assertRaisesRegex(ValueError, 'unknown recording action'):replay(recording)

    def test_limits_reject_before_clock_change(self):
        twin = DigitalTwin()
        for value in (1e308, float('nan'), 1e8):
            with self.assertRaises(ValueError):twin.advance(value)
            self.assertEqual(twin.engine.clock.nanoseconds, 0)
        profile = MCSProfile()
        with self.assertRaises(ValueError):profile.advance_ns(10**1000)
        self.assertEqual(profile.native.engine.clock.nanoseconds, 0)

    def test_cooperative_cancel_leaves_clock_at_completed_tick(self):
        twin = DigitalTwin()
        checks = []
        def cancel():
            checks.append(True)
            return len(checks) >= 3
        with self.assertRaises(SimulationCancelled):twin.advance(100, cancel=cancel)
        self.assertEqual(twin.engine.clock.nanoseconds, 256 * 20_000_000)
        self.assertEqual(twin.state.time, 5.12)
        self.assertLess(len(twin.engine.timeline), 1000)

    def test_cancelled_scenario_can_finish_without_touching_widgets(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(SimulationCancelled):
            run_scenario({'format_version': 1, 'duration': 10}, cancel=cancelled.is_set)

    def test_replay_json_roundtrip_retains_faults_disarm_and_timeline(self):
        import json
        twin = DigitalTwin(seed=23, parameters=ModelParameters(noise_grams=.1, timeline_limit=5), record=True)
        twin.sensors(mass=123)
        twin.faults(delay_seconds=.2)
        twin.transact(p.encode_manual(speed=3))
        twin.advance(1)
        twin.receive_ready()
        twin.disarm()
        twin.advance(1)
        twin.interrupt()
        recording = json.loads(json.dumps(twin.recording))
        other = replay(recording)
        self.assertEqual(twin.state.snapshot(), other.state.snapshot())
        self.assertEqual(list(twin.engine.timeline), list(other.engine.timeline))
        self.assertEqual(len(other.engine.timeline), 5)


if __name__ == '__main__':unittest.main()
