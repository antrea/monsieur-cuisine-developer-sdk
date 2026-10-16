"""Injectable development adapter that uses only an in-memory board model.

This is an original application seam, not a drop-in Android Binder replacement.
It contains no ADB, serial device, network connection, or APK modification.
"""

from __future__ import annotations

import threading

from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, Operation, encode_tx

from .model import PowerBoardModel


class MockPowerBoardAdapter:
    """Expose start/stop and telemetry through an independent memory model.

    All operations use ``model_lock``; callers sharing this model with another
    component must also share its lock or serialize access externally. Command
    results are synthetic RX bytes, never hardware acknowledgements. Time only
    advances through ``advance``; stopping preserves finite model deceleration.
    """

    def __init__(self, model: PowerBoardModel | None = None) -> None:
        self.model = model if model is not None else PowerBoardModel()
        self.model_lock = threading.RLock()

    def start(
        self, speed: int, direction: Direction = Direction.COUNTER_CLOCKWISE,
        temperature_level: int = 0, operation: Operation | int = Operation.STANDARD,
    ) -> list[bytes]:
        """Encode documented setpoints and feed them to the memory model.

        Low-level frame validity is distinct from application safety policy;
        this adapter does not invent appliance interlocks or a cooking UI.
        """

        raw = encode_tx(operation, speed=speed, direction=direction,
                        temperature_level=temperature_level)
        return self.feed(raw)

    def stop(self) -> list[bytes]:
        """Request a synthetic STOP without forcing measured RPM to zero."""

        with self.model_lock:
            direction = self.model.controller.direction
            return self.model.feed(encode_tx(Operation.STOP, direction=direction))

    def feed(self, raw: bytes) -> list[bytes]:
        """Feed raw synthetic bytes, supporting fragments and corruption tests."""

        with self.model_lock:
            return self.model.feed(raw)

    def advance(self, delta_ms: int) -> list[bytes]:
        with self.model_lock:
            return self.model.advance(delta_ms)

    def sample(self) -> list[bytes]:
        with self.model_lock:
            return self.model.sample()

    def snapshot(self) -> dict[str, object]:
        with self.model_lock:
            return self.model.snapshot()

    def set_sensors(self, **changes: object) -> None:
        with self.model_lock:
            self.model.set_sensors(**changes)

    def set_faults(self, **changes: object) -> None:
        with self.model_lock:
            self.model.set_faults(**changes)

    def configure(self, **changes: object) -> None:
        with self.model_lock:
            self.model.configure(**changes)
