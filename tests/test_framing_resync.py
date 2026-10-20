"""Regression: one stray or missing byte must not black out later commands.

0xAA is both the MCS header and the MCC terminator. Before the fix, a single
noise byte made the MCC stream read the next "55 0F" as an MCS length of 21776
and quarantine it forever (every later STOP ignored); in MCS mode a stray 0xAA
before a frame opened a 43521-byte quarantine. Synthetic data only.
"""
import random
import unittest

from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.framing import SelectedStream
from monsieur_cuisine_sdk.profiles.mcs import protocol as mcs

MODELS = ('mcc', 'mcs')


def frames_for(model, count):
    profile = DigitalTwin(model, record=False).profile
    start, stop = profile.encode_start(3, 'cw', 60), profile.encode_stop()
    return [start] + [stop] * (count - 1)


def recovered(model, data):
    stream = SelectedStream(model)
    return [frame for i in range(0, len(data), 15) for frame in stream.feed(data[i:i + 15])]


class FramingResynchronization(unittest.TestCase):
    def test_single_stray_byte_of_any_value_loses_no_later_frame(self):
        for model in MODELS:
            frames = frames_for(model, 40)
            clean = b''.join(frames)
            for value in range(256):
                with self.subTest(model=model, value=value):
                    got = recovered(model, bytes([value]) + clean)
                    self.assertEqual(got[-39:], frames[-39:])

    def test_single_missing_byte_loses_at_most_the_damaged_neighbours(self):
        # MCC: at most the two frames touched by the fault are lost.
        frames = frames_for('mcc', 300)
        clean = b''.join(frames)
        for position in range(len(frames[0]) + len(frames[1])):
            with self.subTest(model='mcc', position=position):
                got = recovered('mcc', clean[:position] + clean[position + 1:])
                self.assertGreaterEqual(len(got), 298)
                self.assertEqual(got[-290:], frames[-290:])

    def test_mcs_length_field_damage_is_bounded_by_the_declared_envelope(self):
        # MCS deliberately discards a complete declared envelope (nested-command
        # protection), so a damaged length can cost up to 64 KiB, never more.
        frames = frames_for('mcs', 1700)  # 66,300 bytes > 65,536
        clean = b''.join(frames)
        for position in (0, 1, 2, 3, 7, 20, 38, 39, 40, 41):
            with self.subTest(position=position):
                got = recovered('mcs', clean[:position] + clean[position + 1:])
                self.assertEqual(got[-200:], frames[-200:])

    def test_stop_after_noise_byte_stops_the_virtual_motor(self):
        for model in MODELS:
            with self.subTest(model=model):
                twin = DigitalTwin(model, record=False)
                twin.start_motor(3, 'cw')
                twin.advance(2)
                twin.feed(b'\xaa')
                twin.stop_motor()
                twin.advance(5)
                self.assertEqual(twin.get_state().requested_speed, 0)
                self.assertEqual(twin.get_state().actual_speed, 0)
                self.assertEqual(twin.stream.discard_remaining, 0)

    def test_random_single_byte_insertions_keep_the_tail(self):
        rng = random.Random(292)
        for model, count in (('mcc', 200), ('mcs', 1700)):
            frames = frames_for(model, count)
            clean = b''.join(frames)
            for _ in range(40 if model == 'mcs' else 150):
                position, value = rng.randrange(60), rng.randrange(256)
                with self.subTest(model=model, position=position, value=value):
                    got = recovered(model, clean[:position] + bytes([value]) + clean[position:])
                    self.assertEqual(got[-150:], frames[-150:])

    def test_nested_commands_stay_isolated_for_lengths_containing_header_bytes(self):
        # Red-team regression: envelopes up to max_frame whose length field holds
        # 0x55/0xAA (86, 171, 342, 597, 4011 bytes) must still be one unit, valid or
        # damaged, in both the foreign (MCC) and own (MCS) case.
        for selected in MODELS:
            nested = DigitalTwin(selected, record=False).profile.encode_start(3, 'cw', 60)
            for size in (86, 171, 342, 597, 4011):
                payload = b'\x12\x34' + nested
                outer = bytearray(mcs.pack(payload + b'\0' * (size - 9 - len(payload))))
                for damaged in (False, True):
                    raw = bytearray(outer)
                    if damaged:raw[-1] ^= 1
                    with self.subTest(selected=selected, size=size, damaged=damaged):
                        twin = DigitalTwin(selected, record=False)
                        twin.feed(bytes(raw))
                        self.assertEqual(twin.get_state().requested_speed, 0)
                        self.assertEqual(twin.command_count, 0)

    def test_damaged_type_byte_or_inserted_aa_cost_one_frame(self):
        # Red-team regression: early type rejection used to expose a fake 0xAA
        # header inside the damaged frame (TURBO A1 -> AA lost 3,380 frames).
        profile = DigitalTwin('mcc', record=False).profile
        from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, Operation, encode_tx
        turbo = bytearray(encode_tx(Operation.TURBO, speed=10, direction=Direction.CLOCKWISE)); turbo[2] = 0xAA
        stop = profile.encode_stop()
        inserted = bytearray(stop); inserted.insert(2, 0xAA)
        for damaged in (bytes(turbo), bytes(inserted)):
            with self.subTest(damaged=damaged.hex()):
                got = recovered('mcc', damaged + stop * 50)
                self.assertGreaterEqual(len(got), 49)

    def test_foreign_envelope_isolation_is_preserved(self):
        # The documented quarantine still fences real foreign envelopes.
        twin = DigitalTwin('mcc', record=False)
        nested = twin.profile.encode_start(3, 'cw', 60)
        for size in (64, 300, 4097, 5026, 65536):
            payload = b'\x12\x34' + nested
            outer = mcs.pack(payload + b'\0' * max(0, size - 9 - len(payload)))
            for offset in range(0, len(outer), 257):
                twin.feed(outer[offset:offset + 257])
            self.assertEqual(twin.get_state().requested_speed, 0, size)
        twin.feed(nested)
        self.assertEqual(twin.get_state().requested_speed, 3)


if __name__ == '__main__':
    unittest.main()
