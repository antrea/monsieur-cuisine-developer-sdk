"""MCS adapter for the common model-owner API. No OS I/O occurs here.

Raw MCS motor levels have no established physical RPM conversion. All dynamics,
interlocks, firmware identifier and saturation behavior are synthetic policies.
"""
from dataclasses import asdict
import math

from . import protocol
from .simulation import DigitalTwin, ModelParameters


class MCSProfile:
    def __init__(self, *, seed=292, parameters=None):
        if parameters is None:
            configured = ModelParameters()
        elif isinstance(parameters, ModelParameters):
            configured = parameters
        elif isinstance(parameters, dict):
            try:configured = ModelParameters(**parameters)
            except TypeError as error:raise ValueError('invalid MCS parameter fields') from error
        else:
            raise ValueError('MCS parameters must be an object')
        self.parameters = asdict(configured)
        self.seed = seed
        self.native = DigitalTwin(seed=seed, parameters=configured)
        self._request_sequence = protocol.Sequence()
        self._parser = protocol.StreamParser()
        self._last_operation = None
        self.capabilities = {
            'model': 'MCS', 'profile': protocol.PROFILE, 'protocol': protocol.PROFILE,
            'tx_bytes': 39, 'legacy_tx_bytes': 35, 'rx_bytes': 48,
            'speed_unit': 'raw_motor_level', 'physical_rpm_verified': False,
            'requested_speed_unit': 'level', 'speed_levels': list(range(11)),
            'temperature_unit': 'celsius', 'duration_supported': True,
            'tare_supported': True, 'query_supported': True, 'rpm_available': False,
            'watchdog_verified': False,
            'actual_rpm_available': False, 'ui_speed_range': [0, 10],
            'raw_speed_range': [0, 20], 'raw_levels_per_ui_speed': 2,
            'directions': ['cw', 'ccw'], 'temperature_values': list(protocol.TEMPERATURES),
            'duration_seconds_range': [0, 5940], 'tare': True,
            'sensors': ['weight', 'temperature', 'lid_open', 'ntc_present', 'error_code', 'firmware'],
            'wire_evidence': 'CONFIRMED_IN_APK', 'model_evidence': 'INFERRED',
            'hardware_verified': False, 'firmware_is_synthetic': True,
            'ota': 'offline shape-only; no firmware validation or flashing',
            'sequence': 'independent counter skipping 0x66; no ACK correlation promised',
            'synthetic_policy': {
                'stop': 'remove targets and timer; preserve coast and cooling',
                'interlocks': 'configured lid/NTC/error blocks demand; targets retained and timer paused',
                'turbo': 'artificial raw level 20 fallback',
                'timer': 'a command re-sending the reported countdown (ceil of remaining) keeps the running deadline; any other value starts a new one',
                'temperature_saturation_celsius': [-100, 1000],
                'weight_saturation': 'signed 32-bit grams; raw saturation flags exposed',
            },
            'unknown': ['physical RPM mapping', 'physical interlocks', 'MCU firmware',
                        'original multistage program schedules', 'OTA success/retry semantics'],
        }

    def _sequenced(self, raw):
        frame = protocol.parse_frame(raw)
        return protocol.pack(frame.payload, sequence=self._request_sequence.next(),
                             subtype=frame.subtype, bitmap=frame.bitmap)

    def encode_start(self, speed, direction='cw', temperature=0, duration=0):
        if not isinstance(direction, str) or direction not in ('cw', 'ccw'):
            raise ValueError('direction must be cw or ccw')
        raw = protocol.encode_manual(speed=speed, reverse=direction == 'ccw',
                                     temperature=temperature, seconds=duration)
        return self._sequenced(raw)

    def encode_temperature(self, celsius):
        """Reissue the last accepted 0802 command with a new target.

        Function, raw speed level, direction, turbo lock and the remaining
        countdown are preserved; without a running program the target is
        applied as a manual operation at speed zero (previous behavior).
        """
        if type(celsius) is not int or celsius not in protocol.TEMPERATURES:
            raise ValueError('temperature absent from APK manual levels')
        level = protocol.TEMPERATURES.index(celsius)
        state = self.native.state
        last = self._last_operation
        if last is None or state.function in (0, 15) or last.function in (0, 15):
            raw = protocol.encode_operation(function=1, temperature_level=level, reverse=state.reverse)
        else:
            seconds = math.ceil(state.remaining - 1e-9) if state.timer_active else 0
            raw = protocol.encode_operation(speed_level=last.speed_level, reverse=bool(last.direction_raw),
                                            temperature_level=level, function=last.function, seconds=seconds,
                                            turbo_lock=last.turbo_lock, button=last.button, legacy=last.legacy)
        return self._sequenced(raw)

    def encode_stop(self):
        return self._sequenced(protocol.encode_operation(function=0))

    def encode_tare(self):
        return self._sequenced(protocol.encode_operation(opcode=0x0803, scale_mode=1))

    def encode_query(self):
        return self._sequenced(protocol.encode_operation(opcode=0x0801))

    def feed_frame(self, raw):
        # A complete foreign/malformed frame is rejected, never scanned for nested commands.
        frame = protocol.parse_frame(raw)
        if frame.bitmap != b'OB' or frame.subtype != 0:
            raise protocol.ProtocolError('MCS requires OB / subtype 0')
        response = self.native.transact(frame.raw)
        if frame.opcode == 0x0802:
            self._last_operation = protocol.decode_command(frame.raw)
        return [] if response is None else [response]

    def advance_ns(self, delta_ns):
        if type(delta_ns) is not int or delta_ns < 0:
            raise ValueError('delta_ns must be a nonnegative integer')
        from .simulation.limits import MAX_TICKS
        if delta_ns > MAX_TICKS * self.native.engine._tick_ns:
            raise ValueError('advance exceeds simulation tick work budget')
        self.native.advance(delta_ns / 1_000_000_000)
        return self.native.receive_ready()

    def sample(self):
        return [self.native.board.telemetry()]

    def state(self):
        s = self.native.state
        return {
            'requested_speed': s.requested_level / 2,
            'target_speed': s.requested_level,
            'actual_speed': abs(s.actual_level), 'speed_unit': 'raw_motor_level',
            'actual_rpm': None, 'physical_rpm_verified': False,
            'requested_direction': 'ccw' if s.reverse else 'cw',
            'actual_direction': 'ccw' if s.actual_level < 0 else 'cw' if s.actual_level > 0 else 'stopped',
            'target_temperature': s.target_temperature, 'temperature': s.temperature,
            'weight': s.weight, 'lid_open': s.lid_open, 'ntc_present': s.ntc_present,
            'error_code': s.error, 'firmware': s.firmware,
            'motor_on': abs(s.actual_level) > 0,
            'heater_on': s.heater_power > 1e-9,
            'raw': s.snapshot(),
        }

    def set_sensors(self, **values):
        allowed = {'weight', 'temperature', 'lid_open', 'ntc_present', 'error_code', 'firmware'}
        if set(values) - allowed:
            raise ValueError('unknown MCS sensor field')
        # Validate the complete normalized update before mutating either native field.
        for name, value in values.items():
            if name in ('lid_open', 'ntc_present'):
                if type(value) is not bool:raise ValueError(f'{name} must be bool')
            elif name in ('error_code', 'firmware'):
                protocol.uint(value, 8 if name == 'error_code' else 16, name)
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{name} must be finite numeric')
            elif name == 'temperature' and not -100 <= value <= 1000:
                raise ValueError('temperature must be in -100..1000 C')
            elif name == 'weight' and abs(value) > 1e8:
                raise ValueError('weight outside synthetic model range')
        sensors = {('error' if name == 'error_code' else name): value
                   for name, value in values.items() if name != 'firmware'}
        if 'weight' in sensors:
            sensors['mass'] = sensors.pop('weight') + self.native.state.tare_offset
        if sensors:self.native.sensors(**sensors)
        if 'firmware' in values:
            self.native.state.firmware = values['firmware']

    def reset_transport(self):
        self._parser.finish()
        self.native.board.pending.clear()
        self.native.board.faults()

    def stop(self):
        self.native.disarm()
        self.reset_transport()
