"""MCC compatibility, shared adapter, and independently found regressions."""
from __future__ import annotations

import importlib
import json
import socket
import subprocess
import sys
import time
import unittest

from monsieur_cuisine_sdk.profiles.mcc import MCCProfile
from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, Operation, decode_frame, encode_tx
from monsieur_cuisine_sdk.profiles.mcc.simulation.recording import RecordingSession, replay_recording
from monsieur_cuisine_sdk.profiles.mcc.simulation.server import PowerBoardTCPServer
from monsieur_cuisine_sdk.profiles.mcc.tools.analyzer import analyze_recording


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("local TCP worker did not reach its expected state")
        time.sleep(0.005)


class MCCProfileTests(unittest.TestCase):
    def test_import_and_construction_are_headless_and_inert(self):
        result = subprocess.run([sys.executable, "-B", "-c",
            "import sys; from monsieur_cuisine_sdk.profiles.mcc import MCCProfile; p=MCCProfile(); "
            "assert 'tkinter' not in sys.modules; assert 'socket' not in sys.modules; "
            "assert p.state()['actual_rpm']==0"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_compatibility_imports_are_same_module_objects(self):
        for old, new in (("mcc_protocol.codec", "protocol.codec"),
                         ("mcc_protocol.stream", "protocol.stream"),
                         ("mcc_protocol.program", "protocol.program"),
                         ("mcc_powerboard_simulator.model", "simulation.model"),
                         ("mcc_powerboard_simulator.recording", "simulation.recording"),
                         ("mcc_tools.analyzer", "tools.analyzer")):
            self.assertIs(importlib.import_module(old),
                          importlib.import_module("monsieur_cuisine_sdk.profiles.mcc." + new))

    def test_protocol_bytes_units_and_temperature_mapping(self):
        profile = MCCProfile(parameters={"acceleration_rpm_s": 1000})
        raw = profile.encode_start(2, "ccw", 60)
        self.assertEqual(raw, encode_tx(Operation.STANDARD, speed=2,
            direction=Direction.COUNTER_CLOCKWISE, temperature_level=5))
        profile.feed_frame(raw)
        profile.advance_ns(100_000_000)
        state = profile.state()
        self.assertEqual((state["requested_speed"], state["target_speed"], state["actual_speed"], state["speed_unit"]), (2, 700, 100, "rpm"))
        self.assertEqual((state["requested_direction"], state["actual_direction"]), ("ccw", "ccw"))
        self.assertEqual(state["target_temperature"], 60)
        self.assertNotIn("log", state["raw"])
        json.dumps(profile.parameters, allow_nan=False)
        json.dumps(profile.capabilities, allow_nan=False)
        self.assertIsNone(profile.encode_query())

    def test_invalid_fields_and_wrong_protocol_never_actuate(self):
        profile = MCCProfile()
        before = profile.state()
        for args in ((11, "cw", 0), (1, "invalid", 0), (1, "cw", 38), (True, "cw", 0), (1, "cw", 60, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                profile.encode_start(*args)
        with self.assertRaises(ValueError):
            profile.feed_frame(b"\x66\x11\x04\x00\x00")
        self.assertEqual(profile.state(), before)

    def test_submillisecond_clock_partitioning(self):
        one, split = MCCProfile(), MCCProfile()
        for profile in (one, split):
            profile.feed_frame(profile.encode_start(2, "cw", 0))
        one.advance_ns(1_000_000)
        for _ in range(10):
            split.advance_ns(100_000)
        self.assertEqual(one.state(), split.state())
        self.assertEqual(split.state()["raw"]["now_ms"], 1)

    def test_sensor_batch_is_atomic_and_normalized(self):
        profile = MCCProfile()
        profile.set_sensors(weight=-10, temperature=42, lid_open=True,
                            ntc_present=False, error_code=5, firmware=123)
        state = profile.state()
        self.assertEqual((state["weight"], state["temperature"], state["lid_open"], state["ntc_present"], state["error_code"], state["firmware"]), (-10, 42, True, False, 5, 123))
        for values in ({"weight": 100, "temperature": -1}, {"weight": 100, "lid_open": 1},
                       {"weight": 100, "unknown": 0}, {"error_code": True}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                profile.set_sensors(**values)
            self.assertEqual(profile.state(), state)

    def test_lifecycle_stop_disarms_disconnected_target_without_instant_braking(self):
        profile = MCCProfile()
        profile.feed_frame(profile.encode_start(2, "cw", 60))
        profile.advance_ns(100_000_000)
        before = profile.state()["actual_rpm"]
        profile.native.feed(profile.encode_start(10, "cw", 0)[:7])
        profile.native.set_faults(disconnected=True)
        profile.stop()
        state = profile.state()
        self.assertEqual((state["requested_speed"], state["target_speed"], state["target_temperature"]), (0, 0, 0))
        self.assertEqual(state["actual_rpm"], before)
        self.assertFalse(state["raw"]["connected"])
        self.assertEqual(state["raw"]["queued_responses"], 0)
        profile.advance_ns(1_000_000_000)
        self.assertEqual(profile.state()["actual_rpm"], 0)

    def test_tare_preserves_requested_motion(self):
        profile = MCCProfile()
        profile.feed_frame(profile.encode_start(3, "ccw", 60))
        profile.set_sensors(weight=250)
        profile.feed_frame(profile.encode_tare())
        state = profile.state()
        self.assertEqual((state["weight"], state["requested_speed"], state["target_temperature"]), (0, 3, 60))

    def test_native_log_retention_is_bounded(self):
        profile = MCCProfile()
        profile.native.log.extend({"event": "old", "at_ms": 0} for _ in range(10001))
        profile.sample()
        self.assertEqual(len(profile.native.log), 10000)


class MCCAuditRegressionTests(unittest.TestCase):
    def test_analyzer_cannot_join_tx_fragments_across_transport_reset(self):
        session = RecordingSession()
        raw = encode_tx(Operation.STANDARD, speed=10)
        session.feed(raw[:7])
        session.reset_transport()
        session.feed(raw[7:])
        result = analyze_recording(session.to_dict()).to_dict()
        self.assertEqual(result["tx_count"], 0)
        self.assertFalse(result["structurally_valid"])
        self.assertEqual(session.snapshot()["controller"]["target_rpm"], 0)

    def test_recording_limit_rejects_before_model_mutation_and_accepted_data_replays(self):
        session = RecordingSession(max_events=2)
        session.advance(1)
        session.sample()
        before = session.snapshot()
        with self.assertRaisesRegex(ValueError, "save and start a new recording"):
            session.advance(100)
        self.assertEqual(session.snapshot(), before)
        self.assertEqual(len(session.events), 2)
        self.assertTrue(replay_recording(session.to_dict(), max_events=2)["PASS"])
        with self.assertRaisesRegex(ValueError, "exceeds 1"):
            replay_recording(session.to_dict(), max_events=1)

    def test_delayed_rx_does_not_cross_legacy_tcp_clients(self):
        with PowerBoardTCPServer() as server:
            server.set_faults(delay_ms=100)
            with socket.create_connection(server.address, timeout=2) as first:
                wait_for(lambda: server.client_connected)
                first.sendall(encode_tx(Operation.STANDARD, speed=10))
                wait_for(lambda: server.snapshot()["queued_responses"] == 1)
            wait_for(lambda: not server.client_connected)
            self.assertEqual(server.snapshot()["queued_responses"], 0)
            self.assertEqual(server.snapshot()["controller"]["requested_speed_level"], 10)
            with socket.create_connection(server.address, timeout=2) as second:
                wait_for(lambda: server.client_connected)
                server.advance(100)
                second.settimeout(0.05)
                with self.assertRaises(socket.timeout):
                    second.recv(1)


if __name__ == "__main__":
    unittest.main()
