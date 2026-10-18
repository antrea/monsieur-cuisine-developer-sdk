"""OEM host policy and explicitly synthetic calibration regression checks."""
import unittest

from monsieur_cuisine_sdk import DigitalTwin, replay
from monsieur_cuisine_sdk.profiles.mcc.oem_policy import HostPolicy
from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import (Direction, Operation, decode_frame,
                                                            encode_calibration, encode_tx)


class HostCommandPolicy(unittest.TestCase):
    def test_high_level_caps_and_minimum_differ_from_raw_feed(self):
        twin = DigitalTwin('mcc')
        for speed, direction, heat, expected in ((10, 'cw', 60, 3), (9, 'ccw', 0, 3), (0, 'cw', 60, 1)):
            twin.start_motor(speed, direction, heat)
            self.assertEqual(twin.get_state().requested_speed, expected)
        twin.feed(encode_tx(Operation.STANDARD, speed=10, temperature_level=5))
        self.assertEqual(twin.get_state().requested_speed, 10)
        self.assertEqual(replay(twin.recording).get_state(), twin.get_state())

    def test_strict_policy_rejects_before_recording_or_state_mutation(self):
        twin = DigitalTwin('mcc', parameters={'host_policy': 'strict'})
        checkpoint = twin._checkpoint()
        for speed, direction, heat in ((10, 'cw', 60), (4, 'ccw', 0), (0, 'cw', 60)):
            with self.assertRaises(ValueError):
                twin.start_motor(speed, direction, heat)
            self.assertEqual(twin._checkpoint(), checkpoint)
            self.assertEqual(twin.recording['actions'], [])

    def test_temperature_reapplies_policy_without_changing_program(self):
        twin = DigitalTwin('mcc')
        twin.feed(encode_tx(Operation.KNEAD, speed=4, direction=Direction.COUNTER_CLOCKWISE))
        twin.set_temperature(60)
        self.assertEqual(twin.get_state().requested_speed, 3)
        self.assertEqual(twin.get_state().raw['controller']['extended_state'], 5)
        idle = DigitalTwin('mcc'); idle.set_temperature(60)
        self.assertEqual(idle.get_state().requested_speed, 1)

    def test_zero_temperature_from_idle_never_starts_motor_or_turbo_during_run(self):
        twin = DigitalTwin('mcc')
        twin.set_temperature(0)
        self.assertEqual(twin.get_state().requested_speed, 0)
        self.assertFalse(twin.get_state().motor_on)
        twin.start_motor(2)
        with self.assertRaises(ValueError): twin.start_turbo()

    def test_recipe_conversion_is_explicit_and_profile_specific(self):
        twin = DigitalTwin('mcc')
        twin.set_recipe_temperature(98)
        self.assertEqual(twin.get_state().target_temperature, 100)
        twin.set_recipe_temperature(25)
        self.assertEqual(twin.get_state().target_temperature, 0)
        with self.assertRaises(ValueError): DigitalTwin('mcs').set_recipe_temperature(98)

    def test_default_direction_and_canonical_turbo(self):
        twin = DigitalTwin('mcc'); twin.start_motor()
        self.assertEqual(twin.get_state().requested_direction, 'cw')
        twin.stop_motor(); twin.start_turbo()
        # Inspect the recording's original TX rather than response ordering.
        tx = decode_frame(bytes.fromhex(twin.recording['actions'][-1]['input']['hex']))
        self.assertEqual((tx.operation, tx.speed_level, tx.direction, tx.temperature_level),
                         (Operation.TURBO, 10, Direction.CLOCKWISE, 0))
        twin.stop_motor(); twin.set_sensors(temperature=60)
        with self.assertRaises(ValueError): twin.start_turbo()
        twin.set_sensors(temperature=20, lid_open=True)
        with self.assertRaises(ValueError): twin.start_motor()
        twin.set_sensors(lid_open=False, error_code=5)
        with self.assertRaises(ValueError): twin.start_motor()

    def test_knead_reverse_cap_and_strict_turbo(self):
        decision = HostPolicy().start(Operation.KNEAD, 10, Direction.COUNTER_CLOCKWISE, 0)
        self.assertEqual(decision.speed, 4)
        strict = HostPolicy('strict').start(Operation.TURBO, 2, Direction.CLOCKWISE, 0,
                                          measured_temperature=20, lid_open=False)
        self.assertFalse(strict.allowed)

    def test_error_names_are_compatible_and_ui_descriptions_are_separate(self):
        twin = DigitalTwin('mcc')
        for code, old, wording in ((5, 'motor', 'overheated'), (6, 'water_missing', 'liquid'),
                                   (7, 'motor_overheat', 'overloaded')):
            twin.set_sensors(error_code=code)
            raw = twin.sample()[0]
            decoded = decode_frame(raw).to_dict()
            self.assertEqual(decoded['error_name'], old)
            self.assertIn(wording, decoded['error_description'])


class CalibrationAndLatchedTraffic(unittest.TestCase):
    def test_calibration_progress_is_virtual_time_based_and_replayable(self):
        twin = DigitalTwin('mcc')
        self.assertEqual(len(twin.feed(encode_calibration('enter'))[0]), 27)
        self.assertEqual(twin.get_state().raw['controller']['calibration_step'], 0)
        for step in range(1, 5):
            for _ in range(10):
                response = twin.feed(encode_calibration('start'))
                self.assertEqual(len(response[0]), 27)
                twin.advance(.1)
            self.assertEqual(twin.get_state().raw['controller']['calibration_step'], step)
        self.assertEqual(replay(twin.recording).get_state(), twin.get_state())
        twin.feed(encode_calibration('exit'))
        self.assertEqual(twin.get_state().raw['controller']['scale_state_raw'], 2)

    def test_repeated_latched_commands_do_not_restart_motion(self):
        twin = DigitalTwin('mcc')
        raw = encode_tx(Operation.STANDARD, speed=3)
        for _ in range(1000):
            self.assertEqual(len(twin.feed(raw)[0]), 27)
            twin.advance(.1)
        self.assertEqual(twin.command_count, 1000)
        self.assertEqual(twin.get_state().actual_speed, twin.get_state().target_speed)
        twin.stop_motor(); twin.advance(3)
        self.assertEqual(twin.get_state().actual_speed, 0)


class OptionalHostTiming(unittest.TestCase):
    def make_host(self):
        from monsieur_cuisine_sdk.profiles.mcc.cooking import CookingHost
        return CookingHost(DigitalTwin('mcc', record=False))

    def test_latch_collapse_and_countdown_finish(self):
        host = self.make_host(); host.start(3, seconds=1)
        self.assertEqual(host.twin.command_count, 0)
        host.stop(); host.start(2, seconds=1); host.advance(.1)
        self.assertEqual(host.twin.command_count, 1)
        self.assertEqual(host.twin.get_state().requested_speed, 2)
        host.advance(1)
        self.assertEqual(host.state, 'FINISHED')
        self.assertEqual(host.twin.get_state().requested_speed, 0)

    def test_lid_pause_no_auto_resume_and_30_second_stop(self):
        host = self.make_host(); host.start(3); host.advance(.2)
        host.twin.set_sensors(lid_open=True); host.advance(.1)
        self.assertEqual(host.state, 'PAUSE')
        host.twin.set_sensors(lid_open=False); host.advance(1)
        self.assertEqual(host.state, 'PAUSE')
        host.advance(30); self.assertEqual(host.state, 'STOP')

    def test_turbo_first_tick_release_and_hot_abort(self):
        host = self.make_host(); host.turbo_hold(True); host.advance(.099)
        self.assertEqual(host.twin.command_count, 0)
        host.advance(.001)
        self.assertEqual(host.twin.get_state().requested_speed, 10)
        host.advance(8); self.assertTrue(host.turbo_warning)
        host.turbo_hold(False); host.advance(.1)
        self.assertEqual(host.twin.get_state().requested_speed, 0)
        host.turbo_hold(True); host.advance(.1)
        host.twin.set_sensors(temperature=60); host.advance(.1)
        self.assertEqual(host.twin.get_state().requested_speed, 0)

    def test_countup_limit_and_idle_sleep_are_host_not_firmware(self):
        host = self.make_host(); host.start(7); host.advance(900)
        self.assertEqual(host.state, 'FINISHED')
        self.assertEqual(host.twin.get_state().requested_speed, 0)
        idle = self.make_host(); idle.advance(449.9)
        self.assertEqual(idle.state, 'STOP')
        idle.advance(.1); self.assertEqual(idle.state, 'SLEEP')
        idle.wake(); idle.advance(.1); self.assertEqual(idle.state, 'STOP')


if __name__ == '__main__': unittest.main()
