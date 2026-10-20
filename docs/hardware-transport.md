# Explicit MCC serial transport

Normal desktop startup is hardware-free. Install the optional serial extra only
for a deliberately selected UART or virtual endpoint:

```sh
python -m pip install '.[serial]'
mc-hardware monitor --port YOUR_PORT --seconds 5 --output private-trace.jsonl
mc-hardware replay private-trace.jsonl
```

The monitor is receive-only: no query, STOP, startup command or reconnect is
sent. The original protocol has no documented telemetry query; a silent board
may produce no RX without another host. Port selection and electrical
compatibility require independent evidence.

`SerialTransport` configures 4800 baud, 8N1 and no flow control, requesting
DTR/RTS low before open. Some OS drivers can still pulse lines. Construction
does not open or discover a port, and no OS driver is installed automatically.

```python
from monsieur_cuisine_sdk.hardware import MCCSerialSession, SerialTransport

with MCCSerialSession(SerialTransport(selected_port)) as session:
    for frame in session.poll():
        print(frame.to_dict())
```

Controlled active experiments require both `SerialTransport(read_only=False)`
and `MCCSerialSession(active=True)`, plus an explicit `arm()` after fresh,
error-free, zero-RPM telemetry with NTC and closed lid. Supply the selected port
as the transport's first argument. `command(tx_bytes)` applies strict MCC host
policy. Call `poll()` frequently; latched TX repeats at 100 ms without catch-up
bursts. Unsafe telemetry or expiry disarms and attempts STOP. There is no
physical braking acknowledgement or verified hardware watchdog. Reconnect
starts disarmed and never replays an old command. These host checks do not
certify appliance safety.

Serial sessions currently support MCC build 292. MCS physical transport remains
unverified. `ReplayTransport` replays timed RX bytes under an injected clock;
it is receive-only and does not construct synthetic telemetry.

Tests cover corrupt/partial/obsolete input, echoes, loss, short writes,
disconnects, sensor gates, STOP and an actual pyserial virtual loopback. They
are INTERNAL TESTED, not HARDWARE VERIFIED. The normal runtime retains zero
mandatory Python dependencies; the source auditor permits the serial import
only inside this optional transport's explicit `open()` method.
