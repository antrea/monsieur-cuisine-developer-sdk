> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Optional virtual serial adapters

The normal simulator and desktop application use an in-memory model. They do not require a serial driver, COM port, network server or appliance. Importing the adapter module starts nothing.

This optional module adds two development seams:

| Adapter | Platforms | Connection | Clock |
|---|---|---|---|
| `SerialLike` | Windows, Linux, macOS with Python 3.11+ | In-process `read`/`write` object; no OS device | Explicit `advance(milliseconds)` |
| `POSIXPTYBridge` | POSIX systems with Python `pty` support | Creates a fresh pseudo-terminal for another local application | Explicit `advance(milliseconds)` |

**Windows virtual COM emulation is not implemented.** No driver is installed, and no existing COM port or arbitrary device path can be selected through these adapters. For a separate Windows process, use the optional [loopback TCP endpoint](api.md). An application that only accepts a Windows COM port would need a separately designed and reviewed virtual-driver integration; this release does not supply that bridge.

## Driver-free serial-style object

```python
from mcc_protocol import Operation, decode_frame, encode_tx
from mcc_powerboard_simulator.virtual_serial import SerialLike

with SerialLike(timeout=0) as port:
    written = port.write(encode_tx(Operation.STANDARD, speed=2))
    assert written == 15
    first = decode_frame(port.read(27))
    assert first.actual_rpm == 0

    port.advance(100)
    port.sample()
    later = decode_frame(port.read(27))
    assert later.actual_rpm > 0
```

All bytes in this example are synthetic. `write` accepts raw binary data, including fragments, and returns the byte count. That count does not prove that a valid command was decoded. Read bytes contain the existing 27-byte RX format. The illustrative physics model changes RPM after time advances; it does not certify a real controller.

`SerialLike` is a deliberately small interface, not a complete `pyserial` implementation or an Android Binder replacement. It has no dependency on `pyserial`. Inject this object at an application's own transport interface rather than passing it as an operating-system port name.

| API | Behavior |
|---|---|
| `SerialLike(model=None, *, timeout=0.0, max_buffer_bytes=1048576)` | Creates an open memory endpoint; starts no transport |
| `write(data) -> int` | Feeds bytes, buffers immediately ready RX and returns input byte count |
| `read(size=1) -> bytes` | Reads up to the requested byte count according to `timeout` |
| `in_waiting` | Count of buffered RX bytes |
| `is_open` | Memory endpoint lifecycle state |
| `advance(delta_ms)` / `sample()` | Buffers ready RX and returns the same frame list |
| `snapshot()` | Returns model state without generating RX; works after close |
| `set_sensors`, `set_faults`, `configure` | Guarded wrappers for the model APIs |
| `reset_input_buffer()` | Clears delivered RX bytes; delayed model responses remain queued |
| `reset_output_buffer()` | Discards an incomplete TX prefix; previously accepted commands remain applied |
| `flush()` | Verifies the endpoint is open; memory writes already reach the model synchronously |
| `close()` | Wakes waiting readers, clears transport buffers and preserves model motor targets |

`timeout=0` is nonblocking. A finite nonnegative timeout may return a partial read. `timeout=None` waits until the requested count is available or the endpoint closes. These waits use wall-clock time only for the read operation; they never advance simulated physics. Closing the endpoint wakes waiting readers with `ValueError`.

RX buffering is bounded. Overflow raises `BufferError` and increments `buffer_overruns`; the triggering model operation has already happened, while its RX is not appended. Read or reset the buffer before continuing. A partial timeout read must be reassembled by the caller, just as with other byte transports.

`model_lock` is a reentrant lock used by all wrappers. If several components share one model, they must share this lock or serialize access externally. Closing the endpoint does not send STOP or invent a controller watchdog.

## Fresh POSIX pseudo-terminal

On Linux or macOS, explicitly start a fresh pair when another local application needs a device-shaped interface:

```python
import time
from mcc_powerboard_simulator.virtual_serial import POSIXPTYBridge

with POSIXPTYBridge() as bridge:
    print("Connect your local development client to:", bridge.slave_name)
    # This example advances a synthetic clock for ten wall-clock seconds.
    for _ in range(100):
        bridge.advance(100)
        bridge.sample()
        time.sleep(0.1)
```

The bridge calls `pty.openpty()` itself. `slave_name` refers only to that newly created virtual endpoint; the API accepts no existing device path. The slave uses raw mode so binary protocol bytes are not line-edited or echoed. Descriptors and the reader thread are closed by the context manager. The name is temporary and must not be reused after close.

The bridge has `start`, `close`, `running`, `slave_name`, `model_lock`, `snapshot`, `advance` and `sample`. Call `set_sensors`, `set_faults` or `configure` on `bridge.model` while holding `bridge.model_lock` for a compound development transaction. It supports bounded response buffering, reports background transport errors through `last_error`, and does not automatically stop a virtual motor when a client disappears.

On Windows, attempting `start()` raises `NotImplementedError` before opening any port. Memory adapter tests run on Windows; native PTY integration tests are skipped there. POSIX test coverage must be assessed from an actual POSIX test run rather than inferred from Windows results.

Neither adapter validates appliance interlocks, physical timing, motor duty cycles or firmware behavior. See [fidelity](fidelity.md) and [safety boundaries](../safety-and-limitations.md).
