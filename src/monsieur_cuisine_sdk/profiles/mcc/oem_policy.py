"""Host-side rules of the OEM MCC app (de.silpion.mc2 build 292), above the wire codec.

These are what the original app enforces before it latches a command, read from
its code and checked by executing its own bytecode (see
``fixtures/oem/mcc_292_vectors.jsonl``). The power-board firmware may
enforce more or less: nothing here is a firmware fact or a certified interlock.

The functions are pure; :class:`HostPolicy` applies them to a requested command.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .protocol.codec import Direction, Operation, TEMPERATURE_LEVELS

SPEED_MAX = 10
SPEED_MAX_HEATER_ON = 3
SPEED_MAX_REVERSE = 3
SPEED_KNEADING_MAX_REVERSE = 4
SPEED_DEFAULT = 1
SPEED_STIRRER_WARNING = 5
MAX_TEMPERATURE = 130
TIME_MAX_MS = 5_940_000
TIME_MAX_FAST_MS = 900_000
FAST_SPEED_ABOVE = 6
HOT_SPEED_LEVEL = 4
HOT_SPEED_TEMPERATURE = 60
TURBO_MAX_TEMPERATURE = 60
TURBO_MAX_TARGET_LEVEL = 5
TURBO_FIRST_TICK_MS = 100
TURBO_TICK_MS = 1000
TURBO_WARNING_S = 8
TURBO_MAX_S = 600
PAUSE_AUTO_STOP_MS = 30_000
SEND_PERIOD_MS = 100
RX_READ_PERIOD_MS = 500
IDLE_SLEEP_S = 420
SLEEP_COUNTDOWN_S = 30
TURBO_COMMAND = (Operation.TURBO, SPEED_MAX, Direction.CLOCKWISE, 0)

# Recipe binning (CookingUtils): inclusive Celsius ranges per level; 1..29 °C match no range -> level 0.
_RECIPE_RANGES = ((None, 0), (30, 37), (38, 45), (46, 50), (51, 55), (56, 60), (61, 65), (66, 70), (71, 75),
                  (76, 80), (81, 85), (86, 90), (91, 95), (96, 100), (101, 105), (106, 110), (111, 115),
                  (116, 120), (121, 125), (126, 130), (131, None))


def recipe_temperature_level(celsius: int) -> int:
    """Level the app derives from a recipe temperature (5 °C bands rounded up; 1-29 °C means no heat)."""
    _require_int("celsius", celsius)
    for level, (low, high) in enumerate(_RECIPE_RANGES):
        if (low is None or celsius >= low) and (high is None or celsius <= high):
            return min(level, len(_RECIPE_RANGES) - 2)
    return 0


def recipe_level_celsius(level: int) -> int:
    """Celsius the app shows for a recipe level; out-of-range levels clamp like the original."""
    _require_int("level", level)
    if level < 0:
        return 0
    return TEMPERATURE_LEVELS[min(level, len(TEMPERATURE_LEVELS) - 1)]


def knob_temperature_level(celsius: int) -> int:
    """Level the temperature knob selects for a Celsius value: first table value >= celsius, else the maximum."""
    _require_int("celsius", celsius)
    for level, value in enumerate(TEMPERATURE_LEVELS):
        if celsius <= value:
            return level
    return len(TEMPERATURE_LEVELS) - 1


def knob_level_celsius(level: int) -> int:
    """Celsius for a knob level; the app returns 0 for levels outside 0..19."""
    _require_int("level", level)
    return TEMPERATURE_LEVELS[level] if 0 <= level < len(TEMPERATURE_LEVELS) else 0


def max_time_ms(speed: int) -> int:
    """Longest session the app allows at a speed level (15 min above level 6, else 99 min)."""
    _require_int("speed", speed)
    return TIME_MAX_FAST_MS if speed > FAST_SPEED_ABOVE else TIME_MAX_MS


def speed_cap(temperature_level: int, direction: Direction, operation: Operation) -> int:
    """Maximum speed the app lets the user select for the other settings."""
    if temperature_level > 0:
        return SPEED_MAX_HEATER_ON
    if direction == Direction.CLOCKWISE:
        return SPEED_MAX
    return SPEED_KNEADING_MAX_REVERSE if operation == Operation.KNEAD else SPEED_MAX_REVERSE


def _require_int(name, value):
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")


@dataclass(frozen=True)
class PolicyDecision:
    operation: Operation
    speed: int
    direction: Direction
    temperature_level: int
    adjustments: tuple[str, ...] = ()
    refusals: tuple[str, ...] = ()
    confirmations: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.refusals


@dataclass
class HostPolicy:
    """Apply the app's command rules. ``mode`` is "oem" (clamp like the app) or "strict" (refuse instead)."""

    mode: str = "oem"
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.mode not in ("oem", "strict"):
            raise ValueError("policy mode must be 'oem' or 'strict'")

    def start(self, operation: Operation, speed: int, direction: Direction, temperature_level: int, *,
              measured_temperature: int | None = None, lid_open: bool | None = None, error_code: int = 0,
              hot_speed_confirmed: bool = False, knead_rest: bool = False) -> PolicyDecision:
        """Decide what the app would latch for a start/resume request (``CookingManager.i()`` then ``a()``)."""
        operation, direction = Operation(operation), Direction(direction)
        adjustments, refusals, confirmations = [], [], []
        if operation in (Operation.STOP, Operation.SLEEP):
            return PolicyDecision(operation, 0, direction, 0)
        if operation == Operation.TURBO:
            return self._turbo(speed, direction, temperature_level, measured_temperature, lid_open, error_code)
        if lid_open:
            refusals.append("lid not closed: the app pauses instead of starting")
        if error_code:
            refusals.append(f"board error {error_code} active: the app pauses instead of starting")
        cap = speed_cap(temperature_level, direction, operation)
        if speed > cap:
            if self.mode == "strict":
                refusals.append(f"speed {speed} above the app limit {cap} for these settings")
            else:
                adjustments.append(f"speed {speed} -> {cap} (app limit for these settings)")
                speed = cap
        if speed == 0 and operation not in (Operation.STEAM, Operation.TOAST) and not (
                operation == Operation.KNEAD and knead_rest):
            if self.mode == "strict":
                refusals.append("the app never runs this operation at speed 0")
            else:
                adjustments.append(f"speed 0 -> {SPEED_DEFAULT} (app minimum)")
                speed = SPEED_DEFAULT
        if (measured_temperature is not None and measured_temperature >= HOT_SPEED_TEMPERATURE
                and speed >= HOT_SPEED_LEVEL and not hot_speed_confirmed):
            confirmations.append(f"speed >= {HOT_SPEED_LEVEL} at >= {HOT_SPEED_TEMPERATURE} °C needs confirmation")
        return PolicyDecision(operation, speed, direction, temperature_level, tuple(adjustments), tuple(refusals),
                              tuple(confirmations))

    def _turbo(self, speed, direction, temperature_level, measured, lid_open, error_code) -> PolicyDecision:
        refusals, adjustments = [], []
        if lid_open or lid_open is None:
            refusals.append("turbo needs a closed lid")
        if measured is None or measured >= TURBO_MAX_TEMPERATURE:
            refusals.append(f"turbo needs a measured temperature below {TURBO_MAX_TEMPERATURE} °C")
        if temperature_level >= TURBO_MAX_TARGET_LEVEL:
            refusals.append(f"turbo needs a target level below {TURBO_MAX_TARGET_LEVEL}")
        if direction != Direction.CLOCKWISE:
            refusals.append("turbo runs clockwise only")
        if error_code:
            refusals.append(f"board error {error_code} active")
        if (speed, temperature_level) != (SPEED_MAX, 0):
            adjustments.append("turbo is always sent as speed 10, clockwise, no heat")
        return PolicyDecision(*TURBO_COMMAND, tuple(adjustments), tuple(refusals))
