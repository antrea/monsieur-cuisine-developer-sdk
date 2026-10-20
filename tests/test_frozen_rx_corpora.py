"""Freeze the Python RX decoders against the RX corpora already in the repository.

The expected fields were produced by the Python decoders themselves when the
corpora were generated, so these checks are regression guards (golden master),
not evidence about the appliance. Before this file only the Kotlin tests read
these corpora, so a change to a Python RX offset or mapping went unnoticed.
"""
import json
from pathlib import Path
import unittest

from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import decode_frame
from monsieur_cuisine_sdk.profiles.mcs import protocol as mcs

ROOT = Path(__file__).resolve().parents[1]
MCC_FIELDS = ('status', 'motor_heater_state', 'motor_on', 'heater_on', 'scale_stable', 'direction',
              'error_detected', 'error_code', 'android_error_code', 'above_target_temperature',
              'bowl_ntc_detected', 'lid_open', 'extended_state', 'target_speed_level', 'target_rpm',
              'actual_rpm', 'target_temperature_level', 'target_temperature', 'actual_temperature', 'weight',
              'firmware_version', 'scale_state_raw', 'scale_state', 'calibration_step', 'unknown_byte_24',
              'actual_speed_level', 'target_speed_level_signed', 'target_temperature_level_signed',
              'unknown_byte_24_signed', 'android_scale_state')


def text(value):
    return str(value).lower() if isinstance(value, bool) else str(int(value) if hasattr(value, 'real') and not isinstance(value, float) else value)


class FrozenRxCorpora(unittest.TestCase):
    def test_mcc_golden_rx_rows(self):
        rows = [line for line in (ROOT / 'android/sdk/src/test/resources/mcc/golden_rx_292.tsv').read_text('utf-8').splitlines()
                if line.strip() and not line.startswith('#')]
        self.assertEqual(len(rows), 256)
        for number, row in enumerate(rows):
            raw, *expected = row.split('\t')
            frame = decode_frame(raw)
            actual = [text(getattr(frame, name)) for name in MCC_FIELDS]
            self.assertEqual(actual, expected, f'row {number}')

    def test_mcs_rx_vectors(self):
        rows = json.loads((ROOT / 'fixtures/mcs/android-rx-vectors.json').read_text('utf-8'))
        self.assertEqual(len(rows), 1000)
        for number, row in enumerate(rows):
            self.assertEqual(mcs.decode(bytes.fromhex(row['hex']))['fields'], row['fields'], f'row {number}')


if __name__ == '__main__':
    unittest.main()
