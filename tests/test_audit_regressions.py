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
        self.assertEqual(state.raw['remaining'], 110)
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

    def test_idle_set_temperature_heats_at_speed_zero_for_both(self):
        for model in ('mcc', 'mcs'):
            with self.subTest(model=model):
                twin = DigitalTwin(model, record=False)
                twin.set_temperature(60)
                state = twin.get_state()
                self.assertEqual((state.requested_speed, state.target_temperature), (0, 60))
                self.assertTrue(state.heater_on or model == 'mcs')

    def test_invalid_temperature_rejected_before_mutation(self):
        for model in ('mcc', 'mcs'):
            twin = DigitalTwin(model, record=False)
            twin.start_motor(2, 'cw', 60)
            for value in (38, 60.0, True, None):
                with self.subTest(model=model, value=value), self.assertRaises(ValueError):
                    twin.set_temperature(value)
            self.assertEqual(twin.get_state().target_temperature, 60)


if __name__ == '__main__':
    unittest.main()
