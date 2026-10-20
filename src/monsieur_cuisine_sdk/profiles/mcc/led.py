"""Front LED behavior of the build-292 host app as a pure, time-based model (STATIC evidence).

The app writes three sysfs brightness nodes (red, green, blue). "White" lights
only the blue node at 50. Modes: solid, blink (500 ms on/off starting on),
pulse (brightness times a 100-step raised-cosine curve, 30 ms per step) and
off; a request may revert to solid white after a timeout. This model keeps the
same numbers but writes nothing anywhere.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

WHITE = (0, 0, 50)
GREEN = (0, 60, 0)
RED = (75, 0, 0)
OFF = (0, 0, 0)
BLINK_MS = 500
PULSE_STEP_MS = 30
PULSE_STEPS = 100
PULSE_CURVE = tuple((math.cos(i * 2 / PULSE_STEPS * math.pi) + 1.0) * 0.5 for i in range(PULSE_STEPS))
MODES = ("solid", "blink", "pulse", "off")


def pulse_rgb(colour, elapsed_ms: int):
    """Channels during a pulse: the app advances the curve index before each write."""
    index = (elapsed_ms // PULSE_STEP_MS + 1) % PULSE_STEPS
    factor = PULSE_CURVE[index]
    return tuple(int(channel * factor) for channel in colour)


def blink_rgb(colour, elapsed_ms: int):
    return colour if (elapsed_ms // BLINK_MS) % 2 == 0 else OFF


@dataclass(frozen=True)
class LedRequest:
    at_ms: int
    mode: str
    colour: tuple
    timeout_ms: int | None = None


@dataclass
class LedModel:
    """Requests in virtual time; ``rgb_at`` reproduces what the nodes would hold."""
    requests: list = field(default_factory=list)

    def request(self, at_ms: int, mode: str, colour=WHITE, *, timeout_ms: int | None = None):
        if mode not in MODES:
            raise ValueError(f"unknown LED mode {mode!r}")
        if type(at_ms) is not int or at_ms < 0 or (self.requests and at_ms < self.requests[-1].at_ms):
            raise ValueError("LED requests must be in nondecreasing virtual time")
        if timeout_ms is not None and (type(timeout_ms) is not int or timeout_ms < 0):
            raise ValueError("timeout_ms must be a nonnegative integer")
        colour = tuple(colour)
        if len(colour) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in colour):
            raise ValueError("colour must be three integer channels 0..255")
        self.requests.append(LedRequest(at_ms, mode, colour if mode != "off" else OFF, timeout_ms))

    def solid(self, at_ms, colour=WHITE):
        self.request(at_ms, "solid", colour)

    def pulse(self, at_ms, colour=WHITE):
        self.request(at_ms, "pulse", colour)

    def blink(self, at_ms, colour, timeout_ms=None):
        self.request(at_ms, "blink", colour, timeout_ms=timeout_ms)

    def off(self, at_ms):
        self.request(at_ms, "off")

    def active(self, t_ms: int) -> LedRequest | None:
        current = None
        for item in self.requests:
            if item.at_ms <= t_ms:
                current = item
        if current is not None and current.timeout_ms is not None and t_ms >= current.at_ms + current.timeout_ms:
            return LedRequest(current.at_ms + current.timeout_ms, "solid", WHITE)
        return current

    def rgb_at(self, t_ms: int):
        item = self.active(t_ms)
        if item is None:
            return OFF
        elapsed = t_ms - item.at_ms
        if item.mode == "solid":
            return item.colour
        if item.mode == "blink":
            return blink_rgb(item.colour, elapsed)
        if item.mode == "pulse":
            return pulse_rgb(item.colour, elapsed)
        return OFF

    def is_off(self, t_ms: int) -> bool:
        return all(channel == 0 for channel in self.rgb_at(t_ms))
