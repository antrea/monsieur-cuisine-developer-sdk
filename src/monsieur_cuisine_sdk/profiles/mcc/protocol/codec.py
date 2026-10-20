"""Independent, offline encoding and decoding of the build 292 frame format.

The format follows static application analysis, not a firmware specification.
Unknown semantic values remain available; invalid framing raises ``FrameError``.
No transport or hardware access is provided by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar


class FrameError(ValueError):
    """Malformed input, with a stable machine-readable ``code``.

    A streaming truncation additionally exposes the retained ``raw`` bytes,
    ``bytes_remaining`` (their count), and the expected/missing frame size when
    the length byte was available.
    """

    def __init__(
        self,
        message: str,
        code: str = "invalid_frame",
        *,
        raw: bytes = b"",
        expected_size: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.raw = raw
        self.bytes_remaining = len(raw)
        self.expected_size = expected_size
        self.missing_bytes = (
            max(0, expected_size - len(raw)) if expected_size is not None else None
        )


class Direction(IntEnum):
    """Android representation; the TX wire representation is its inverse."""

    COUNTER_CLOCKWISE = 0
    CLOCKWISE = 1


class Operation(IntEnum):
    STOP = 0
    STANDARD = 1
    STEAM = 3
    TOAST = 4
    KNEAD = 5
    SLEEP = 15
    TURBO = 198


TEMPERATURE_LEVELS: tuple[int, ...] = (
    0, 37, 45, 50, 55, 60, 65, 70, 75, 80,
    85, 90, 95, 100, 105, 110, 115, 120, 125, 130,
)
_ERROR_TO_ANDROID = {1: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 12, 8: 13}
_ERROR_NAMES = {
    1: "serial_communication", 3: "overvoltage", 4: "undervoltage",
    5: "motor", 6: "water_missing", 7: "motor_overheat", 8: "maximum_runtime",
}
ERROR_DESCRIPTIONS = {
    1: "Internal serial communication fault", 3: "Input voltage too high",
    4: "Input voltage too low", 5: "Motor overheated; allow it to cool",
    6: "Pot overheated; add liquid", 7: "Motor overloaded; switch off and cool",
    8: "Maximum runtime exceeded",
}
_CALIBRATION_NAMES = {0: "exit_or_normal", 230: "enter", 233: "start"}
_CALIBRATION_STEPS = {
    0: "init", 1: "zero", 2: "one_kg", 3: "three_kg",
    4: "success", 5: "overload", 7: "failure",
}
_EXTENDED_STATES = {3: "steam", 4: "toast", 5: "knead"}


def parse_hex(text: str) -> bytes:
    """Parse nonempty compact or ASCII-whitespace-separated hexadecimal bytes.

    Prefixes, comments, commas and colon separators are intentionally rejected.
    File-oriented clients may handle comments before calling this function.
    """

    if not isinstance(text, str):
        raise FrameError("Hex input must be text.", "input_type")
    try:
        data = bytes.fromhex(text)
    except ValueError as exc:
        raise FrameError(f"Invalid hexadecimal input: {exc}", "hex") from exc
    if not data:
        raise FrameError("Hex input is empty.", "empty")
    return data


def checksum(data: bytes) -> int:
    """Return the unsigned additive checksum modulo 256 (not a CRC)."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise FrameError("Checksum input must be bytes.", "input_type")
    return sum(bytes(data)) & 0xFF


def _integer(value: int, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FrameError(f"{name} must be an integer.", "field_type")
    if not low <= value <= high:
        raise FrameError(f"{name} must be in {low}..{high}.", "field_range")
    return int(value)


def encode_tx(
    operation: Operation | int = Operation.STOP,
    *,
    speed: int = 0,
    temperature_level: int = 0,
    direction: Direction = Direction.CLOCKWISE,
    tare: bool = False,
) -> bytes:
    """Build a synthetic 15-byte TX frame without accessing any device.

    Values outside the documented ranges are rejected, unlike the original
    serializer's zero substitution. Only known operations are accepted.
    Calibration ENTER/START generation is deliberately absent. STOP with
    nonzero fields is representable for diagnostics and receives a decoder
    warning; callers wanting the canonical STOP should use the defaults.
    """

    operation_value = _integer(operation, "operation", 0, 255)
    try:
        Operation(operation_value)
    except ValueError as exc:
        raise FrameError("Unknown or unverified operation.", "operation") from exc
    speed_value = _integer(speed, "speed", 0, 10)
    temperature = _integer(temperature_level, "temperature_level", 0, 19)
    android_direction = _integer(direction, "direction", 0, 1)
    if not isinstance(tare, bool):
        raise FrameError("tare must be a boolean.", "field_type")
    frame = bytearray((0x55, 15, 0xA1, operation_value, 0xA9 if tare else 0,
                       speed_value, temperature, 0, 0, 0, 0,
                       1 - android_direction, 0))
    frame.extend((checksum(frame), 0xAA))
    return bytes(frame)


def encode_calibration(command: str) -> bytes:
    """Observed ENTER/START layout; EXIT is a normal STOP with calibration zero."""
    if command not in ("enter", "start", "exit"):
        raise FrameError("calibration must be enter, start or exit", "calibration")
    frame = bytearray(encode_tx())
    frame[12] = {"enter": 0xE6, "start": 0xE9, "exit": 0}[command]
    frame[13] = checksum(frame[:13])
    return bytes(frame)


def actual_speed_level(rpm: int) -> int:
    """Map measured RPM to the application bins; these are not target RPMs."""

    if isinstance(rpm, bool) or not isinstance(rpm, int):
        raise FrameError("rpm must be an integer.", "field_type")
    if rpm <= 0:
        return 0
    for level, upper in enumerate(
        (558, 1008, 1437, 3359, 6349, 9309, 12312, 15315, 18232), start=1
    ):
        if rpm <= upper:
            return level
    return 10


@dataclass(frozen=True, slots=True)
class TxFrame:
    raw: bytes
    operation: int
    tare: bool
    tare_raw: int
    speed_level: int
    temperature_level: int
    reserved: tuple[int, ...]
    wire_direction: int
    direction: Direction | None
    calibration: int
    warnings: tuple[str, ...]
    kind: ClassVar[str] = "TX"

    @property
    def operation_name(self) -> str:
        try:
            return Operation(self.operation).name
        except ValueError:
            return "UNKNOWN"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind, "raw_hex": self.raw.hex(" ").upper(),
            "size": len(self.raw), "operation": self.operation,
            "operation_name": self.operation_name, "tare": self.tare,
            "tare_raw": self.tare_raw, "speed_level": self.speed_level,
            "temperature_level": self.temperature_level,
            "temperature_celsius": (
                TEMPERATURE_LEVELS[self.temperature_level]
                if self.temperature_level < len(TEMPERATURE_LEVELS) else None
            ),
            "reserved": list(self.reserved), "wire_direction": self.wire_direction,
            "direction": int(self.direction) if self.direction is not None else None,
            "direction_name": self.direction.name if self.direction is not None else None,
            "calibration": self.calibration,
            "calibration_name": _CALIBRATION_NAMES.get(self.calibration, "unknown"),
            "checksum": self.raw[13], "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class RxFrame:
    raw: bytes
    status: int
    motor_heater_state: int
    motor_on: bool
    heater_on: bool
    scale_stable: bool
    direction: Direction
    error_detected: bool
    above_target_temperature: bool
    bowl_ntc_detected: bool
    lid_open: bool
    extended_state: int
    error_code: int
    android_error_code: int
    target_speed_level: int
    target_rpm: int
    actual_rpm: int
    target_temperature_level: int
    target_temperature: int
    actual_temperature: int
    weight: int
    firmware_version: int
    scale_state_raw: int
    scale_state: str
    calibration_step: int
    unknown_byte_24: int
    warnings: tuple[str, ...]
    kind: ClassVar[str] = "RX"

    @property
    def actual_speed_level(self) -> int:
        return actual_speed_level(self.actual_rpm)

    @property
    def target_speed_level_signed(self) -> int:
        """Original Android signed-byte widening, including malformed levels."""

        return self.target_speed_level if self.target_speed_level < 128 else self.target_speed_level - 256

    @property
    def target_temperature_level_signed(self) -> int:
        """Original Android signed-byte widening, including malformed levels."""

        return self.target_temperature_level if self.target_temperature_level < 128 else self.target_temperature_level - 256

    @property
    def android_scale_state(self) -> str:
        """Application interpretation, including its no-known-flags fallback."""

        return "overload" if self.scale_state == "not_available" else self.scale_state

    @property
    def unknown_byte_24_signed(self) -> int:
        """The original signed-byte widening; its meaning remains unknown."""

        return self.unknown_byte_24 if self.unknown_byte_24 < 128 else self.unknown_byte_24 - 256

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind, "raw_hex": self.raw.hex(" ").upper(),
            "size": len(self.raw), "status": self.status,
            "motor_heater_state": self.motor_heater_state,
            "motor_on": self.motor_on, "heater_on": self.heater_on,
            "scale_stable": self.scale_stable, "direction": int(self.direction),
            "direction_name": self.direction.name,
            "error_detected": self.error_detected, "error_code": self.error_code,
            "error_name": (
                _ERROR_NAMES.get(self.error_code, "undefined")
                if self.error_detected else "none"
            ),
            "error_description": ERROR_DESCRIPTIONS.get(self.error_code, "Undefined controller fault") if self.error_detected else "No controller error",
            "android_error_code": self.android_error_code,
            "above_target_temperature": self.above_target_temperature,
            "bowl_ntc_detected": self.bowl_ntc_detected, "lid_open": self.lid_open,
            "extended_state": self.extended_state,
            "extended_state_name": _EXTENDED_STATES.get(self.extended_state, "undefined"),
            "target_speed_level": self.target_speed_level,
            "target_speed_level_signed": self.target_speed_level_signed,
            "target_rpm": self.target_rpm,
            "actual_rpm": self.actual_rpm, "actual_speed_level": self.actual_speed_level,
            "target_temperature_level": self.target_temperature_level,
            "target_temperature_level_signed": self.target_temperature_level_signed,
            "target_temperature": self.target_temperature,
            "actual_temperature": self.actual_temperature, "weight": self.weight,
            "firmware_version": self.firmware_version,
            "scale_state_raw": self.scale_state_raw, "scale_state": self.scale_state,
            "android_scale_state": self.android_scale_state,
            "calibration_step": self.calibration_step,
            "calibration_step_name": _CALIBRATION_STEPS.get(self.calibration_step, "not_available"),
            "unknown_byte_24": self.unknown_byte_24,
            "unknown_byte_24_signed": self.unknown_byte_24_signed, "checksum": self.raw[25],
            "warnings": list(self.warnings),
        }


def _decode_tx(raw: bytes) -> TxFrame:
    warnings: list[str] = []
    if raw[3] not in Operation._value2member_map_:
        warnings.append(f"Unknown or unverified operation 0x{raw[3]:02X}.")
    if raw[4] not in (0, 0xA9):
        warnings.append(f"Unrecognized tare byte 0x{raw[4]:02X}.")
    if raw[5] > 10:
        warnings.append("Speed level exceeds the documented range 0..10.")
    if raw[6] > 19:
        warnings.append("Temperature level exceeds the documented range 0..19.")
    if any(raw[7:11]):
        warnings.append("Reserved offsets 7..10 are not all zero.")
    direction = Direction(1 - raw[11]) if raw[11] in (0, 1) else None
    if direction is None:
        warnings.append(f"Unrecognized wire direction 0x{raw[11]:02X}.")
    if raw[12] not in _CALIBRATION_NAMES:
        warnings.append(f"Unrecognized calibration byte 0x{raw[12]:02X}.")
    elif raw[12] in (230, 233) and any(raw[3:12]):
        warnings.append("Calibration ENTER/START normally zero offsets 3..11.")
    if raw[3] == 0 and (raw[5] or raw[6]):
        warnings.append("STOP contains nonzero speed or temperature fields.")
    return TxFrame(raw, raw[3], raw[4] == 0xA9, raw[4], raw[5], raw[6],
                   tuple(raw[7:11]), raw[11], direction, raw[12], tuple(warnings))


def _decode_rx(raw: bytes) -> RxFrame:
    status = raw[3]
    state = status & 3
    error_detected = bool(status & 0x10)
    warnings: list[str] = []
    if raw[6] > 10:
        warnings.append("Target speed level exceeds the documented range 0..10.")
    if raw[11] > 19:
        warnings.append("Target temperature level exceeds the documented range 0..19.")
    if raw[4] not in (0, 3, 4, 5):
        warnings.append(f"Uninterpreted extended state 0x{raw[4]:02X}.")
    if error_detected and raw[5] not in _ERROR_TO_ANDROID:
        warnings.append(f"Unmapped board error 0x{raw[5]:02X}; Android maps it to 6.")
    elif not error_detected and raw[5]:
        warnings.append("Error byte is nonzero while the error flag is clear.")
    if raw[22] & ~7:
        warnings.append("Scale-state byte contains undocumented high bits.")
    if not raw[22] & 7:
        warnings.append("No known scale-state flags; Android falls back to overload.")
    if raw[23] not in _CALIBRATION_STEPS:
        warnings.append(f"Uninterpreted calibration step 0x{raw[23]:02X}.")
    scale_state = (
        "overload" if raw[22] & 4 else "calibration" if raw[22] & 1
        else "normal" if raw[22] & 2 else "not_available"
    )
    return RxFrame(
        raw=raw, status=status, motor_heater_state=state,
        motor_on=state in (1, 3), heater_on=state in (1, 2),
        scale_stable=bool(status & 4),
        direction=Direction.CLOCKWISE if status & 8 else Direction.COUNTER_CLOCKWISE,
        error_detected=error_detected,
        above_target_temperature=bool(status & 0x20),
        bowl_ntc_detected=bool(status & 0x40), lid_open=bool(status & 0x80),
        extended_state=raw[4], error_code=raw[5],
        android_error_code=_ERROR_TO_ANDROID.get(raw[5], 6) if error_detected else 0,
        target_speed_level=raw[6], target_rpm=int.from_bytes(raw[7:9], "big"),
        actual_rpm=int.from_bytes(raw[9:11], "big"), target_temperature_level=raw[11],
        target_temperature=int.from_bytes(raw[12:14], "big"),
        actual_temperature=int.from_bytes(raw[14:16], "big"),
        weight=int.from_bytes(raw[16:20], "big", signed=True),
        firmware_version=int.from_bytes(raw[20:22], "big"),
        scale_state_raw=raw[22], scale_state=scale_state, calibration_step=raw[23],
        unknown_byte_24=raw[24], warnings=tuple(warnings),
    )


def decode_frame(data: bytes | str) -> TxFrame | RxFrame:
    """Validate one complete frame and decode every documented field.

    Unknown semantic values are preserved with warnings. Header, exact size,
    type byte, terminator and checksum errors are structural and are rejected.
    """

    if isinstance(data, str):
        raw = parse_hex(data)
    elif isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
    else:
        raise FrameError("Frame input must be bytes or hexadecimal text.", "input_type")
    if len(raw) not in (15, 27):
        raise FrameError(f"Expected exactly 15 or 27 bytes; received {len(raw)}.", "length")
    if raw[0] != 0x55:
        raise FrameError("Frame must begin with 0x55.", "header")
    if raw[1] != len(raw):
        raise FrameError("Length byte does not match the frame size.", "length_byte")
    expected_type = 0xA1 if len(raw) == 15 else 0xB1
    if raw[2] != expected_type:
        raise FrameError(f"Expected type byte 0x{expected_type:02X}.", "type")
    if raw[-1] != 0xAA:
        raise FrameError("Frame must end with 0xAA.", "terminator")
    expected_checksum = checksum(raw[:-2])
    if raw[-2] != expected_checksum:
        raise FrameError(
            f"Checksum mismatch: received 0x{raw[-2]:02X}, expected 0x{expected_checksum:02X}.",
            "checksum",
        )
    return _decode_tx(raw) if len(raw) == 15 else _decode_rx(raw)
