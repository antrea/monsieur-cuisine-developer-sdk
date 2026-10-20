"""Host IPC view of a PowerBoard frame and the change callbacks the build-292 service raises (STATIC).

The app service decodes the latest RX frame every 100 ms into a small sensor
holder, compares it with the previous one and raises Binder callbacks only
for changes. ``on_bad_state`` is edge-triggered: a persisting error is
reported once, and a cleared error raises nothing. Scale overload is the
app's own code 7, derived from the scale byte, not board error 7.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .protocol.codec import Direction, RxFrame

SCALE_NORMAL, SCALE_OVERLOAD, SCALE_CALIBRATION = 0, 1, 2
LID_OPEN, LID_CLOSED, LID_NA = 0, 1, 2
ERROR_SCALE_OVERLOAD = 7
_SCALE_STATES = {"normal": SCALE_NORMAL, "calibration": SCALE_CALIBRATION, "overload": SCALE_OVERLOAD}
_CALIBRATION = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 7: 6}
_MOTOR_HEATER = {0: (0, 0), 1: (1, 1), 2: (0, 1), 3: (1, 0)}


@dataclass(frozen=True)
class IpcSnapshot:
    """Sensor holder of the service: the values its callbacks carry."""
    motor: int = 0
    heater: int = 0
    direction: int = 0          # 1 RIGHT (CW), 0 LEFT
    speed_level: int = 0        # measured RPM binned to a level, not the target
    temperature: int = 0
    scale_state: int = SCALE_NORMAL
    weight: int = 0
    calibration_step: int = 0
    lid: int = LID_CLOSED
    error: int = 0              # IPC error code (board code mapped), 0 when the flag is clear

    @classmethod
    def from_frame(cls, frame: RxFrame) -> "IpcSnapshot":
        motor, heater = _MOTOR_HEATER[frame.motor_heater_state]
        return cls(motor, heater, 1 if frame.direction == Direction.CLOCKWISE else 0, frame.actual_speed_level,
                   frame.actual_temperature, _SCALE_STATES[frame.android_scale_state], frame.weight,
                   _CALIBRATION.get(frame.calibration_step, 7), LID_OPEN if frame.lid_open else LID_CLOSED,
                   frame.android_error_code)


DEFAULT_SNAPSHOT = IpcSnapshot()


def collect_warnings(snapshot: IpcSnapshot) -> list[int]:
    """Codes passed to ``on_bad_state``: app code 7 for scale overload, then the board-derived code."""
    if snapshot.error == 0:
        return [ERROR_SCALE_OVERLOAD] if snapshot.scale_state == SCALE_OVERLOAD else []
    return [ERROR_SCALE_OVERLOAD, snapshot.error] if snapshot.scale_state == SCALE_OVERLOAD else [snapshot.error]


def callbacks(previous: IpcSnapshot, current: IpcSnapshot) -> list[tuple]:
    """Callbacks the service raises when ``current`` replaces ``previous`` (name first, then arguments)."""
    out = []
    if (current.motor, current.direction, current.speed_level) != (previous.motor, previous.direction,
                                                                   previous.speed_level):
        out.append(("on_motor_state_changed", current.motor, current.direction, current.speed_level))
    if (current.scale_state, current.weight, current.calibration_step) != (
            previous.scale_state, previous.weight, previous.calibration_step):
        out.append(("on_scale_state_changed", current.scale_state, current.weight, current.calibration_step))
    if (current.heater, current.temperature) != (previous.heater, previous.temperature):
        out.append(("on_temperature_changed", current.temperature))
    if current.lid != previous.lid:
        out.append(("on_lid_opened" if current.lid == LID_OPEN else "on_lid_closed",))
    error_edge = current.error != previous.error and current.error != 0
    overload_edge = current.scale_state != previous.scale_state and current.scale_state == SCALE_OVERLOAD
    if error_edge or overload_edge:
        out.append(("on_bad_state", collect_warnings(current)))
    return out


def visible_warnings(codes, *, scale_view_visible: bool = False) -> list[int]:
    """Codes the main screen shows: 7 only while the scale view or a scale step is visible."""
    return [code for code in codes if code != ERROR_SCALE_OVERLOAD or scale_view_visible]


def rounded_weight(grams: int) -> int:
    """Weight as the scale knob shows it: nearest 5 g, Java ``Math.round`` half-up."""
    if type(grams) is not int:
        raise ValueError("grams must be an integer")
    return int(math.floor(grams / 5.0 + 0.5)) * 5


def weight_text(grams: int, *, overload: bool = False) -> str:
    return "----g" if overload else f"{rounded_weight(grams)}g"
