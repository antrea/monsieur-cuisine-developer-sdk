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


if __name__ == '__main__':
    unittest.main()
