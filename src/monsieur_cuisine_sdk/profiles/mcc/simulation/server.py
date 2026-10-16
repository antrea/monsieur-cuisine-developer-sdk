"""Explicitly started, loopback-only raw binary protocol development server.

The TCP endpoint emulates a byte transport into a synthetic model. It does not
open serial devices, contact an appliance, or provide a controller watchdog.
Virtual time advances only when a caller invokes :meth:`advance`.
"""

from __future__ import annotations

import socket
import threading
from types import TracebackType

from .model import PowerBoardModel


class PowerBoardTCPServer:
    """Serve a single active TCP client on literal ``127.0.0.1``.

    Construction does not bind a socket. Call ``start()`` or use a context
    manager. Other simultaneous clients are closed without model access.
    ``model_lock`` is the shared reentrant lock for embedding transactions.
    Every provided model wrapper acquires it automatically. A slow or departed
    client is disconnected; TCP failure never implies a synthetic motor STOP.
    This server is single-use after ``close()``; shutdown is idempotent.
    """

    def __init__(self, model: PowerBoardModel | None = None, *, port: int = 0) -> None:
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be an integer in 0..65535")
        self.model = model if model is not None else PowerBoardModel()
        self.model_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._stop = threading.Event()
        self._closed = False
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._client_threads: set[threading.Thread] = set()
        self._address = ("127.0.0.1", port)

    @property
    def address(self) -> tuple[str, int]:
        """The requested endpoint before start, and bound endpoint afterward."""

        with self._state_lock:
            return self._address

    @property
    def client_connected(self) -> bool:
        with self._state_lock:
            return self._client is not None

    @property
    def running(self) -> bool:
        with self._state_lock:
            return self._listener is not None and not self._closed

    def _ensure_open(self) -> None:
        with self._state_lock:
            if self._closed:
                raise RuntimeError("server is closed; create a new instance")

    def _event(self, event: str, **fields: object) -> None:
        # Callers hold model_lock, keeping model clock and log entries coherent.
        self.model.log.append({"at_ms": self.model.now_ms, "event": event, **fields})

    @staticmethod
    def _close_socket(connection: socket.socket) -> None:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()

    def start(self) -> PowerBoardTCPServer:
        """Bind the local endpoint and start daemon accept/client workers."""

        with self._state_lock:
            self._ensure_open()
            if self._listener is not None:
                return self
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.bind(self._address)
                listener.listen(4)
                listener.settimeout(0.2)
            except BaseException:
                listener.close()
                raise
            endpoint = listener.getsockname()
            self._address = ("127.0.0.1", endpoint[1])
            self._listener = listener
            self._accept_thread = threading.Thread(
                target=self._accept, args=(listener,), name="powerboard-tcp-accept", daemon=True,
            )
            self._accept_thread.start()
        return self

    def _accept(self, listener: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            connection.settimeout(0.2)
            with self.model_lock:
                with self._state_lock:
                    reject = self._closed or self._client is not None
                    if not reject:
                        # Keep registration and thread.start atomic relative
                        # to close(), so shutdown never joins an unstarted worker.
                        self.model.reset_transport()
                        self._event("tcp_client_connected")
                        self._client = connection
                        worker = threading.Thread(
                            target=self._read_client, args=(connection,),
                            name="powerboard-tcp-client", daemon=True,
                        )
                        self._client_threads.add(worker)
                        worker.start()
                if reject:
                    self._event("tcp_client_rejected")
                    self._close_socket(connection)
                    continue

    def _disconnect_locked(self, connection: socket.socket, reason: str) -> None:
        """Detach only this session; model_lock must already be held."""

        with self._state_lock:
            if self._client is not connection:
                return
            self._client = None
        self.model.reset_transport()
        self._event("tcp_client_disconnected", reason=reason)
        self._close_socket(connection)

    def _send_locked(self, frames: list[bytes]) -> None:
        if not frames:
            return
        with self._state_lock:
            connection = self._client
        if connection is None:
            return
        payload = b"".join(frames)
        try:
            connection.sendall(payload)
        except OSError:
            self._disconnect_locked(connection, "send_failed")
            return
        self._event("tcp_sent", frame_count=len(frames), byte_count=len(payload))

    def _read_client(self, connection: socket.socket) -> None:
        reason = "peer_closed"
        try:
            while not self._stop.is_set():
                try:
                    data = connection.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    reason = "receive_failed"
                    break
                if not data:
                    break
                with self.model_lock:
                    with self._state_lock:
                        if self._closed or self._client is not connection:
                            break
                    frames = self.model.feed(data)
                    self._send_locked(frames)
        finally:
            with self.model_lock:
                self._disconnect_locked(connection, reason)
            with self._state_lock:
                self._client_threads.discard(threading.current_thread())

    def feed(self, data: bytes) -> list[bytes]:
        """Feed development bytes and attempt to forward ready RX to TCP."""

        with self.model_lock:
            self._ensure_open()
            frames = self.model.feed(data)
            self._send_locked(frames)
            return frames

    def advance(self, delta_ms: int) -> list[bytes]:
        """Advance virtual time explicitly and forward any newly ready RX."""

        with self.model_lock:
            self._ensure_open()
            frames = self.model.advance(delta_ms)
            self._send_locked(frames)
            return frames

    def sample(self) -> list[bytes]:
        """Request synthetic telemetry and forward any ready RX."""

        with self.model_lock:
            self._ensure_open()
            frames = self.model.sample()
            self._send_locked(frames)
            return frames

    def snapshot(self) -> dict[str, object]:
        """Return serialized model state, also available after shutdown."""

        with self.model_lock:
            return self.model.snapshot()

    def set_sensors(self, **changes: object) -> None:
        with self.model_lock:
            self._ensure_open()
            self.model.set_sensors(**changes)

    def set_faults(self, **changes: object) -> None:
        with self.model_lock:
            self._ensure_open()
            self.model.set_faults(**changes)

    def configure(self, **changes: object) -> None:
        with self.model_lock:
            self._ensure_open()
            self.model.configure(**changes)

    def close(self) -> None:
        """Stop workers and close sockets; never issue a model motor command."""

        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            listener, self._listener = self._listener, None
            client, self._client = self._client, None
            accept_worker = self._accept_thread
            workers = tuple(self._client_threads)
        if listener is not None:
            self._close_socket(listener)
        if client is not None:
            self._close_socket(client)
        current = threading.current_thread()
        # Closing sockets wakes blocking calls; joins bound shutdown duration.
        for worker in (accept_worker, *workers):
            if worker is not None and worker is not current:
                worker.join(timeout=2.0)
        with self.model_lock:
            self.model.reset_transport()
            self._event("tcp_server_closed")

    def __enter__(self) -> PowerBoardTCPServer:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        self.close()
