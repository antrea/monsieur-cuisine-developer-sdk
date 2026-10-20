# MCC build 292: host policy versus controller simulation

The local reference is the owner's Android host app `de.silpion.mc2` 1.1.28,
build 292. It is not the PowerBoard MCU firmware. Evidence levels are explicit:

| Level | Meaning in this branch |
|---|---|
| VERIFIED | Original host bytecode executed previously in an isolated JVM, or independent differential output reproduced from its recorded vectors |
| STATIC | Existing decompiled app code inspected; UI/state-machine behavior has not been executed here |
| INFERRED | A deterministic model chosen to support development, including controller physics and calibration timing |
| UNVERIFIED | Physical UART, MCU image/implementation, real safety interlocks, controller timings and hardware restoration |

The retained 9,642-record [fixture](../fixtures/oem/README.md) covers TX/RX,
temperature conversions, speed bins and time limits. The complete private
differential contains 57,998 records. These are Android software comparisons,
not measured motor/thermal curves or physical traffic captures.

## High-level command construction

`DigitalTwin('mcc')` uses `parameters={'host_policy': 'oem'}` by default. It adapts
requests as the app does: speed at most 3 with heat, at most 3 CCW, and at most 4
for unheated CCW KNEAD. STANDARD uses minimum speed 1; STEAM/TOAST can use zero.
`set_temperature()` reissues the current operation with those limits, including
minimum speed 1 from idle. It no longer constructs STANDARD/heating/speed-zero.
Use `parameters={'host_policy': 'strict'}` to reject an adjustment instead.
Explicit byte-level `feed()` retains the original wire semantics and does not
apply this host policy.

`start_motor()` now defaults to **CW**, as does Kotlin `startMotor()`. Always pass
the direction explicitly in existing applications that need CCW. The Kotlin
high-level STANDARD client uses the same speed caps/minimum and offers
`HostPolicyMode.STRICT`; raw frame transport remains independent. Kotlin cannot
automatically confirm the hot-speed dialog and rejects a high-speed request when
cached telemetry reports at least 60 °C.

`set_recipe_temperature(celsius)` is explicitly MCC-only and applies the recipe
conversion: 1–29 °C means no heat, 30–37 maps to level 1, then upward bands to
130 °C. Exact knob/table temperatures remain required by `set_temperature()`.
The pure conversion functions are exposed from `profiles.mcc.oem_policy`.

`start_turbo()` checks MCC host entry gates and sends `C6`, speed 10, CW, no heat.
It sends one command, not a hold gesture. The caller must STOP on release. A
measured temperature at least 60 °C, an open lid, a target level at least 5 or an
active error blocks manual entry. High-speed/hot confirmation is explicit in
Python (`hot_speed_confirmed=True`) and selects level 4, rather than certifying
any physical safety property.

## App timing and latch (STATIC)

The service latches the latest command and reserializes approximately every
100 ms, including STOP/SLEEP. STOP followed by START before the next service tick
can leave only START on the wire; this also occurs at step transitions. Start
followed immediately by app pause can similarly collapse to STOP. Unbind can
silence transmission before its latched STOP is sent; no MCU watchdog is known.

The serial reader runs every **500 ms**, keeping the latest aligned 27-byte block
without robust byte-stream resynchronization. The SDK intentionally provides a
more robust parser; that is a documented improvement, not identical OEM timing.

Manual turbo begins after a **100 ms first tick**, then uses **1 s** ticks. It is
hold-to-run: release/outside stops, the warning appears at 8 s and the app limit
is 600 ticks/about 600 s. Lid opening or measured temperature at least 60 °C stops
turbo. Guided turbo has its own step-specific timing and is not implemented as
an Android UI clone.

Count-up sessions stop automatically at the app limit: 15 min above level 6,
otherwise 99 min. Pause sends STOP, retains remaining time and becomes a full
stop after 30 s; lid closure does not automatically resume. Lid and board-error
handling belong to the app: board code 6 pauses, 8 stops, other reported errors
can leave RUN active while showing a dialog. Every nonzero error blocks a new
high-level start. These are not firmware interlocks inside the raw twin.

Idle is checked every 60 s. At least 420 s idle leads to a 30 s sleep countdown;
the effective idle interval depends on polling phase. Display sleep follows
about 2 s later in the app. Waking sends STOP with the app's LEFT direction.

Optional `profiles.mcc.cooking.CookingHost` models the latch, bounded count-up/
count-down, pause, manual turbo and sleep/wake above one MCC `DigitalTwin`:

```python
from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.profiles.mcc.cooking import CookingHost

host = CookingHost(DigitalTwin('mcc', record=False))
host.start(speed=3, seconds=5)
host.advance(5)  # virtual time, no real wait; host reaches FINISHED
print(host.state, host.twin.get_state().requested_speed)
```

The model samples app guards at its deterministic event boundaries. It does not
reproduce Android scheduling, dialog rendering, cloud, guided-recipe views or
display power. It is opt-in; ordinary twin commands remain single sends.

## Presets and running knobs (STATIC)

`profiles.mcc.programs` holds the app's three presets as data and
`CookingHost.start_program('kneading' | 'roasting' | 'steaming', seconds=None)`
runs them above the twin:

| Preset | Structure | Steps (work mode, speed, direction, level) | Limits |
|---|---|---|---|
| kneading | cycling unit, default 45 s | 15 s KNEAD 4 LEFT; rest KNEAD 0 LEFT; 104 s KNEAD 4 RIGHT | 120 s; only the time knob |
| roasting | cycling unit, default 420 s | 5 s TOAST 1 LEFT level 19; 30 s TOAST 0 LEFT level 19 | 840 s; time and temperature knobs |
| steaming | sequence | preheat 600 s STEAM 1 RIGHT level 17 (limit 600 s); then 1200 s (limit 3600 s) | time knob only; the preheat knob edits the next step |

A one-second timer tick selects the unit sub-step from `elapsed mod cycle`
with the app's `<=` comparison, so every boundary is reached one tick late: the
kneading rest is active only at the 16 s tick and at an exact cycle multiple the
first sub-step is selected again (`programs.unit_schedule` lists the switches).
For sessions longer than 85 s the rest phase becomes `duration - 85 s`. A
sub-step change re-sends the latched command only when speed, level or work mode
differ; in kneading a direction change alone is not re-sent. Sequence steps end
with STOP immediately followed by the next START, which the latch collapses to
START; only the final step blinks the LED green. `skip_step()` skips a running
preheat step when the lid is closed.

Knob changes while running follow `CookingManager`: `set_speed(0)` stops;
adding heat caps the speed at 3 and re-sends; a speed of at least 4 while the
measured temperature is at least 60 °C needs `hot_speed_confirmed=True`, which
selects level 4 and silences the warning for the session; `set_temperature()`
applies the recipe binning; `set_direction()` is ignored by kneading;
`set_time()` with a new value restarts a running countdown from zero, 0 stops,
and count-up sessions ignore it. Presets lock the knobs the app locks.

## Service callbacks, scale display and LED (STATIC)

`profiles.mcc.ipc` maps an RX frame to the service's sensor holder
(`IpcSnapshot.from_frame`) and reproduces its change callbacks:
`on_motor_state_changed(motor, direction, level)` uses the measured level,
`on_scale_state_changed(state, weight, calibration_step)`,
`on_temperature_changed(celsius)` also fires on heater changes, and
`on_lid_opened`/`on_lid_closed`. `on_bad_state(codes)` is edge-triggered: it
fires when the error code changes to a nonzero value or the scale enters
overload, carrying app code 7 for scale overload before the board-derived code.
A persisting error is reported once; clearing it raises nothing. The main screen
hides code 7 unless the scale view is visible (`visible_warnings`). `CookingHost`
records these callbacks in `events` at each 100 ms service tick, together with
`on_start_cooking`, `on_pause_cooking`, `on_resume_cooking`, `on_stop_cooking`,
`on_next_step`, `on_finish_cooking`, `dialog` and optional `on_tick_cooking`.

The scale knob shows the signed gram value rounded to the nearest 5 g with Java
`Math.round` semantics and `----g` during overload (`ipc.weight_text`).

`profiles.mcc.led.LedModel` reproduces the LED service with the app's numbers:
white is blue 50 only, green 60, red 75; solid, 500 ms blink, a 100-step
raised-cosine pulse at 30 ms per step, off, and timeouts that revert to solid
white. The host pulses white while cooking, shows solid white when paused or
stopped, blinks green for 3 s when finished, blinks red for 3 s on a dialog,
turns off when asleep and returns to white on wake. `host.led_rgb()` gives the
three channel values at the current virtual time; nothing is written to sysfs.

## Errors and synthetic calibration

Compatibility error names remain unchanged. `RxFrame.to_dict()['error_description']`
adds the app UI meaning: board 5 motor overheated, 6 pot overheated/add liquid,
7 motor overloaded. Board 7 is not app scale-overload code 7.

`encode_calibration('enter'|'start'|'exit')` uses the observed zero-payload E6/E9
layout. The dynamic model responds in calibration state and advances byte 23
from 0 to 4 after repeated START. The step interval defaults to **synthetic**
1000 ms and is configurable via `calibration_step_ms`; repeated 10 Hz frames do
not reset it. No weight thresholds or real scale adjustment are established.
Normal commands leave calibration. This is development scaffolding for the
documented wire fields, never a validated calibration procedure.
