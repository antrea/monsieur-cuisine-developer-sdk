"""Common SDK adapter for the observed MCC build-292 frame format.

The codec describes statically observed host bytes. Dynamics and responses are
explicit software hypotheses. Importing or constructing this adapter opens no
socket, GUI, serial port, or physical appliance connection.
"""
from __future__ import annotations

import json
from typing import Any

from .protocol import codec as nativecodec
from .protocol.codec import Direction, Operation, TEMPERATURE_LEVELS, TxFrame, decode_frame, encode_tx
from .simulation.model import PhysicsConfig, PowerBoardModel
from .oem_policy import HostPolicy, recipe_temperature_level


_DIRECTIONS = {"cw": Direction.CLOCKWISE, "ccw": Direction.COUNTER_CLOCKWISE}


def _integer(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


class MCCProfile:
    """Private native model with common units and integer nanosecond clock."""

    def __init__(self, seed: int = 292, parameters: dict[str, Any] | None = None) -> None:
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError("parameters must be a JSON object")
        try:
            values = json.loads(json.dumps({} if parameters is None else parameters, allow_nan=False))
            if "speed_rpm" in values:
                values["speed_rpm"] = tuple(values["speed_rpm"])
            self.policy = HostPolicy(values.pop("host_policy", "oem"))
            config = PhysicsConfig(**values)
        except (TypeError, OverflowError) as exc:
            raise ValueError("invalid MCC physics parameters") from exc
        self.seed = seed
        self.parameters = {**config.to_dict(), "host_policy": self.policy.mode}
        self.native = PowerBoardModel(config)
        self._remainder_ns = 0
        self._operation = Operation.STOP

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "model": "MCC", "protocol": "build-292", "tx_bytes": 15, "rx_bytes": 27,
            "speed_unit": "rpm", "requested_speed_unit": "level", "speed_levels": list(range(11)),
            "temperature_unit": "celsius", "temperature_values": list(TEMPERATURE_LEVELS),
            "directions": ["cw", "ccw"], "duration_supported": False,
            "host_policy": self.policy.mode, "calibration_supported": "synthetic only",
            "tare_supported": True, "query_supported": False, "rpm_available": True,
            "sensors": ["weight", "temperature", "lid_open", "ntc_present", "error_code", "firmware"],
            "evidence": "Static APK host serializer/getter observations; no physical capture or firmware specification",
            "synthetic_policy": "Illustrative finite acceleration, braking, heating and queued telemetry; no certified interlocks or physical STOP acknowledgement",
            "watchdog_verified": False,
        }

    def _trim_log(self) -> None:
        del self.native.log[:-10000]

    def encode_start(self, speed: int, direction: str, temperature: int, duration: int = 0, *,
                     operation=Operation.STANDARD, hot_speed_confirmed=False) -> bytes:
        _integer("speed", speed, 0, 10)
        if not isinstance(direction, str) or direction not in _DIRECTIONS:
            raise ValueError("direction must be 'cw' or 'ccw'")
        if type(temperature) is not int or temperature not in TEMPERATURE_LEVELS:
            raise ValueError("MCC temperature must be an exact documented Celsius level")
        if type(duration) is not int or duration != 0:
            raise ValueError("MCC has no wire duration field; duration must be zero")
        return self._policy_command(operation, speed, _DIRECTIONS[direction],
                                    TEMPERATURE_LEVELS.index(temperature), hot_speed_confirmed)

    def _policy_command(self, operation, speed, direction, level, hot_speed_confirmed=False):
        state = self.state()
        decision = self.policy.start(operation, speed, direction, level,
                                     measured_temperature=state["temperature"],
                                     lid_open=state["lid_open"], error_code=state["error_code"],
                                     hot_speed_confirmed=hot_speed_confirmed)
        if decision.refusals or decision.confirmations:
            raise ValueError("MCC host policy: " + "; ".join(decision.refusals + decision.confirmations))
        return encode_tx(decision.operation, speed=decision.speed, direction=decision.direction,
                         temperature_level=decision.temperature_level)

    def encode_recipe_temperature(self, celsius: int) -> bytes:
        """Apply the OEM recipe binning, then the high-level host policy."""
        return self.encode_temperature(TEMPERATURE_LEVELS[recipe_temperature_level(celsius)])

    def encode_temperature(self, celsius: int) -> bytes:
        """Reissue the current operation, speed and direction with a new target.

        A halted controller uses STANDARD with the OEM minimum speed one.
        Heated/reverse speed limits apply; strict policy rejects adjustments.
        Raw feed remains independent of host policy.
        """
        if type(celsius) is not int or celsius not in TEMPERATURE_LEVELS:
            raise ValueError("MCC temperature must be an exact documented Celsius level")
        if celsius == 0 and self._operation in (Operation.STOP, Operation.SLEEP):
            return self.encode_stop()
        operation = self._operation if self._operation not in (Operation.STOP, Operation.SLEEP) else Operation.STANDARD
        return self._policy_command(operation, self.native.controller.requested_speed_level,
                                    Direction(self.native.snapshot()["requested_direction"]),
                                    TEMPERATURE_LEVELS.index(celsius))

    def encode_stop(self) -> bytes:
        direction = Direction(self.native.snapshot()["requested_direction"])
        return encode_tx(Operation.STOP, direction=direction)

    def encode_tare(self) -> bytes:
        controller = self.native.controller
        return encode_tx(self._operation, speed=controller.requested_speed_level,
                         temperature_level=controller.requested_temperature_level,
                         direction=Direction(self.native.snapshot()["requested_direction"]), tare=True)

    def encode_query(self) -> None:
        """No verified MCC query opcode exists; sample() is host model input."""
        return None

    def feed_frame(self, raw: bytes) -> list[bytes]:
        frame = decode_frame(raw)
        if not isinstance(frame, TxFrame):
            raise ValueError("MCC accepts TX command frames only")
        if frame.warnings or frame.direction is None:
            # The native model refuses these without actuation; report the
            # refusal instead of counting the frame as an accepted command.
            reason = "; ".join(frame.warnings) or "unknown direction"
            raise ValueError(f"MCC command rejected without actuation: {reason}")
        result = self.native.feed(frame.raw)
        self._operation = Operation(frame.operation)
        self._trim_log()
        return result

    def advance_ns(self, delta_ns: int) -> list[bytes]:
        if type(delta_ns) is not int or delta_ns < 0:
            raise ValueError("delta_ns must be a nonnegative integer")
        milliseconds, remainder = divmod(self._remainder_ns + delta_ns, 1_000_000)
        # Native validation happens before committing the fractional remainder.
        result = self.native.advance(milliseconds)
        self._remainder_ns = remainder
        self._trim_log()
        return result

    def sample(self) -> list[bytes]:
        result = self.native.sample()
        self._trim_log()
        return result

    def state(self) -> dict[str, Any]:
        raw = self.native.snapshot()
        board = raw["controller"]
        return {
            "requested_speed": board["requested_speed_level"],
            "target_speed": board["target_rpm"],
            "actual_speed": board["actual_rpm"], "speed_unit": "rpm", "actual_rpm": board["actual_rpm"],
            "requested_direction": "cw" if raw["requested_direction"] == 1 else "ccw",
            "actual_direction": "cw" if board["direction"] == 1 else "ccw",
            "target_temperature": board["target_temperature"], "temperature": board["actual_temperature"],
            "weight": board["weight"], "lid_open": board["lid_open"], "ntc_present": board["bowl_ntc_detected"],
            "error_code": board["error_code"], "firmware": board["firmware_version"],
            "motor_on": board["motor_on"], "heater_on": board["heater_on"], "raw": raw,
        }

    def set_sensors(self, **values: Any) -> None:
        mapping = {"weight": "weight", "temperature": "actual_temperature", "lid_open": "lid_open",
                   "ntc_present": "bowl_ntc_detected", "error_code": "error_code", "firmware": "firmware_version"}
        unknown = set(values) - mapping.keys()
        if unknown:
            raise ValueError(f"unsupported MCC sensors: {', '.join(sorted(unknown))}")
        # Native set_sensors validates a complete dataclass replacement before
        # applying any field. Profile validation preserves exact integer/bool types.
        changes = {}
        for name, value in values.items():
            if name in ("lid_open", "ntc_present"):
                if type(value) is not bool:
                    raise ValueError(f"{name} must be bool")
            else:
                bounds = (-(2**31), 2**31 - 1) if name == "weight" else (0, 255) if name == "error_code" else (0, 65535)
                _integer(name, value, *bounds)
            changes[mapping[name]] = value
        self.native.set_sensors(**changes)
        self._trim_log()

    def stop(self) -> None:
        """Disarm targets, retaining finite synthetic braking and measurements."""
        # Lifecycle cleanup must disarm even if a native disconnection fault was
        # injected. No response or immediate physical stop is claimed here.
        self.native.reset_input()
        connected = self.native.connected
        self.native.connected = True
        try:
            self.native.feed(self.encode_stop())
        finally:
            self.native.connected = connected
        self._operation = Operation.STOP
        self.native.reset_transport()
        self._trim_log()

    def reset_transport(self) -> None:
        self.native.reset_transport()
        self._trim_log()
