"""One explicit localhost TCP listener, one twin, one controller owner."""
from collections import deque
from dataclasses import dataclass
import ipaddress
import math
import socket
import time

from .api import DigitalTwin


@dataclass(frozen=True)
class ConnectionConfig:
    host: str = "127.0.0.1"
    port: int | None = None
    fragment_timeout: float = 2.0
    idle_timeout: float = 30.0
    max_output: int = 65536

    def __post_init__(self):
        host = "127.0.0.1" if self.host == "localhost" else self.host
        try:
            if not ipaddress.IPv4Address(host).is_loopback:
                raise ValueError("not loopback")
        except (ValueError, ipaddress.AddressValueError) as exc:
            raise ValueError("literal IPv4 loopback required; no wildcard/LAN exposure") from exc
        object.__setattr__(self, "host", host)
        if self.port is not None and (type(self.port) is not int or not 0 <= self.port <= 65535):
            raise ValueError("port must be None or integer0..65535")
        for value in (self.fragment_timeout, self.idle_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("timeouts must be finite positive seconds")
        if type(self.max_output) is not int or not 269 <= self.max_output <= 1048576:
            raise ValueError("output bound must be269..1048576")


class AndroidConnection:
    def __init__(self, twin: DigitalTwin, config: ConnectionConfig | None = None, *, clock=time.monotonic):
        self.twin, self.config, self.clock = twin, config or ConnectionConfig(), clock
        self.listener = self.client = None
        self.address = (self.config.host, self.config.port if self.config.port is not None else
                        8765 if twin.model.value == "mcc" else 8766)
        self._owner = None
        self._output = bytearray()
        self._sizes = deque()
        self._unsubscribe_rx = self._unsubscribe_switch = None
        self.generation = twin.generation
        self._last_input = self._last_activity = clock()
        self.tx_frames = self.rx_frames = self.rejected_clients = 0
        self.last_command = self.last_error = self.last_disconnect = None
        self._overflow = False

    def start(self):
        self.twin._check_thread()
        if self.listener:
            return self
        if self.generation != self.twin.generation:
            raise ValueError("old connection object cannot attach to a new model session")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(self.address); listener.listen(4); listener.setblocking(False)
        except BaseException:
            listener.close(); raise
        self.listener = listener
        self.address = (self.address[0], listener.getsockname()[1])
        self._unsubscribe_rx = self.twin.subscribe_rx(self._response)
        self._unsubscribe_switch = self.twin.before_switch(self.close)
        return self

    def _response(self, raw, generation):
        if self.client is None or generation != self.generation:
            return
        if len(self._output) + len(raw) > self.config.max_output:
            self._overflow = True; self.last_error = "output buffer limit"; return
        self._output.extend(raw); self._sizes.append(len(raw))

    def status(self):
        status = ("Connected" if self.client else "Disconnected" if self.listener and self.last_disconnect
                  else "Listening" if self.listener else "Disabled")
        return {"status": status, "listener": bool(self.listener), "address": self.address,
                "model": self.twin.model.value, "clients": int(self.client is not None),
                "owner": self.twin.owner, "tx_frames": self.tx_frames, "rx_frames": self.rx_frames,
                "last_command": self.last_command, "last_error": self.last_error,
                "last_disconnect": self.last_disconnect, "rejected_clients": self.rejected_clients,
                "pending_bytes": len(self._output), "generation": self.generation}

    def disconnect(self, reason="local disconnect"):
        self.twin._check_thread()
        client, self.client = self.client, None
        owner, self._owner = self._owner, None
        self._output.clear(); self._sizes.clear(); self._overflow = False
        if client is None:
            return
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client.close()
        self.twin.release(owner)
        self.twin.disarm()
        self.last_disconnect = reason

    def poll(self):
        self.twin._check_thread()
        if self.listener is None:
            return
        self._service()  # release an old EOF before accepting a rapid reconnect
        for _ in range(4):
            try:
                candidate, _ = self.listener.accept()
            except BlockingIOError:
                break
            if self.client is not None or self.twin.owner != "local":
                candidate.close(); self.rejected_clients += 1; continue
            candidate.setblocking(False)
            self.twin.disarm()
            self._owner = object(); self.twin.claim(self._owner)
            self.client = candidate
            self._last_activity = self._last_input = self.clock()
        self._service()

    def _service(self):
        if self.client is None:
            return
        now = self.clock()
        if self.twin.buffered_bytes and now - self._last_input >= self.config.fragment_timeout:
            self.last_error = "incomplete frame timeout"; self.disconnect("fragment timeout"); return
        if now - self._last_activity >= self.config.idle_timeout:
            self.last_error = "inactive connection timeout"; self.disconnect("idle timeout"); return
        try:
            data = self.client.recv(4096)
        except BlockingIOError:
            data = None
        except OSError as exc:
            self.last_error = str(exc); self.disconnect("receive failure"); return
        if data == b"":
            self.disconnect("peer closed"); return
        if data:
            old_count = self.twin.command_count
            try:
                self.twin.feed(data, owner=self._owner)
            except ValueError as exc:
                self.last_error = str(exc); self.disconnect("command error"); return
            self.tx_frames += self.twin.command_count - old_count
            self.last_command = data[:40].hex(" ").upper()
            self._last_activity = self._last_input = now
        if self._overflow or self.twin.overflow:
            self.disconnect("response buffer overflow"); return
        if self._output:
            try:
                count = self.client.send(self._output)
            except BlockingIOError:
                return
            except OSError as exc:
                self.last_error = str(exc); self.disconnect("send failure"); return
            if count == 0:
                self.disconnect("send closed"); return
            del self._output[:count]
            self._last_activity = now
            while count and self._sizes:
                if count >= self._sizes[0]:
                    count -= self._sizes.popleft(); self.rx_frames += 1
                else:
                    self._sizes[0] -= count; count = 0

    def close(self):
        self.twin._check_thread()
        self.disconnect("listener disabled")
        if self.listener is not None:
            self.listener.close(); self.listener = None
        for name in ("_unsubscribe_rx", "_unsubscribe_switch"):
            unsubscribe = getattr(self, name)
            if unsubscribe:
                unsubscribe(); setattr(self, name, None)

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()
