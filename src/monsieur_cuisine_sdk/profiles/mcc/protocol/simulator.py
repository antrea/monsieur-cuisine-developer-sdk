"""Deterministic, memory-only controller and communication scenarios.

Frames follow the documented format. Responses to commands, illustrative RPM
targets, and instantaneous motion are hypotheses for testing software; they are
not a motor model or a claim about the appliance's interlocks. No transport is
opened and no wall clock is read.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import heapq

from .codec import Direction, Operation, TEMPERATURE_LEVELS, TxFrame, checksum, decode_frame, encode_tx


# Illustrative points inside the observed UI RPM bands, NOT real target RPM.
ILLUSTRATIVE_RPM = (0, 200, 700, 1200, 2000, 4500, 7500, 10500, 13500, 16500, 19000)


def _integer(name: str, value: int, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")


@dataclass(slots=True)
class VirtualController:
    """Synthetic controller state; command effects are immediate hypotheses.

    Sensor fields can be changed through :meth:`set_sensors`. Calling
    :meth:`response` encodes every RX field, including the unknown byte 24.
    Calibration commands are rejected; no calibration procedure exists here.
    """

    requested_speed_level: int = 0
    target_rpm: int = 0
    actual_rpm: int = 0
    requested_temperature_level: int = 0
    target_temperature: int = 0
    actual_temperature: int = 20
    weight: int = 0
    firmware_version: int = 1
    direction: Direction = Direction.CLOCKWISE
    motor_on: bool = False
    heater_on: bool = False
    lid_open: bool = False
    error_detected: bool = False
    error_code: int = 0
    scale_stable: bool = True
    above_target_temperature: bool = False
    bowl_ntc_detected: bool = True
    extended_state: int = 0
    scale_state_raw: int = 2
    calibration_step: int = 0
    unknown_byte_24: int = 0

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        _integer("requested_speed_level", self.requested_speed_level, 0, 10)
        _integer("requested_temperature_level", self.requested_temperature_level, 0, 19)
        for field in ("target_rpm", "actual_rpm", "target_temperature", "actual_temperature", "firmware_version"):
            _integer(field, getattr(self, field), 0, 65535)
        _integer("weight", self.weight, -(2**31), 2**31 - 1)
        for field in ("error_code", "extended_state", "scale_state_raw", "calibration_step", "unknown_byte_24"):
            _integer(field, getattr(self, field), 0, 255)
        if not isinstance(self.direction, Direction):
            raise ValueError("direction must be a Direction member")
        for field in ("motor_on", "heater_on", "lid_open", "error_detected", "scale_stable", "above_target_temperature", "bowl_ntc_detected"):
            if type(getattr(self, field)) is not bool:
                raise ValueError(f"{field} must be bool")

    def set_sensors(self, **changes: int | bool) -> None:
        """Atomically inject measured/status values, never a hardware action.

        Allowed names: actual_rpm, actual_temperature, weight, firmware_version,
        lid_open, error_detected, error_code, scale_stable,
        above_target_temperature, bowl_ntc_detected, scale_state_raw,
        calibration_step, unknown_byte_24. Setting error_code also sets the flag
        unless error_detected is explicitly provided.
        """
        allowed = {
            "actual_rpm", "actual_temperature", "weight", "firmware_version",
            "lid_open", "error_detected", "error_code", "scale_stable",
            "above_target_temperature", "bowl_ntc_detected", "scale_state_raw",
            "calibration_step", "unknown_byte_24",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported sensor fields: {', '.join(sorted(unknown))}")
        if "error_code" in changes and "error_detected" not in changes:
            changes["error_detected"] = changes["error_code"] != 0
        candidate = replace(self, **changes)
        for name in changes:
            setattr(self, name, getattr(candidate, name))

    def apply_tx(self, raw: bytes | str) -> None:
        """Interpret a valid TX in memory, with immediate synthetic response.

        A STOP/SLEEP sets measured RPM to zero instantly. Other known operations
        use illustrative RPM points. Lid/error inputs do not emulate firmware
        interlocks; the separate intermittent program applies its own guards.
        """
        frame = decode_frame(raw)
        if not isinstance(frame, TxFrame):
            raise ValueError("controller accepts TX frames only")
        if frame.calibration:
            raise ValueError("calibration commands are not simulated")
        try:
            operation = Operation(frame.operation)
        except ValueError as exc:
            raise ValueError("unknown operation is not simulated") from exc
        if frame.direction is None or frame.speed_level not in range(11) or frame.temperature_level not in range(20):
            raise ValueError("invalid command parameter")
        self.direction = frame.direction
        if frame.tare:
            self.weight = 0
        halted = operation in (Operation.STOP, Operation.SLEEP)
        self.requested_speed_level = 0 if halted else frame.speed_level
        self.requested_temperature_level = 0 if halted else frame.temperature_level
        self.target_rpm = ILLUSTRATIVE_RPM[self.requested_speed_level]
        self.actual_rpm = self.target_rpm
        self.target_temperature = TEMPERATURE_LEVELS[self.requested_temperature_level]
        self.motor_on = self.requested_speed_level > 0
        self.heater_on = self.requested_temperature_level > 0
        self.extended_state = int(operation) if operation in (Operation.STEAM, Operation.TOAST, Operation.KNEAD) else 0

    def response(self) -> bytes:
        """Build a complete synthetic 27-byte RX with the current fields."""
        self._validate()
        data = bytearray(27)
        data[:3] = b"\x55\x1b\xb1"
        state = {(False, False): 0, (True, True): 1, (False, True): 2, (True, False): 3}[(self.motor_on, self.heater_on)]
        data[3] = (
            state | (int(self.scale_stable) << 2)
            | (int(self.direction == Direction.CLOCKWISE) << 3)
            | (int(self.error_detected) << 4)
            | (int(self.above_target_temperature) << 5)
            | (int(self.bowl_ntc_detected) << 6)
            | (int(self.lid_open) << 7)
        )
        data[4:7] = bytes((self.extended_state, self.error_code, self.requested_speed_level))
        data[7:9] = self.target_rpm.to_bytes(2, "big")
        data[9:11] = self.actual_rpm.to_bytes(2, "big")
        data[11] = self.requested_temperature_level
        data[12:14] = self.target_temperature.to_bytes(2, "big")
        data[14:16] = self.actual_temperature.to_bytes(2, "big")
        data[16:20] = self.weight.to_bytes(4, "big", signed=True)
        data[20:22] = self.firmware_version.to_bytes(2, "big")
        data[22:25] = bytes((self.scale_state_raw, self.calibration_step, self.unknown_byte_24))
        data[25] = checksum(data[:25])
        data[26] = 0xAA
        return bytes(data)

    def snapshot(self) -> dict[str, object]:
        """Return JSON-compatible state, with direction as an Android integer."""
        result = asdict(self)
        result["direction"] = int(self.direction)
        return result


@dataclass(frozen=True, slots=True)
class ReceivedFrame:
    """Local delivery metadata; sequence/timestamps are absent from the wire."""

    raw: bytes
    generated_ms: int
    received_ms: int
    sequence: int

    def to_dict(self) -> dict[str, object]:
        return {"hex": self.raw.hex(" "), "generated_ms": self.generated_ms, "received_ms": self.received_ms, "sequence": self.sequence}


class MemoryLink:
    """Virtual clock plus queued RX delay/loss/corruption injection.

    TX commands are applied immediately in memory. ``delay_ms``, ``drop``, and
    ``corrupt`` affect only their synthetic responses. A corrupted response has
    one checksum bit flipped. No periodic behavior occurs implicitly.
    """

    def __init__(self, controller: VirtualController | None = None) -> None:
        self.controller = controller if controller is not None else VirtualController()
        self.now_ms = 0
        self.log: list[dict[str, object]] = []
        self._queue: list[tuple[int, int, ReceivedFrame]] = []
        self._sequence = 0
        self._delivered = 0

    def send(self, raw: bytes | str, *, delay_ms: int = 0, drop: bool = False, corrupt: bool = False) -> None:
        """Apply TX immediately and schedule one synthetic RX response."""
        self._options(delay_ms, drop, corrupt)
        self.controller.apply_tx(raw)
        command = decode_frame(raw)
        self.log.append({"at_ms": self.now_ms, "event": "tx", "hex": command.raw.hex(" ")})
        self.sample(delay_ms=delay_ms, drop=drop, corrupt=corrupt)

    @staticmethod
    def _options(delay_ms: int, drop: bool, corrupt: bool) -> None:
        _integer("delay_ms", delay_ms, 0, 2**63 - 1)
        if type(drop) is not bool or type(corrupt) is not bool:
            raise ValueError("drop and corrupt must be bool")

    def sample(self, *, delay_ms: int = 0, drop: bool = False, corrupt: bool = False) -> None:
        """Schedule a state snapshot without changing the virtual controller."""
        self._options(delay_ms, drop, corrupt)
        raw = self.controller.response()
        self._sequence += 1
        if drop:
            self.log.append({"at_ms": self.now_ms, "event": "rx_dropped", "snapshot_id": self._sequence})
            return
        if corrupt:
            raw = raw[:25] + bytes((raw[25] ^ 1,)) + raw[26:]
        arrival = self.now_ms + delay_ms
        frame = ReceivedFrame(raw, self.now_ms, arrival, self._sequence)
        heapq.heappush(self._queue, (arrival, self._sequence, frame))
        self.log.append({"at_ms": self.now_ms, "event": "rx_queued", "arrival_ms": arrival, "snapshot_id": self._sequence, "corrupt": corrupt})

    def advance(self, delta_ms: int) -> list[ReceivedFrame]:
        """Advance virtual milliseconds and return all newly ready responses."""
        _integer("delta_ms", delta_ms, 0, 2**63 - 1)
        self.now_ms += delta_ms
        return self.receive_ready()

    def receive_ready(self) -> list[ReceivedFrame]:
        """Drain ready RX in delivery order; retains individual transient events."""
        frames = []
        while self._queue and self._queue[0][0] <= self.now_ms:
            _, _, frame = heapq.heappop(self._queue)
            self._delivered += 1
            # Metadata counts host deliveries, not snapshot creation. A delayed
            # snapshot can legitimately arrive after a later generated one.
            frame = replace(frame, sequence=self._delivered)
            frames.append(frame)
            self.log.append({"at_ms": frame.received_ms, "event": "rx", **frame.to_dict()})
        return frames


def run_demo() -> dict[str, object]:
    """Deterministic successful start/stop plus delay/loss/corruption scenario."""
    link = MemoryLink(VirtualController(weight=-12, unknown_byte_24=0xA5))
    link.send(encode_tx(Operation.STANDARD, speed=2, direction=Direction.COUNTER_CLOCKWISE), delay_ms=100)
    frames = link.advance(100)
    link.controller.set_sensors(actual_temperature=42, weight=125)
    link.sample(drop=True)
    link.sample(corrupt=True)
    frames.extend(link.receive_ready())
    link.send(encode_tx(Operation.STOP), delay_ms=20)
    frames.extend(link.advance(20))
    results: list[dict[str, object]] = []
    for event in frames:
        try:
            decoded = decode_frame(event.raw)
            results.append({**event.to_dict(), "valid": True, "decoded": decoded.to_dict()})
        except ValueError as exc:
            results.append({**event.to_dict(), "valid": False, "error": str(exc)})
    return {
        "synthetic": True,
        "behavior": "Instantaneous illustrative RPM response; no acceleration physics or hardware safety validation.",
        "now_ms": link.now_ms, "frames": results, "log": link.log,
        "final_state": link.controller.snapshot(),
    }


def run_intermittent_demo() -> dict[str, object]:
    """Run a complete virtual-time intermittent session without sleeping."""
    from .program import IntermittentConfig, IntermittentProgram

    link = MemoryLink()
    config = IntermittentConfig(spin_ms=2000, rest_ms=3000, total_ms=12000, speed=2)

    def send(raw: bytes) -> None:
        link.send(raw, delay_ms=1)

    program = IntermittentProgram(config, send)
    link.sample()
    for frame in link.receive_ready():
        program.receive(frame.raw, link.now_ms, received_ms=frame.received_ms, sequence=frame.sequence)
    program.start(0)
    # Fresh synthetic telemetry every 250 virtual milliseconds, plus queued TX
    # responses. Deliver each event separately, never coalesce safety events.
    while link.now_ms < config.total_ms:
        link.sample(delay_ms=1)
        for frame in link.advance(250):
            program.receive(frame.raw, link.now_ms, received_ms=frame.received_ms, sequence=frame.sequence)
        program.tick(link.now_ms)
    return {
        "synthetic": True, "behavior": "Memory-only software scheduling hypothesis; no physical stop acknowledgement.",
        "config": config.to_dict(), "state": program.state.value,
        "reason": program.reason, "program_log": program.log, "link_log": link.log,
        "final_state": link.controller.snapshot(),
    }
