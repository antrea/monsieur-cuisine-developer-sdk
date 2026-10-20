"""Cooking presets of the build-292 host app and their step selection rules (STATIC evidence).

A preset is data: either one step (manual), a cycling unit (kneading, roasting)
or a sequence of steps (steaming). The functions reproduce how the app picks
the active sub-step at each one-second timer tick and how it rewrites the
kneading rest phase. Nothing here is controller firmware behavior; durations
and limits are the app's own values.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .protocol.codec import Direction, Operation

# Host work modes (IPC WorkMode) to wire operations.
WORK_MODES = {0: Operation.STOP, 1: Operation.STANDARD, 2: Operation.TURBO, 3: Operation.STEAM,
              4: Operation.TOAST, 5: Operation.KNEAD, 6: Operation.SLEEP}
LEFT, RIGHT = 0, 1          # IPC Direction: 0 LEFT (reverse, CCW), 1 RIGHT (CW)
KNEADING_MAX_MS = 120_000
KNEADING_REST_THRESHOLD_MS = 85_000
KNEADING_REST_MIN_MS = 1_000
TICK_MS = 1_000


@dataclass(frozen=True)
class MachineConfiguration:
    work_mode: int
    speed: int
    direction: int
    temperature_level: int

    @property
    def operation(self) -> Operation:
        return WORK_MODES[self.work_mode]

    @property
    def wire_direction(self) -> Direction:
        return Direction.CLOCKWISE if self.direction == RIGHT else Direction.COUNTER_CLOCKWISE


@dataclass(frozen=True)
class CookingStep:
    """One SingleCookingStep: a configuration, a duration and the knobs the app leaves editable."""
    duration_ms: int
    configuration: MachineConfiguration
    description: str = ""
    speed_limit: int = 10
    time_limit_ms: int = -1
    turbo_enabled: bool = True
    direction_modifiable: bool = True
    time_knob: bool = True
    speed_knob: bool = True
    temperature_knob: bool = True
    scale_enabled: bool = True
    rest: bool = False       # customInfo "rest phase": exempt from the minimum-speed rule
    preheat: bool = False


@dataclass(frozen=True)
class CookingUnit:
    """A cycle of sub-steps repeated for ``duration_ms`` (kneading, roasting)."""
    duration_ms: int
    limit_ms: int
    steps: tuple[CookingStep, ...]
    tag: str

    @property
    def cycle_ms(self) -> int:
        return sum(step.duration_ms for step in self.steps)


@dataclass(frozen=True)
class CookingSteps:
    """Consecutive steps, each with its own countdown (steaming, guided ramps)."""
    steps: tuple[CookingStep, ...]


def manual_default() -> CookingStep:
    return CookingStep(0, MachineConfiguration(1, 0, RIGHT, 0), "manual")


def kneading_unit() -> CookingUnit:
    locked = dict(turbo_enabled=False, direction_modifiable=False, speed_knob=False, temperature_knob=False,
                  time_limit_ms=KNEADING_MAX_MS, description="kneading")
    return CookingUnit(45_000, KNEADING_MAX_MS, (
        CookingStep(15_000, MachineConfiguration(5, 4, LEFT, 0), speed_limit=4, **locked),
        CookingStep(KNEADING_REST_MIN_MS, MachineConfiguration(5, 0, LEFT, 0), speed_limit=0, rest=True, **locked),
        CookingStep(104_000, MachineConfiguration(5, 4, RIGHT, 0), speed_limit=4, **locked)), "KNEADING")


def roasting_unit() -> CookingUnit:
    locked = dict(turbo_enabled=False, direction_modifiable=False, speed_knob=False, speed_limit=-1)
    return CookingUnit(420_000, 840_000, (
        CookingStep(5_000, MachineConfiguration(4, 1, LEFT, 19), "roasting", **locked),
        CookingStep(30_000, MachineConfiguration(4, 0, LEFT, 19), "heating up", **locked)), "ROASTING")


def steaming_steps() -> CookingSteps:
    locked = dict(turbo_enabled=False, direction_modifiable=False, speed_knob=False, temperature_knob=False,
                  speed_limit=-1, description="steaming")
    return CookingSteps((
        CookingStep(600_000, MachineConfiguration(3, 1, RIGHT, 17), time_limit_ms=600_000, preheat=True, **locked),
        CookingStep(1_200_000, MachineConfiguration(3, 1, RIGHT, 17), time_limit_ms=3_600_000, **locked)))


PRESETS = {"manual": manual_default, "kneading": kneading_unit, "roasting": roasting_unit, "steaming": steaming_steps}


def preset(name: str):
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; choose one of {', '.join(PRESETS)}")
    return PRESETS[name]()


def knead_rest_ms(unit_duration_ms: int) -> int:
    """Rest phase the app writes into kneading step 1 for the session duration."""
    if type(unit_duration_ms) is not int or unit_duration_ms < 0:
        raise ValueError("duration must be a nonnegative integer of milliseconds")
    return unit_duration_ms - KNEADING_REST_THRESHOLD_MS if unit_duration_ms > KNEADING_REST_THRESHOLD_MS \
        else KNEADING_REST_MIN_MS


def with_rest(unit: CookingUnit, duration_ms: int) -> CookingUnit:
    """Kneading unit with its rest step rewritten as the app does during validation."""
    if unit.tag != "KNEADING" or len(unit.steps) < 2:
        return unit
    steps = list(unit.steps)
    steps[1] = replace(steps[1], duration_ms=knead_rest_ms(duration_ms))
    return replace(unit, steps=tuple(steps))


def active_step_index(unit: CookingUnit, elapsed_ms: int) -> int | None:
    """Sub-step the app selects at a timer tick with ``elapsed_ms`` run time.

    The app compares ``elapsed mod cycle`` with cumulative durations using
    ``<=``, so each sub-step boundary is reached one tick later than its
    nominal duration. None means the app found no step (never for a sane unit).
    """
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError("elapsed_ms must be a nonnegative integer")
    cycle = unit.cycle_ms
    if cycle <= 0:
        return None
    rest = elapsed_ms % cycle
    cumulative = 0
    for index, step in enumerate(unit.steps):
        if rest <= step.duration_ms + cumulative:
            return index
        cumulative += step.duration_ms
    return None


def unit_schedule(unit: CookingUnit, duration_ms: int, *, tick_ms: int = TICK_MS) -> list[tuple[int, int]]:
    """[(elapsed_ms, step index)] at every tick where the active sub-step changes, starting at 0."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("duration_ms must be a positive integer")
    unit = with_rest(unit, duration_ms)
    schedule, current = [(0, 0)], 0
    for elapsed in range(tick_ms, duration_ms + 1, tick_ms):
        index = active_step_index(unit, elapsed)
        if index is not None and index != current:
            schedule.append((elapsed, index))
            current = index
    return schedule
