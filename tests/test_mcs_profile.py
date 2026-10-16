"""MCS historical wire vectors and common profile behavior; no hardware claims."""
import hashlib
import importlib
import json
import random
import unittest

from monsieur_cuisine_sdk.profiles.mcs import MCSProfile
from monsieur_cuisine_sdk.profiles.mcs import protocol as p
from monsieur_cuisine_sdk.profiles.mcs import simulation


class McsProfileTests(unittest.TestCase):
    def test_historical_900_encoder_digest(self):
        digest = hashlib.sha256()
        for i in range(300):
            digest.update(p.encode_manual(speed=i % 11, temperature=p.TEMPERATURES[i % 21],
                seconds=(i * 19) % 5941, reverse=bool(i % 2), sequence=i % 256))
        for i in range(300):
            digest.update(p.encode_operation(speed_level=i % 21, temperature_level=i % 21,
                constant_temperature=i % 256, function=(0, 1, 3, 4, 5, 198)[i % 6],
                seconds=i * 79, scale_mode=i % 2, sequence=i % 256, legacy=bool(i % 2),
                turbo_lock=i % 11, button=i % 7))
        for i in range(300):
            sub = (1, 2, 3, 4, 6)[i % 5]
            n = 16 if sub == 1 else i % 257 if sub == 2 else 0
            data = bytes((i + j) % 256 for j in range(n))
            digest.update(p.encode_ota(sub, data=data, packet_sequence=i * 17, sequence=i % 256))
        self.assertEqual(digest.hexdigest(), 'd3db51b05914af1cbb30c5f68856eaa00cba7f2e85a258940206948505129fe9')

    def test_aliases_are_canonical_module_objects(self):
        self.assertIs(importlib.import_module('mcs_protocol'), p)
        self.assertIs(importlib.import_module('mcs_digital_twin'), simulation)
        for name in ('_baseline', 'types', 'schema', 'stream'):
            self.assertIs(importlib.import_module(f'mcs_protocol.{name}'),
                          importlib.import_module(f'{p.__name__}.{name}'))
        for name in ('model', 'board', 'api', 'scenarios'):
            self.assertIs(importlib.import_module(f'mcs_digital_twin.{name}'),
                          importlib.import_module(f'{simulation.__name__}.{name}'))

    def test_wire_shapes_and_no_rpm_claim(self):
        profile = MCSProfile()
        tx = profile.encode_start(3, 'ccw', 60, 90)
        self.assertEqual(len(tx), 39)
        command = p.decode_command(tx)
        self.assertEqual((command.speed_level, command.direction_raw, command.seconds), (6, 1, 90))
        self.assertEqual(len(profile.feed_frame(tx)[0]), 48)
        profile.advance_ns(1_000_000_000)
        state = profile.state()
        self.assertEqual((state['requested_speed'], state['target_speed'], state['actual_speed']), (3, 6, 6))
        self.assertEqual(state['actual_direction'], 'ccw')
        self.assertEqual(state['speed_unit'], 'raw_motor_level')
        self.assertIsNone(state['actual_rpm'])
        self.assertFalse(profile.capabilities['physical_rpm_verified'])
        json.dumps(profile.parameters, allow_nan=False)
        json.dumps(profile.capabilities, allow_nan=False)
        json.dumps(state, allow_nan=False)

    def test_stop_retains_coast_but_removes_targets(self):
        profile = MCSProfile()
        profile.feed_frame(profile.encode_start(8, 'cw', 60, 30))
        profile.advance_ns(2_000_000_000)
        before = profile.state()['actual_speed']
        profile.stop()
        self.assertEqual(profile.state()['target_speed'], 0)
        self.assertEqual(profile.state()['actual_speed'], before)
        profile.advance_ns(2_000_000_000)
        self.assertEqual(profile.state()['actual_speed'], 0)

    def test_query_does_not_apply_operational_fields(self):
        profile = MCSProfile()
        profile.feed_frame(profile.encode_start(3, 'cw', 60))
        profile.feed_frame(profile.encode_query())
        self.assertEqual(profile.state()['target_speed'], 6)

    def test_independent_response_sequence_skips_66(self):
        profile = MCSProfile()
        profile.native.board.sequence.value = 0x65
        tx = p.encode_manual(sequence=99)
        rx = profile.feed_frame(tx)[0]
        self.assertEqual(p.parse_frame(rx).sequence, 0x67)
        self.assertEqual(p.parse_frame(profile.sample()[0]).sequence, 0x68)
        self.assertNotEqual(p.parse_frame(rx).sequence, p.parse_frame(tx).sequence)

    def test_wrong_profile_and_malformed_inputs_are_atomic(self):
        profile = MCSProfile()
        initial = profile.state()
        wrong = bytes.fromhex('550fa101a90307000000000100baaa')
        for raw in (wrong, profile.encode_start(3, 'cw', 60)[:-1], p.pack(b'\x12\x34'),
                    p.pack(p.parse_frame(p.encode_manual()).payload, subtype=9)):
            with self.subTest(raw=raw.hex()), self.assertRaises(ValueError):
                profile.feed_frame(raw)
            self.assertEqual(profile.state(), initial)

    def test_sensors_all_validated_before_mutation(self):
        profile = MCSProfile()
        initial = profile.state()
        for values in ({'weight': 123, 'firmware': 65536}, {'weight': 123, 'ntc_present': 1},
                       {'error_code': 7, 'temperature': float('nan')}, {'temperature': 90, 'unknown': 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                profile.set_sensors(**values)
            self.assertEqual(profile.state(), initial)
        profile.set_sensors(weight=123, firmware=65535, error_code=3, lid_open=True, ntc_present=False)
        state = profile.state()
        self.assertEqual((state['weight'], state['firmware'], state['error_code']), (123, 65535, 3))
        self.assertTrue(state['lid_open'])
        self.assertFalse(state['ntc_present'])
        self.assertEqual(p.decode_telemetry(profile.sample()[0]).firmware_version, 65535)

    def test_normalized_weight_after_tare(self):
        profile = MCSProfile()
        profile.set_sensors(weight=123)
        profile.feed_frame(profile.encode_tare())
        profile.set_sensors(weight=40)
        self.assertEqual(profile.state()['weight'], 40)

    def test_grid_partition_invariance(self):
        a = MCSProfile(seed=23, parameters={'noise_grams': .1})
        b = MCSProfile(seed=23, parameters={'noise_grams': .1})
        for profile in (a, b):
            profile.feed_frame(profile.encode_start(3, 'cw', 60, 30))
        a.advance_ns(10_000_000_000)
        for _ in range(1000):b.advance_ns(10_000_000)
        self.assertEqual(a.state(), b.state())

    def test_signed_telemetry_and_raw_preservation(self):
        rnd = random.Random(20261016)
        for _ in range(100):
            t = p.Telemetry(speed_level=rnd.randrange(-128, 128), weight=rnd.randrange(-(1 << 31), 1 << 31),
                actual_temperature=rnd.randrange(-32768, 32768), returned_temperature=-32768,
                direction_raw=255, temperature_level=-128, temperature_unit=-1, turbo_key=-1,
                firmware_version=65535, weight_format=0x12, error=255, return_code=255,
                seconds=255 * 3600 + 3599, light=255, button=255)
            raw = p.encode_telemetry(t)
            decoded = p.decode_telemetry(raw)
            self.assertEqual(decoded.frame.raw, raw)
            for name in t.__dataclass_fields__:
                if name != 'frame':self.assertEqual(getattr(decoded, name), getattr(t, name))

    def test_ota_shapes_are_separate_packet_sequence(self):
        profile = MCSProfile()
        for sub, tx_size, rx_size in ((1, 27, 12), (2, 269, 13), (3, 11, 28), (4, 11, 12), (6, 11, 14)):
            tx = p.encode_ota(sub, data=b'x' * 16 if sub == 1 else b'', packet_sequence=0x1234, sequence=99)
            self.assertEqual(len(tx), tx_size)
            rx = profile.feed_frame(tx)[0]
            self.assertEqual(len(rx), rx_size)
            if sub == 2:self.assertEqual(p.decode(rx)['fields']['packet_sequence'], 0x1234)

    def test_invalid_start_does_not_consume_sequence_or_mutate(self):
        profile = MCSProfile()
        before = profile.state()
        for args in ((True, 'cw', 60, 0), (3, 'sideways', 60, 0), (3, 'cw', 61, 0), (3, 'cw', 60, 5941)):
            with self.assertRaises(ValueError):profile.encode_start(*args)
        self.assertEqual(profile.state(), before)
        self.assertEqual(p.parse_frame(profile.encode_start(3, 'cw', 60)).sequence, 1)


if __name__ == '__main__':unittest.main()
