"""Explicit-profile framing, including rejection of fully framed foreign input.

Both envelope validators are used to fence foreign frames, never to switch the
selected model. A valid foreign envelope is discarded as one unit, so an MCC
command embedded inside an MCS OTA packet cannot actuate the MCC model.

Resynchronization: 0xAA is both the MCS header and the MCC terminator, and 0x55
is the MCC header. An apparent MCS header whose length bytes contain either
header byte is the signature of a desynchronized stream (for example an MCC
terminator followed by the next "55 0F" frame), never a documented MCS frame
size, so it is dropped as one noise byte instead of opening a quarantine. MCC
candidates are also rejected as soon as their type byte disagrees with their
length byte, so a stray "55 0F" cannot swallow the following valid frame.
"""
from collections import deque

# Header bytes of either profile; never part of a documented MCS length field.
_HEADER_BYTES = (0x55, 0xAA)


class SelectedStream:
    def __init__(self, model: str, *, max_frame: int = 4096):
        if model not in ("mcc", "mcs"):
            raise ValueError("explicit model must be mcc or mcs")
        if type(max_frame) is not int or not 269 <= max_frame <= 65536:
            raise ValueError("max_frame must be 269..65536")
        self.model, self.max_frame = model, max_frame
        self.buffer = bytearray()
        self.discard_remaining = 0
        self.issues = deque(maxlen=128)
        self.rejected = 0

    def reset(self):
        self.buffer.clear()
        self.discard_remaining = 0

    def _issue(self, reason, count):
        self.rejected += 1
        self.issues.append({"reason": reason, "bytes": count})

    @staticmethod
    def _validate(raw, protocol):
        if protocol == "mcc":
            from .profiles.mcc.protocol.codec import decode_frame
            decode_frame(raw)
        else:
            from .profiles.mcs.protocol import parse_frame
            parse_frame(raw)

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("stream input must be bytes")
        if len(data) > 65536:
            raise ValueError("one input chunk must be <=65536 bytes")
        frames = []
        # Incremental bounded buffer; a 64k chunk is never retained wholesale.
        for value in bytes(data):
            if self.discard_remaining:
                self.discard_remaining -= 1
                if not self.discard_remaining:
                    self.buffer.clear()
                continue
            self.buffer.append(value)
            while self.buffer:
                head = self.buffer[0]
                if head == 0x55:
                    protocol = "mcc"
                    if len(self.buffer) < 2:
                        break
                    size = self.buffer[1]
                    if size not in (15, 27):
                        self._issue("MCC length", 1); del self.buffer[0]; continue
                    if len(self.buffer) < 3:
                        break
                    if self.buffer[2] != (0xA1 if size == 15 else 0xB1):
                        self._issue("MCC type", 1); del self.buffer[0]; continue
                elif head == 0xAA:
                    protocol = "mcs"
                    if len(self.buffer) < 3:
                        break
                    if self.buffer[1] in _HEADER_BYTES or self.buffer[2] in _HEADER_BYTES:
                        self._issue("ambiguous AA resynchronized", 1); del self.buffer[0]; continue
                    size = int.from_bytes(self.buffer[1:3], "big") + 1
                    if size > self.max_frame:
                        # Quarantine the entire declared envelope, even beyond
                        # our allocation bound. Keep only its three-byte header
                        # and a counter so transport timeout still sees a partial
                        # frame. Never rescan an oversized payload for commands.
                        self._issue("oversize MCS envelope quarantined", size)
                        self.discard_remaining = size - len(self.buffer)
                        break
                    if size < 10:
                        self._issue("MCS length", 1); del self.buffer[0]; continue
                else:
                    self._issue("noise", 1); del self.buffer[0]; continue
                if len(self.buffer) < size:
                    break
                raw = bytes(self.buffer[:size])
                if protocol != self.model:
                    # Foreign framing is quarantined even when its checksum is
                    # damaged. Scanning its payload could otherwise execute an
                    # embedded local-protocol command after a one-byte reject.
                    del self.buffer[:size]
                    self._issue("foreign protocol quarantined", size)
                    continue
                try:
                    self._validate(raw, protocol)
                except ValueError:
                    # A complete declared envelope is one rejected unit. Its
                    # payload/trailer must not become a new apparent header;
                    # this also preserves a following separate valid frame.
                    self._issue("invalid envelope quarantined", size)
                    del self.buffer[:size]
                    continue
                del self.buffer[:size]
                if protocol == "mcc" and size != 15:
                    self._issue("RX is not a command", size)
                else:
                    frames.append(raw)
        return frames
