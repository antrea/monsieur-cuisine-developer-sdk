"""Original, configurable PowerBoard software model with explicit virtual time.

All rates and response rules below are illustrative hypotheses. Rotational
inertia is represented by deceleration/coasting coefficients, not a measured
moment of inertia. This model does not implement or certify firmware interlocks,
watchdogs, physical braking, or electrical behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import heapq
import math

from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, Operation, TxFrame, decode_frame
from monsieur_cuisine_sdk.profiles.mcc.protocol.simulator import ILLUSTRATIVE_RPM, VirtualController
from monsieur_cuisine_sdk.profiles.mcc.protocol.stream import StreamParser


def _nonnegative_integer(name: str, value: int) -> None:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError(f"{name} must be an integer in 0..{2**63 - 1}")


@dataclass(frozen=True, slots=True)
class PhysicsConfig:
    """Synthetic coefficients; no value is a measurement or appliance limit."""

    acceleration_rpm_s: float = 4000.0
    deceleration_rpm_s: float = 6000.0
    coast_deceleration_rpm_s: float = 1000.0
    heating_c_s: float = 1.0
    cooling_c_s: float = 0.1
    ambient_c: float = 20.0
    speed_rpm: tuple[int, ...] = ILLUSTRATIVE_RPM
    calibration_step_ms: int = 1000

    def __post_init__(self) -> None:
        if type(self.calibration_step_ms) is not int or not 1 <= self.calibration_step_ms <= 60000:
            raise ValueError("synthetic calibration step must be 1..60000 milliseconds")
        for name in ("acceleration_rpm_s", "deceleration_rpm_s", "coast_deceleration_rpm_s", "heating_c_s", "cooling_c_s", "ambient_c"):
            value = getattr(self, name)
            try:
                finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError(f"{name} must be a finite number")
            minimum = 0 if name in ("heating_c_s", "cooling_c_s", "ambient_c") else 0.000000001
            if value < minimum:
                raise ValueError(f"{name} is outside the synthetic configuration range")
        if self.ambient_c > 65535:
            raise ValueError("ambient_c cannot exceed the RX field range")
        if not isinstance(self.speed_rpm, tuple) or len(self.speed_rpm) != 11:
            raise ValueError("speed_rpm must be an immutable tuple of eleven integer RPM values")
        if any(type(value) is not int or not 0 <= value <= 65535 for value in self.speed_rpm):
            raise ValueError("speed_rpm values must be integers in 0..65535")
        if self.speed_rpm[0] != 0 or any(a >= b for a, b in zip(self.speed_rpm, self.speed_rpm[1:])):
            raise ValueError("speed_rpm must start at zero and increase strictly")

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["speed_rpm"] = list(self.speed_rpm)
        return result


class PowerBoardModel:
    """Deterministic incremental TX endpoint, synthetic physics, and queued RX.

    Network access belongs to a separate opt-in loopback server. Constructing or
    advancing this class opens no devices, sockets, or files and never sleeps.
    Lid/error fields are injected observations; they do not autonomously stop
    this hypothetical controller. Link disconnection retains the last target,
    deliberately making no assumption about an unverified firmware watchdog.
    """

    def __init__(self, config: PhysicsConfig | None = None) -> None:
        self.config = config if config is not None else PhysicsConfig()
        if not isinstance(self.config, PhysicsConfig):
            raise ValueError("config must be PhysicsConfig")
        self.now_ms = 0
        self.connected = True
        self.controller = VirtualController(actual_temperature=round(self.config.ambient_c))
        self.log: list[dict[str, object]] = []
        self._parser = StreamParser()
        self._velocity = 0.0
        self._temperature = float(self.config.ambient_c)
        self._requested_direction = Direction.CLOCKWISE
        self._coasting = False
        self._calibration_active = False
        self._calibration_start_ms = None
        self._delay_ms = 0
        self._drop_every = 0
        self._corrupt_every = 0
        self._response_count = 0
        self._queue: list[tuple[int, int, bytes]] = []

    def _event(self, event: str, **values: object) -> None:
        self.log.append({"at_ms": self.now_ms, "event": event, **values})

    def configure(self, **changes: object) -> None:
        """Atomically replace synthetic coefficients, preserving time/motion.

        A JSON list supplied as speed_rpm is normalized to an immutable tuple.
        Existing requested speed is mapped through the new illustrative table.
        """
        if "speed_rpm" in changes and isinstance(changes["speed_rpm"], list):
            changes["speed_rpm"] = tuple(changes["speed_rpm"])
        try:
            candidate = replace(self.config, **changes)
        except TypeError as exc:
            raise ValueError("unknown physics configuration field") from exc
        self.config = candidate
        self.controller.target_rpm = candidate.speed_rpm[self.controller.requested_speed_level]
        self._event("physics_configured", physics=candidate.to_dict())

    def reset_input(self) -> None:
        """Discard an incomplete TX fragment at a virtual client boundary."""
        retained = self._parser.buffered_bytes
        self._parser = StreamParser()
        self._event("input_reset", discarded_partial_bytes=retained)

    def reset_transport(self) -> None:
        """Synthetic session boundary: discard fragments and delayed RX.

        This is a host API, never a recovered UART command or MCU guarantee.
        Motion, targets, sensors, faults and virtual time are preserved.
        """
        pending = len(self._queue)
        self.reset_input()
        self._queue.clear()
        self._event("transport_reset", discarded_responses=pending)

    def feed(self, data: bytes) -> list[bytes]:
        """Consume arbitrary TX fragments; return currently ready RX frames.

        Every structurally and semantically accepted TX schedules one response.
        Unknown/calibration commands, RX input, and malformed TX never actuate.
        Fault options affect responses, not command execution. Disconnected
        input is ignored and cannot change the virtual controller's target.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("data must be bytes")
        if not self.connected:
            self._event("tx_ignored_disconnected", byte_count=len(data))
            return []
        frames = self._parser.feed(data)
        for issue in self._parser.issues:
            self._event("parse_issue", **issue.to_dict())
        self._parser.issues.clear()
        for frame in frames:
            if not isinstance(frame, TxFrame):
                self._event("tx_rejected", reason="RX input is not a command", hex=frame.raw.hex(" "))
                continue
            if frame.calibration in (0xE6, 0xE9) and not frame.warnings:
                # Synthetic firmware policy: repeated 10 Hz START does not reset
                # elapsed calibration time. No loads/real calibration are claimed.
                if not self._calibration_active:
                    self._calibration_active = True
                    self._calibration_start_ms = None
                    self.controller.calibration_step = 0
                if frame.calibration == 0xE9 and self._calibration_start_ms is None:
                    self._calibration_start_ms = self.now_ms
                self.controller.scale_state_raw = 1
                self.controller.requested_speed_level = self.controller.target_rpm = 0
                self.controller.requested_temperature_level = self.controller.target_temperature = 0
                self.controller.motor_on = self.controller.heater_on = False
                self._event("synthetic_calibration", command=frame.calibration)
                self._schedule_response()
                continue
            if frame.warnings or frame.direction is None:
                self._event("tx_rejected", reason="unknown, calibration, or semantically invalid command", hex=frame.raw.hex(" "), warnings=list(frame.warnings))
                continue
            try:
                Operation(frame.operation)
                # Existing independent codec/controller sets requested fields;
                # restore motion immediately so physics owns measured values.
                actual_rpm = self.controller.actual_rpm
                actual_direction = self.controller.direction
                self.controller.apply_tx(frame.raw)
                self.controller.actual_rpm = actual_rpm
                self.controller.direction = actual_direction
            except ValueError as exc:
                self._event("tx_rejected", reason=str(exc))
                continue
            if self._calibration_active:
                self._calibration_active = False
                self._calibration_start_ms = None
                self.controller.scale_state_raw = 2
                self.controller.calibration_step = 0
            self._requested_direction = frame.direction
            self._coasting = frame.operation == Operation.SLEEP
            self.controller.target_rpm = self.config.speed_rpm[self.controller.requested_speed_level]
            self._synchronize()
            self._event("tx", operation=frame.operation, hex=frame.raw.hex(" "))
            self._schedule_response()
        return self._ready()

    def _synchronize(self) -> None:
        self.controller.actual_rpm = min(65535, round(abs(self._velocity)))
        self.controller.actual_temperature = min(65535, max(0, round(self._temperature)))
        self.controller.direction = (
            Direction.CLOCKWISE if self._velocity > 0 else
            Direction.COUNTER_CLOCKWISE if self._velocity < 0 else self._requested_direction
        )

    @staticmethod
    def _approach(value: float, target: float, amount: float) -> float:
        return min(target, value + amount) if value < target else max(target, value - amount)

    def _motion(self, seconds: float) -> None:
        target = float(self.controller.target_rpm) * (1 if self._requested_direction == Direction.CLOCKWISE else -1)
        velocity = self._velocity
        # Opposite targets first consume an explicit finite braking interval.
        if velocity * target < 0:
            stopping_seconds = abs(velocity) / self.config.deceleration_rpm_s
            if seconds <= stopping_seconds:
                self._velocity = self._approach(velocity, 0.0, seconds * self.config.deceleration_rpm_s)
                return
            seconds -= stopping_seconds
            velocity = 0.0
            self._event("direction_zero_crossing", braking_ms=stopping_seconds * 1000,
                        zero_at_ms=self.now_ms + stopping_seconds * 1000)
        slowing = abs(target) < abs(velocity)
        rate = (
            self.config.coast_deceleration_rpm_s if target == 0 and self._coasting else
            self.config.deceleration_rpm_s if slowing else self.config.acceleration_rpm_s
        )
        self._velocity = self._approach(velocity, target, seconds * rate)

    def _heat(self, seconds: float) -> None:
        target = float(self.controller.target_temperature) if self.controller.heater_on else self.config.ambient_c
        if self.controller.heater_on and self._temperature < target:
            self._temperature = min(target, self._temperature + self.config.heating_c_s * seconds)
        elif self._temperature > max(target, self.config.ambient_c):
            self._temperature = max(target, self.config.ambient_c, self._temperature - self.config.cooling_c_s * seconds)
        elif not self.controller.heater_on and self._temperature < self.config.ambient_c:
            self._temperature = min(self.config.ambient_c, self._temperature + self.config.cooling_c_s * seconds)

    def advance(self, delta_ms: int) -> list[bytes]:
        """Advance explicit virtual time; integrate motion and return ready RX."""
        _nonnegative_integer("delta_ms", delta_ms)
        self._motion(delta_ms / 1000)
        self._heat(delta_ms / 1000)
        self.now_ms += delta_ms
        if self._calibration_active and self._calibration_start_ms is not None:
            self.controller.calibration_step = min(4, (self.now_ms - self._calibration_start_ms) // self.config.calibration_step_ms)
        self._synchronize()
        self._event("advance", delta_ms=delta_ms, velocity_rpm=self._velocity, temperature_c=self._temperature)
        return self._ready()

    def set_sensors(self, **changes: int | bool) -> None:
        """Inject synthetic measurements/status, without firmware interlocks."""
        self.controller.set_sensors(**changes)
        if "actual_rpm" in changes:
            sign = 1 if self.controller.direction == Direction.CLOCKWISE else -1
            self._velocity = self.controller.actual_rpm * sign
        if "actual_temperature" in changes:
            self._temperature = float(self.controller.actual_temperature)
        self._synchronize()
        self._event("sensors", changes=dict(changes))

    def set_faults(self, *, delay_ms: int = 0, drop_every: int = 0, corrupt_every: int = 0, disconnected: bool = False) -> None:
        """Replace deterministic response faults; zero disables each frequency.

        Frequencies count attempted responses across this model's lifetime.
        Disconnection clears queued RX and parser fragments. Reconnection never
        changes setpoints or implies that any pending STOP was delivered.
        """
        for name, value in (("delay_ms", delay_ms), ("drop_every", drop_every), ("corrupt_every", corrupt_every)):
            _nonnegative_integer(name, value)
        if type(disconnected) is not bool:
            raise ValueError("disconnected must be bool")
        self._delay_ms = delay_ms
        self._drop_every = drop_every
        self._corrupt_every = corrupt_every
        if self.connected == disconnected:
            self.reset_input()
            self._queue.clear()
        self.connected = not disconnected
        self._event("faults", **self.faults)

    @property
    def faults(self) -> dict[str, object]:
        return {"delay_ms": self._delay_ms, "drop_every": self._drop_every, "corrupt_every": self._corrupt_every, "disconnected": not self.connected}

    def disconnect(self) -> None:
        self.set_faults(delay_ms=self._delay_ms, drop_every=self._drop_every, corrupt_every=self._corrupt_every, disconnected=True)

    def reconnect(self) -> None:
        self.set_faults(delay_ms=self._delay_ms, drop_every=self._drop_every, corrupt_every=self._corrupt_every, disconnected=False)

    def _schedule_response(self) -> None:
        if not self.connected:
            self._event("rx_suppressed_disconnected")
            return
        self._response_count += 1
        if self._drop_every and self._response_count % self._drop_every == 0:
            self._event("rx_dropped", response_number=self._response_count)
            return
        raw = self.controller.response()
        corrupt = bool(self._corrupt_every and self._response_count % self._corrupt_every == 0)
        if corrupt:
            raw = raw[:25] + bytes((raw[25] ^ 1,)) + raw[26:]
        due = self.now_ms + self._delay_ms
        heapq.heappush(self._queue, (due, self._response_count, raw))
        self._event("rx_queued", due_ms=due, response_number=self._response_count, corrupt=corrupt)

    def _ready(self) -> list[bytes]:
        result = []
        if self.connected:
            while self._queue and self._queue[0][0] <= self.now_ms:
                due, number, raw = heapq.heappop(self._queue)
                result.append(raw)
                self._event("rx", due_ms=due, response_number=number, hex=raw.hex(" "))
        return result

    def sample(self) -> list[bytes]:
        """Schedule a current synthetic RX and drain responses now ready."""
        self._schedule_response()
        return self._ready()

    def snapshot(self) -> dict[str, object]:
        """Inspect current state without scheduling a response or advancing time."""
        raw = self.controller.response()
        return {
            "synthetic": True, "now_ms": self.now_ms, "connected": self.connected,
            "velocity_rpm": self._velocity, "temperature_c": self._temperature,
            "requested_direction": int(self._requested_direction),
            "controller": self.controller.snapshot(), "physics": self.config.to_dict(),
            "telemetry": decode_frame(raw).to_dict(), "rx_hex": raw.hex(" "),
            "faults": self.faults, "queued_responses": len(self._queue),
            "input_remainder_bytes": self._parser.buffered_bytes,
        }
