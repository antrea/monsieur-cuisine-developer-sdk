"""Independent intermittent-program state machine for offline experiments.

All time is supplied as nonnegative integer virtual milliseconds. This model
cannot confirm a physical stop or correlate RX with TX: the wire has no request
identifier. A new post-STOP telemetry delivery is only a software observation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable

from .codec import Direction, Operation, RxFrame, decode_frame, encode_tx


def _positive(name: str, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class IntermittentConfig:
    """Synthetic scheduling parameters, not recommended appliance settings."""

    spin_ms: int
    rest_ms: int
    total_ms: int
    speed: int
    direction: Direction = Direction.COUNTER_CLOCKWISE
    stop_timeout_ms: int = 2000
    max_sample_age_ms: int = 1500

    def __post_init__(self) -> None:
        for name in ("spin_ms", "rest_ms", "total_ms", "stop_timeout_ms", "max_sample_age_ms"):
            _positive(name, getattr(self, name))
        if type(self.speed) is not int or not 1 <= self.speed <= 10:
            raise ValueError("speed must be an integer in 1..10")
        if not isinstance(self.direction, Direction):
            raise ValueError("direction must be a Direction member")
        if self.direction == Direction.COUNTER_CLOCKWISE and self.speed > 3:
            raise ValueError("manual counter-clockwise speed must not exceed 3")
        if self.total_ms > (900000 if self.speed > 6 else 5940000):
            raise ValueError("total duration exceeds the observed application limit")

    def to_dict(self) -> dict[str, object]:
        values = asdict(self)
        values["direction"] = int(self.direction)
        return values


class ProgramState(str, Enum):
    IDLE = "IDLE"
    SPIN = "SPIN"
    WAIT_STOP = "WAIT_STOP"
    REST = "REST"
    FINISHED = "FINISHED"
    STOPPED = "STOPPED"
    FAULT = "FAULT"


ACTIVE_STATES = frozenset((ProgramState.SPIN, ProgramState.WAIT_STOP, ProgramState.REST))


@dataclass(frozen=True, slots=True)
class _Sample:
    frame: RxFrame
    received_ms: int
    sequence: int


class IntermittentProgram:
    """Single-session state machine with immediate fault latching.

    ``send`` accepts TX bytes and either returns normally or raises an exception.
    Returning normally indicates only this memory callback's success, never a
    hardware acknowledgement. Every RX must call ``receive`` separately.
    A terminal instance cannot be rearmed; create a new instance for a deliberate
    new session. Callbacks should be serialized and must not call back into this
    program synchronously.
    """

    def __init__(self, config: IntermittentConfig, send: Callable[[bytes], None]) -> None:
        if not isinstance(config, IntermittentConfig) or not callable(send):
            raise ValueError("a validated config and callable send are required")
        self.config = config
        self._send = send
        self.state = ProgramState.IDLE
        self.reason: str | None = None
        self.log: list[dict[str, object]] = []
        self._now = 0
        self._sample: _Sample | None = None
        self._last_sequence = 0
        self._total_deadline: int | None = None
        self._phase_deadline: int | None = None
        self._stop_sent_ms: int | None = None
        self._stop_sequence = 0

    def _time(self, now_ms: int) -> None:
        if type(now_ms) is not int or now_ms < 0 or now_ms < self._now:
            if self.state in ACTIVE_STATES:
                self._terminal(ProgramState.FAULT, "invalid_clock")
            raise ValueError("now_ms must be a nonnegative monotonic integer")
        self._now = now_ms

    def _event(self, event: str, **fields: object) -> None:
        self.log.append({"at_ms": self._now, "event": event, **fields})

    def _command(self, *, start: bool) -> bool:
        raw = encode_tx(
            Operation.STANDARD if start else Operation.STOP,
            speed=self.config.speed if start else 0,
            direction=self.config.direction,
        )
        self._event("tx", command="START" if start else "STOP", hex=raw.hex(" "))
        try:
            self._send(raw)
        except Exception as exc:
            # Exception text can contain external data; public logs retain only
            # the exception type and never claim the command was delivered.
            self._event("send_failed", exception_type=type(exc).__name__)
            return False
        return True

    def _terminal(self, state: ProgramState, reason: str) -> None:
        if self.state in (ProgramState.FINISHED, ProgramState.STOPPED, ProgramState.FAULT):
            return
        self.state = state  # latch before the best-effort STOP callback
        self.reason = reason
        self._phase_deadline = None
        self._event("state", state=state.value, reason=reason)
        if not self._command(start=False):
            self.state = ProgramState.FAULT
            self.reason = "stop_send_failed"
            self._event("state", state=self.state.value, reason=self.reason)

    def _deadlines(self) -> bool:
        if self.state not in ACTIVE_STATES:
            return self.state != ProgramState.IDLE
        if self._total_deadline is not None and self._now >= self._total_deadline:
            self._terminal(ProgramState.FINISHED, "total_deadline")
            return True
        if self.state == ProgramState.WAIT_STOP and self._phase_deadline is not None and self._now >= self._phase_deadline:
            self._terminal(ProgramState.FAULT, "stop_timeout")
            return True
        return False

    def _unsafe(self, *, require_stopped: bool) -> str | None:
        sample = self._sample
        if sample is None:
            return "missing_telemetry"
        if self._now - sample.received_ms > self.config.max_sample_age_ms:
            return "stale_telemetry"
        frame = sample.frame
        if frame.lid_open:
            return "lid_open"
        if frame.error_detected or frame.error_code != 0 or frame.android_scale_state == "overload":
            return "controller_error"
        if frame.heater_on:
            return "unexpected_heating"
        if frame.actual_temperature >= 60 and self.config.speed >= 4:
            return "thermal_warning_required"
        if require_stopped and (frame.motor_on or frame.actual_rpm != 0):
            return "unexpected_motion"
        return None

    def _guard(self, *, require_stopped: bool = False) -> bool:
        reason = self._unsafe(require_stopped=require_stopped)
        if reason is not None:
            self._terminal(ProgramState.FAULT, reason)
            return False
        return True

    def receive(self, raw: bytes | str, now_ms: int, *, received_ms: int | None = None, sequence: int | None = None) -> None:
        """Process each RX immediately using local receive metadata.

        Optional ``sequence`` is a strictly increasing host delivery counter,
        not a wire field. ``received_ms`` permits testing delayed processing; it
        cannot be in the future. Identical bytes received anew are valid. Fault
        events cannot be overwritten by subsequent normal telemetry.
        """
        self._time(now_ms)
        if self._deadlines():
            return
        arrival = now_ms if received_ms is None else received_ms
        serial = self._last_sequence + 1 if sequence is None else sequence
        if type(arrival) is not int or not 0 <= arrival <= now_ms or type(serial) is not int or serial <= self._last_sequence:
            self._terminal(ProgramState.FAULT, "invalid_receive_metadata")
            return
        if self._sample is not None and arrival < self._sample.received_ms:
            self._terminal(ProgramState.FAULT, "out_of_order_telemetry")
            return
        try:
            frame = decode_frame(raw)
        except ValueError:
            self._terminal(ProgramState.FAULT, "invalid_telemetry")
            return
        if not isinstance(frame, RxFrame):
            self._terminal(ProgramState.FAULT, "expected_rx")
            return
        self._sample = _Sample(frame, arrival, serial)
        self._last_sequence = serial
        self._event("rx", received_ms=arrival, sequence=serial)
        if self.state not in ACTIVE_STATES:
            return
        if not self._guard(require_stopped=self.state == ProgramState.REST):
            return
        if self.state == ProgramState.WAIT_STOP:
            assert self._stop_sent_ms is not None
            if arrival > self._stop_sent_ms and serial > self._stop_sequence and not frame.motor_on and frame.actual_rpm == 0:
                self.state = ProgramState.REST
                # Count a full rest interval after processing the observation.
                self._phase_deadline = now_ms + self.config.rest_ms
                self._event("state", state=self.state.value, rest_deadline_ms=self._phase_deadline)

    def start(self, now_ms: int) -> None:
        """Start once after fresh, stationary, closed-lid, error-free telemetry."""
        self._time(now_ms)
        if self.state != ProgramState.IDLE:
            raise RuntimeError("session is already started or terminal; create a new instance")
        if not self._guard(require_stopped=True):
            return
        self._total_deadline = now_ms + self.config.total_ms
        self.state = ProgramState.SPIN
        self._phase_deadline = now_ms + self.config.spin_ms
        self._event("state", state=self.state.value, total_deadline_ms=self._total_deadline)
        if not self._command(start=True):
            self._terminal(ProgramState.FAULT, "start_send_failed")

    def tick(self, now_ms: int) -> None:
        """Process deadlines once; missed cycles are never replayed in a burst."""
        self._time(now_ms)
        if self.state not in ACTIVE_STATES or self._deadlines():
            return
        if not self._guard(require_stopped=self.state == ProgramState.REST):
            return
        assert self._phase_deadline is not None
        if now_ms < self._phase_deadline:
            return
        if self.state == ProgramState.SPIN:
            self.state = ProgramState.WAIT_STOP
            self._stop_sent_ms = now_ms
            self._stop_sequence = self._last_sequence
            self._phase_deadline = now_ms + self.config.stop_timeout_ms
            self._event("state", state=self.state.value, stop_deadline_ms=self._phase_deadline)
            if not self._command(start=False):
                self._terminal(ProgramState.FAULT, "stop_send_failed")
        elif self.state == ProgramState.REST:
            self.state = ProgramState.SPIN
            self._phase_deadline = now_ms + self.config.spin_ms
            self._event("state", state=self.state.value)
            if not self._command(start=True):
                self._terminal(ProgramState.FAULT, "start_send_failed")

    def stop(self, now_ms: int) -> None:
        """Latch a user stop. There is no automatic resume or reset operation."""
        self._time(now_ms)
        self._terminal(ProgramState.STOPPED, "user_stop")
