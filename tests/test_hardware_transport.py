"""Host transport proofs. Virtual endpoints are never classified as OEM evidence."""
from collections import deque
import importlib.util
import unittest

from monsieur_cuisine_sdk.hardware import (
    ConnectionState, MCCSerialSession, ReplayTransport, SerialTransport, TelemetryTimeout,
)
from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Operation, decode_frame, encode_tx
from monsieur_cuisine_sdk.profiles.mcc.protocol.simulator import VirtualController


class Clock:
    value = 0.0
    def __call__(self):
        return self.value


class Endpoint:
    def __init__(self):
        self.opened = False
        self.incoming = deque()
        self.outgoing = bytearray()
        self.failure = False
        self.short_write = 15

    def open(self):
        self.opened = True

    def read(self, size):
        if self.failure:
            raise OSError("virtual cable disconnected")
        return self.incoming.popleft() if self.incoming else b""

    def write(self, data):
        count = min(len(data), self.short_write)
        self.outgoing.extend(data[:count])
        return count

    def close(self):
        self.opened = False


class HardwareSessionTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.endpoint = Clock(), Endpoint()
        self.board = VirtualController()

    def session(self, active=False):
        session = MCCSerialSession(self.endpoint, active=active, clock=self.clock)
        self.assertFalse(self.endpoint.opened)
        session.connect()
        return session

    def telemetry(self, session):
        self.endpoint.incoming.append(self.board.response())
        return session.poll()

    def test_read_only_never_writes_even_stop_or_close(self):
        session = self.session()
        self.assertEqual(len(self.telemetry(session)), 1)
        with self.assertRaises(PermissionError):
            session.arm()
        with self.assertRaises(PermissionError):
            session.stop()
        session.close()
        self.assertFalse(self.endpoint.outgoing)
        self.assertIsNone(session.telemetry)

    def test_partial_corrupt_echo_and_obsolete_input(self):
        session = self.session()
        raw = self.board.response()
        self.endpoint.incoming.extend([raw[:10], raw[10:]])
        self.assertEqual(session.poll(), [])
        self.assertEqual(len(session.poll()), 1)
        damaged = bytearray(raw); damaged[25] ^= 1
        self.endpoint.incoming.extend([bytes(damaged) + encode_tx(Operation.STOP) + raw, raw[:5]])
        self.assertEqual(len(session.poll()), 1)
        session.poll()
        self.clock.value = 0.6
        self.endpoint.incoming.append(raw[5:])
        self.assertEqual(session.poll(), [])
        self.assertTrue(any(e.detail == "partial frame expired" for e in session.events))
        self.assertEqual(len(self.telemetry(session)), 1)

    def test_active_requires_idle_fresh_safe_telemetry_and_strict_policy(self):
        session = self.session(True)
        with self.assertRaises(TelemetryTimeout):
            session.arm()
        self.board.actual_rpm = 50
        self.telemetry(session)
        with self.assertRaises(PermissionError):
            session.arm()
        self.board.actual_rpm = 0
        self.telemetry(session); session.arm()
        with self.assertRaises(PermissionError):
            session.command(encode_tx(Operation.STANDARD, speed=10, temperature_level=5))
        self.assertFalse(self.endpoint.outgoing)

    def test_latched_cadence_short_writes_and_no_catchup_burst(self):
        session = self.session(True)
        self.telemetry(session); session.arm()
        self.endpoint.short_write = 2
        command = encode_tx(Operation.STANDARD, speed=2)
        session.command(command); session.poll()
        self.assertEqual(bytes(self.endpoint.outgoing), command)
        self.clock.value = 0.099; session.poll()
        self.assertEqual(len(self.endpoint.outgoing), 15)
        self.clock.value = 0.5; self.telemetry(session)
        self.assertEqual(bytes(self.endpoint.outgoing), command * 2)
        session.close()
        self.assertEqual(decode_frame(bytes(self.endpoint.outgoing[-15:])).operation, Operation.STOP)

    def test_lost_telemetry_sends_one_stop_disarms_and_never_resumes(self):
        session = self.session(True)
        self.telemetry(session); session.arm()
        session.command(encode_tx(Operation.STANDARD, speed=2)); session.poll()
        self.clock.value = 1.001
        with self.assertRaises(TelemetryTimeout):
            session.poll()
        self.assertFalse(session.armed)
        self.assertEqual(decode_frame(bytes(self.endpoint.outgoing[-15:])).operation, Operation.STOP)
        previous = bytes(self.endpoint.outgoing)
        self.telemetry(session)
        self.assertEqual(bytes(self.endpoint.outgoing), previous)

    def test_each_unsafe_sensor_causes_stop(self):
        for name, value in (("lid_open", True), ("error_code", 3), ("error_detected", True), ("bowl_ntc_detected", False)):
            with self.subTest(name=name):
                self.board = VirtualController()
                self.endpoint = Endpoint()
                session = self.session(True)
                self.telemetry(session); session.arm()
                session.command(encode_tx(Operation.STANDARD, speed=2))
                setattr(self.board, name, value)
                self.telemetry(session)
                self.assertFalse(session.armed)
                self.assertEqual(decode_frame(bytes(self.endpoint.outgoing)).operation, Operation.STOP)

    def test_disconnect_fails_closed_and_reconnect_discards_active_command(self):
        session = self.session(True)
        self.telemetry(session); session.arm()
        self.endpoint.failure = True
        with self.assertRaises(OSError):
            session.poll()
        self.assertEqual(session.state, ConnectionState.FAILED)
        self.assertFalse(session.armed or self.endpoint.opened)
        self.endpoint.failure = False; session.connect()
        self.assertIsNone(session.telemetry)
        session.poll()
        self.assertFalse(self.endpoint.outgoing)

    def test_zero_length_write_does_not_spin(self):
        session = self.session(True)
        self.telemetry(session); session.arm()
        self.endpoint.short_write = 0
        with self.assertRaises(ConnectionError):
            session.poll()
        self.assertEqual(session.state, ConnectionState.FAILED)

    def test_replay_uses_original_observation_bytes_and_virtual_clock(self):
        raw = self.board.response()
        transport = ReplayTransport([(0.0, raw[:4]), (0.2, raw[4:])], clock=self.clock)
        with MCCSerialSession(transport, clock=self.clock) as session:
            self.assertEqual(session.poll(), [])
            self.clock.value = 0.2
            self.assertEqual(session.poll()[0].raw, raw)
            with self.assertRaises(PermissionError):
                transport.write(b"x")

    @unittest.skipUnless(importlib.util.find_spec("serial"), "optional pyserial extra not installed")
    def test_actual_pyserial_virtual_loopback(self):
        import serial
        transport = SerialTransport("loop://", factory=lambda **kw: serial.serial_for_url(
            "loop://", do_not_open=True, **{k: v for k, v in kw.items() if k != "port"}))
        with MCCSerialSession(transport, clock=self.clock) as session:
            transport._current().write(self.board.response())
            self.assertEqual(len(session.poll()), 1)
            with self.assertRaises(PermissionError):
                transport.write(encode_tx(Operation.STOP))
