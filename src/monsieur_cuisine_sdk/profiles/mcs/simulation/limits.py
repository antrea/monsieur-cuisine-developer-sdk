"""Local input budgets; host policies, never appliance limits."""
import math

MAX_TICKS = 1_000_000
MAX_ACTIONS = 100_000
MAX_SAMPLES = 100_000
MAX_PENDING = 1024
MAX_RECORD_BYTES = 32 * 1024 * 1024


class SimulationCancelled(ValueError):
    """A caller cancelled a bounded simulation job."""


def seconds_ns(value, *, name='seconds'):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1_000_000_000:
        raise ValueError(f'{name} must be finite and in 0..1000000000')
    return round(value * 1_000_000_000)


def check_work(total_ns, tick_ns):
    if total_ns // tick_ns > MAX_TICKS:
        raise ValueError(f'simulation exceeds {MAX_TICKS} tick work budget')
