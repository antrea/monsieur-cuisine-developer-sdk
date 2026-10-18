"""Offline explicit-profile SDK. Import never loads Tk or starts networking."""
from .api import DeviceModel, DigitalTwin, TwinState, replay, RecordingLimitError, OwnershipError

__version__ = "2.0.0.dev0"
__all__ = ["DeviceModel", "DigitalTwin", "TwinState", "replay", "RecordingLimitError", "OwnershipError"]
