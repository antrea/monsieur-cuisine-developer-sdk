"""Optional virtual host above an MCC DigitalTwin, reconstructed from static build-292 app logic.

It models what the app does above the wire: the 100 ms latch, the one-second
cooking timer, presets with cycling sub-steps, knob changes while running,
pause/auto-stop, manual turbo, idle sleep, the service's change callbacks and
the front LED. It sits above the twin, not inside controller simulation, and
every rule is a deterministic reading of decompiled app code (STATIC), never an
executed Android UI or a firmware fact.
"""
from __future__ import annotations

import math
from collections import deque

from .ipc import DEFAULT_SNAPSHOT, IpcSnapshot, callbacks as ipc_callbacks, visible_warnings
from .led import GREEN, RED, WHITE, LedModel
from .oem_policy import HOT_SPEED_LEVEL, HOT_SPEED_TEMPERATURE, SPEED_STIRRER_WARNING, max_time_ms, \
    recipe_temperature_level, speed_cap
from .programs import (CookingStep, CookingSteps, CookingUnit, LEFT, RIGHT, TICK_MS, WORK_MODES,
                       MachineConfiguration, active_step_index, preset, with_rest)
from .protocol.codec import Direction, Operation, decode_frame, encode_tx

NS, MS = 10**9, 10**6
SERVICE_PERIOD_NS = 100 * MS
DIALOG_LID_OPENED_DURING_COOKING = 10
_DIRECTIONS = {"cw": RIGHT, "ccw": LEFT}


def _wire(direction: int) -> Direction:
    return Direction.CLOCKWISE if direction == RIGHT else Direction.COUNTER_CLOCKWISE


class CookingHost:
    def __init__(self, twin, *, record_ticks=False):
        if twin.model.value != 'mcc':
            raise ValueError('CookingHost requires an MCC twin')
        self.twin = twin
        self.generation = twin.generation
        self.state = 'STOP'
        self.latched = twin.profile.encode_stop()
        self.events = deque(maxlen=4096)
        self.record_ticks = bool(record_ticks)
        self.led = LedModel()
        self.led.solid(self._now_ms(), WHITE)
        self._ipc_previous = DEFAULT_SNAPSHOT
        self._next_tx = twin.now_ns + SERVICE_PERIOD_NS
        self._next_idle_check = twin.now_ns + 60 * NS
        self._interaction = twin.now_ns
        self._finish_at = self._pause_stop_at = self._sleep_at = self._tick_at = None
        self._remaining_ms = 0
        self._turbo_at = self._turbo_started = None
        self.turbo_warning = False
        self._hot_acknowledged = False
        self._load_program(CookingStep(0, MachineConfiguration(1, 0, RIGHT, 0), "manual"))

    # -- bookkeeping ----------------------------------------------------------
    def _now_ms(self) -> int:
        return self.twin.now_ns // MS

    def _check(self):
        self.twin._check_owner()
        if self.twin.generation != self.generation or self.twin.model.value != 'mcc':
            raise ValueError('host session belongs to an old device generation')

    def _event(self, name, **data):
        self.events.append({"time": self.twin.now_ns / 1e9, "event": name, **data})

    @property
    def configuration(self) -> MachineConfiguration:
        return MachineConfiguration(self._work_mode, self._speed, self._direction, self._level)

    @property
    def step(self) -> CookingStep:
        return self._step

    @property
    def step_index(self) -> int:
        return self._index

    @property
    def speed_limit(self) -> int:
        return self._speed_limit

    @property
    def stirrer_warning(self) -> bool:
        return self._speed >= SPEED_STIRRER_WARNING

    @property
    def countdown(self) -> bool:
        return self._countdown

    def remaining_ms(self) -> int:
        if self.state == 'RUN' and self._finish_at is not None:
            return max(0, (self._finish_at - self.twin.now_ns) // MS)
        return self._remaining_ms if self.state == 'PAUSE' else 0

    def elapsed_ms(self) -> int:
        if self.state in ('RUN', 'PAUSE'):
            return self._total_ms - self.remaining_ms()
        return self._elapsed_ms

    def display_time_ms(self) -> int:
        """What the time knob shows: set time when stopped, remaining (countdown) or elapsed (count-up)."""
        if self.state in ('STOP', 'FINISHED', 'SLEEP'):
            return self._set_time_ms()
        return self.remaining_ms() if self._countdown else self.elapsed_ms()

    def led_rgb(self):
        return self.led.rgb_at(self._now_ms())

    # -- program template (CookingManager.f) ------------------------------------
    def _load_program(self, program):
        self.program = program
        self._index = 0
        self._speed_override = self._level_override = -1
        self._elapsed_ms = 0
        if isinstance(program, CookingSteps):
            self._step = program.steps[0]
            self._duration_ms = self._step.duration_ms
        elif isinstance(program, CookingUnit):
            self._step = program.steps[0]
            self._duration_ms = program.duration_ms
        else:
            self._step = program
            self._duration_ms = program.duration_ms
        config = self._step.configuration
        self._work_mode, self._speed, self._direction, self._level = (
            config.work_mode, config.speed, config.direction, config.temperature_level)
        self._countdown = self._duration_ms != 0
        self._total_ms = self._remaining_ms = 0
        self._limit_ms = max_time_ms(self._speed)
        self._speed_limit = 10
        self._sent = None
        self._countdown_key = None
        self._validate()

    def _next_step(self):
        if isinstance(self.program, CookingSteps) and self._index + 1 < len(self.program.steps):
            return self.program.steps[self._index + 1]
        return None

    def _set_time_ms(self) -> int:
        following = self._next_step() if self._step.preheat else None
        return following.duration_ms if following is not None else self._duration_ms

    def _set_duration(self, milliseconds):
        """CookingManager.a(long): the preheat step's knob edits the next step instead."""
        following = self._next_step() if self._step.preheat else None
        if following is not None:
            steps = list(self.program.steps)
            steps[self._index + 1] = CookingStep(**{**following.__dict__, "duration_ms": milliseconds})
            self.program = CookingSteps(tuple(steps))
        else:
            self._duration_ms = milliseconds

    # -- validation (CookingManager.i) and minimum speed (a) -------------------
    def _validate(self):
        operation = WORK_MODES[self._work_mode]
        cap = speed_cap(self._level, _wire(self._direction), operation)
        self._speed = min(self._speed, cap)
        self._speed_limit = cap
        if 0 <= self._step.speed_limit < cap:
            self._speed_limit = self._step.speed_limit
        limit = max_time_ms(self._speed)
        if isinstance(self.program, CookingUnit) and self.program.limit_ms > 0:
            limit = min(limit, self.program.limit_ms)
            if self._work_mode == 5:
                self.program = with_rest(self.program, self._duration_ms)
                self._step = self.program.steps[self._index]
        elif isinstance(self.program, CookingSteps) and self._step.time_limit_ms > 0:
            limit = min(limit, self._step.time_limit_ms)
        self._limit_ms = limit
        self._duration_ms = min(self._duration_ms, limit)
        self._elapsed_ms = min(self._elapsed_ms, limit)
        self._remaining_ms = min(self._remaining_ms, limit)

    def _frame(self, *, gates):
        """The latched start frame for the current configuration (HostPolicy applies caps/minimum)."""
        state = self.twin.get_state()
        decision = self.twin.profile.policy.start(
            WORK_MODES[self._work_mode], self._speed, _wire(self._direction), self._level,
            measured_temperature=state.temperature if gates else None,
            lid_open=state.lid_open if gates else None, error_code=state.error_code if gates else 0,
            hot_speed_confirmed=self._hot_acknowledged, knead_rest=self._step.rest)
        if decision.refusals or decision.confirmations:
            raise ValueError('MCC host policy: ' + '; '.join(decision.refusals + decision.confirmations))
        return decision, encode_tx(decision.operation, speed=decision.speed, direction=decision.direction,
                                   temperature_level=decision.temperature_level)

    def _send_start(self, *, gates):
        decision, frame = self._frame(gates=gates)
        self._speed = decision.speed
        self.latched = frame
        self._sent = (self._work_mode, self._speed, self._direction, self._level)

    def _send_stop(self):
        self.latched = encode_tx(Operation.STOP, direction=_wire(self._direction))

    # -- countdown (CookingManager.d) --------------------------------------------
    def _create_countdown(self, *, arm):
        if self.state in ('STOP', 'FINISHED', 'SLEEP') or self._countdown:
            self._elapsed_ms = 0
        self._countdown_key = (self._duration_ms, self._limit_ms)
        self._total_ms = self._duration_ms or self._limit_ms
        self._remaining_ms = self._duration_ms or (self._limit_ms - self._elapsed_ms)
        if arm:
            self._finish_at = self.twin.now_ns + self._remaining_ms * MS
            self._tick_at = self.twin.now_ns + TICK_MS * MS

    def _start_cooking(self):
        """CookingManager.startCooking: validate, minimum speed, latch START, new countdown."""
        self._validate()
        self._countdown = self._duration_ms != 0
        self._send_start(gates=True)
        self.led.pulse(self._now_ms(), WHITE)
        self._create_countdown(arm=True)
        self._pause_stop_at = self._sleep_at = None
        if self.state != 'RUN':
            self.state = 'RUN'
            self._event('on_start_cooking', countdown=self._countdown)
        self._interaction = self.twin.now_ns

    def _apply_changes(self):
        """CookingManager.b: re-send on changed settings while running, rebuild the timer on time changes."""
        if self.state == 'RUN':
            previous = self._sent or (None,) * 4
            if ((self._direction != previous[2] and self._work_mode != 5) or self._speed != previous[1]
                    or self._level != previous[3] or self._work_mode != previous[0]):
                self._send_start(gates=False)
            if self._countdown_key != (self._duration_ms, self._limit_ms):
                if self._countdown and self._duration_ms == 0:
                    self.stop()
                    return
                self._create_countdown(arm=True)
        elif self.state == 'PAUSE' and self._countdown_key != (self._duration_ms, self._limit_ms):
            if self._countdown and self._duration_ms == 0:
                self.stop()
                return
            self._create_countdown(arm=False)

    # -- public controls ---------------------------------------------------------
    def start(self, speed=2, direction='cw', temperature=0, seconds=0):
        """Manual session: one STANDARD step; ``seconds`` 0 means count-up to the app limit."""
        self._check()
        if type(seconds) is not int or not 0 <= seconds <= 5940:
            raise ValueError('host duration must be integer seconds 0..5940')
        if direction not in _DIRECTIONS:
            raise ValueError("direction must be 'cw' or 'ccw'")
        values = self.twin.profile.capabilities['temperature_values']
        if type(temperature) is not int or temperature not in values:
            raise ValueError('MCC temperature must be an exact documented Celsius level')
        if type(speed) is not int or not 0 <= speed <= 10:
            raise ValueError('speed must be an integer level 0..10')
        self._load_program(CookingStep(seconds * 1000, MachineConfiguration(
            1, speed, _DIRECTIONS[direction], values.index(temperature)), "manual"))
        self._start_cooking()

    def start_program(self, program, seconds=None):
        """Run a preset by name ('kneading', 'roasting', 'steaming') or a CookingUnit/CookingSteps/CookingStep."""
        self._check()
        if isinstance(program, str):
            program = preset(program)
        if not isinstance(program, (CookingStep, CookingUnit, CookingSteps)):
            raise ValueError('program must be a preset name, CookingStep, CookingUnit or CookingSteps')
        if isinstance(program, (CookingUnit, CookingSteps)) and not program.steps:
            raise ValueError('program has no steps')
        self._load_program(program)
        if seconds is not None:
            if type(seconds) is not int or not 0 <= seconds <= 5940:
                raise ValueError('host duration must be integer seconds 0..5940')
            self._set_duration(seconds * 1000)
            self._validate()
        self._start_cooking()

    def stop(self):
        """CookingManager.stopCooking: STOP on the wire, template values restored."""
        self._check()
        self._send_stop()
        self.led.solid(self._now_ms(), WHITE)
        self._finish_at = self._pause_stop_at = self._tick_at = self._turbo_at = self._turbo_started = None
        self.turbo_warning = False
        self._hot_acknowledged = False
        self._load_program(self.program)
        self._interaction = self.twin.now_ns
        if self.state != 'STOP':
            self.state = 'STOP'
            self._event('on_stop_cooking')

    def pause(self):
        self._check()
        self._remaining_ms = self.remaining_ms() if self.state == 'RUN' else self._remaining_ms
        self._send_stop()
        self.led.solid(self._now_ms(), WHITE)
        self._finish_at = self._tick_at = None
        if self.state != 'PAUSE':
            self.state = 'PAUSE'
            self._event('on_pause_cooking')
            self._pause_stop_at = self.twin.now_ns + 30 * NS

    def resume(self):
        self._check()
        if self.state != 'PAUSE':
            raise ValueError('host is not paused')
        self._validate()
        self._send_start(gates=True)
        self.led.pulse(self._now_ms(), WHITE)
        self._finish_at = self.twin.now_ns + self._remaining_ms * MS
        self._tick_at = self.twin.now_ns + TICK_MS * MS
        self._pause_stop_at = None
        self.state = 'RUN'
        self._event('on_resume_cooking')
        self._interaction = self.twin.now_ns

    def skip_step(self):
        """Skip the steaming preheat step; the app allows it only with the lid closed."""
        self._check()
        if self.state != 'RUN' or not self._step.preheat or self._next_step() is None:
            raise ValueError('only a running preheat step can be skipped')
        if self.twin.get_state().lid_open:
            raise ValueError('close the lid before skipping the preheat step')
        self._on_finish()

    def set_speed(self, level, *, hot_speed_confirmed=False):
        """Speed knob: 0 while running stops; >= 4 at >= 60 °C measured needs confirmation (selects 4)."""
        self._check()
        if type(level) is not int or not 0 <= level <= 10:
            raise ValueError('speed must be an integer level 0..10')
        if not self._step.speed_knob:
            raise ValueError('this program locks the speed knob')
        if level <= 0 and self.state == 'RUN':
            self.stop()
            return
        if (not self._hot_acknowledged and level >= HOT_SPEED_LEVEL and self.state == 'RUN'
                and self.twin.get_state().temperature >= HOT_SPEED_TEMPERATURE):
            if not hot_speed_confirmed:
                raise ValueError('hot-speed confirmation required: pass hot_speed_confirmed=True (the app selects level 4)')
            self._hot_acknowledged = True
            level = HOT_SPEED_LEVEL
        self._speed = level
        self._validate()
        if isinstance(self.program, CookingUnit):
            self._speed_override = self._speed
        self._apply_changes()

    def set_temperature(self, celsius):
        """Temperature knob/recipe value: binned like the app, then heated speed caps re-apply."""
        self._check()
        if not self._step.temperature_knob:
            raise ValueError('this program locks the temperature knob')
        self._level = recipe_temperature_level(celsius)
        self._validate()
        if isinstance(self.program, CookingUnit):
            self._level_override = self._level
        self._apply_changes()

    def set_temperature_level(self, level):
        self._check()
        if type(level) is not int or level < 0:
            raise ValueError('level must be a nonnegative integer')
        if not self._step.temperature_knob:
            raise ValueError('this program locks the temperature knob')
        self._level = min(19, level)
        self._validate()
        self._apply_changes()

    def set_direction(self, direction):
        """Direction button: re-sent while running except in kneading, whose cycle owns the direction."""
        self._check()
        if direction not in _DIRECTIONS:
            raise ValueError("direction must be 'cw' or 'ccw'")
        if not self._step.direction_modifiable:
            raise ValueError('this program locks the direction')
        self._direction = _DIRECTIONS[direction]
        self._validate()
        self._apply_changes()

    def set_time(self, seconds):
        """Time knob: in a running countdown the elapsed time restarts; 0 stops; count-up ignores it."""
        self._check()
        if type(seconds) is not int or not 0 <= seconds <= 5940:
            raise ValueError('host duration must be integer seconds 0..5940')
        if not self._step.time_knob:
            raise ValueError('this program locks the time knob')
        milliseconds = seconds * 1000
        if self.state in ('STOP', 'FINISHED', 'SLEEP'):
            self._set_duration(milliseconds)
        elif self._countdown:
            if milliseconds <= 0:
                self.stop()
                return
            self._set_duration(milliseconds)
        self._validate()
        self._apply_changes()

    def turbo_hold(self, held):
        self._check()
        if type(held) is not bool:
            raise ValueError('held must be bool')
        if not held:
            self.stop(); return
        if self._turbo_at is not None or self._turbo_started is not None:
            return
        if self.state not in ('STOP', 'FINISHED'):
            raise ValueError('manual turbo starts only from STOP/FINISHED')
        if not self._step.turbo_enabled:
            raise ValueError('this program disables turbo')
        state = self.twin.get_state()
        if state.lid_open or state.temperature >= 60 or state.target_temperature >= 60 or state.error_code:
            raise ValueError('manual turbo host entry gate')
        self._turbo_at = self.twin.now_ns + SERVICE_PERIOD_NS
        self._interaction = self.twin.now_ns

    def wake(self):
        self._check(); self.stop()
        # Static App.wakeUpMachine sends workMode=0, direction LEFT.
        self.latched = encode_tx(Operation.STOP, direction=Direction.COUNTER_CLOCKWISE)
        self._sleep_at = None
        self.led.solid(self._now_ms(), WHITE)
        self._event('wake')

    # -- timer events ---------------------------------------------------------------
    def _on_finish(self):
        """CookingManager timer end: next step of a sequence, else FINISHED with a green blink."""
        self._send_stop()
        self._finish_at = self._tick_at = None
        following = self._next_step()
        if following is not None:
            self._index += 1
            self._step = following
            config = following.configuration
            self._work_mode, self._speed, self._direction, self._level = (
                config.work_mode, config.speed, config.direction, config.temperature_level)
            self._duration_ms = following.duration_ms
            self._event('on_next_step', index=self._index)
            self._start_cooking()
            return
        self.state = 'FINISHED'
        self._index = 0
        self._elapsed_ms = self._total_ms
        if isinstance(self.program, CookingSteps):
            self._step = self.program.steps[0]
            self._work_mode = self._step.configuration.work_mode
        self._event('on_finish_cooking')
        self.led.blink(self._now_ms(), GREEN, timeout_ms=3000)

    def _tick(self):
        """One-second timer tick: unit sub-step selection and the tick callback."""
        remaining = self.remaining_ms()
        elapsed = self._total_ms - remaining
        if isinstance(self.program, CookingUnit):
            index = active_step_index(self.program, elapsed)
            if index is not None and index != self._index:
                self._index = index
                self._step = self.program.steps[index]
                config = self._step.configuration
                self._direction = config.direction
                self._level = self._level_override if self._level_override != -1 else config.temperature_level
                self._speed = self._speed_override if self._speed_override != -1 else config.speed
                self._work_mode = config.work_mode
                if elapsed > self.program.steps[0].duration_ms:
                    self._event('on_next_step', index=index)
                self._validate()
                self._apply_changes()
        if self.record_ticks:
            self._event('on_tick_cooking', remaining_ms=remaining)

    def _service_tick(self):
        """The 100 ms service loop: reserialize the latch, then raise the change callbacks."""
        replies = self.twin.feed(self.latched)
        frames = [raw for raw in replies if len(raw) == 27]
        if not frames:
            return
        current = IpcSnapshot.from_frame(decode_frame(frames[-1]))
        for callback in ipc_callbacks(self._ipc_previous, current):
            self._event(callback[0], args=list(callback[1:]))
            if callback[0] == 'on_bad_state':
                codes = visible_warnings(callback[1])
                if codes:
                    self._event('dialog', codes=codes)
                    self.led.blink(self._now_ms(), RED, timeout_ms=3000)
        self._ipc_previous = current

    def advance(self, seconds):
        self._check()
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 86400:
            raise ValueError('bounded finite virtual seconds required')
        end = self.twin.now_ns + round(seconds * NS)
        while self.twin.now_ns < end:
            deadlines = [end, self._next_tx, self._next_idle_check]
            deadlines += [n for n in (self._finish_at, self._pause_stop_at, self._sleep_at, self._turbo_at,
                                      self._tick_at) if n is not None and n > self.twin.now_ns]
            next_time = min(deadlines)
            self.twin.advance((next_time - self.twin.now_ns) / 1e9)
            now = self.twin.now_ns
            state = self.twin.get_state()
            if self.state == 'RUN' and (state.lid_open or state.error_code == 6):
                self.pause()
                if state.lid_open:
                    self._event('dialog', codes=[DIALOG_LID_OPENED_DURING_COOKING])
                    self.led.blink(self._now_ms(), RED, timeout_ms=3000)
            if self.state == 'RUN' and state.error_code == 8:
                self.stop()
            if self._turbo_at is not None and now >= self._turbo_at:
                self.latched = encode_tx(Operation.TURBO, speed=10)
                self._turbo_started = now; self._turbo_at = None
            if self._turbo_started is not None:
                elapsed = (now - self._turbo_started) / 1e9
                self.turbo_warning = elapsed >= 8
                if state.lid_open or state.temperature >= 60 or elapsed >= 600:
                    self.stop()
            if self._finish_at is not None and now >= self._finish_at:
                self._on_finish()
            if self.state == 'RUN' and self._tick_at is not None and now >= self._tick_at:
                self._tick_at += TICK_MS * MS
                self._tick()
            if self._pause_stop_at is not None and now >= self._pause_stop_at:
                self.stop()
            if now >= self._next_idle_check:
                self._next_idle_check += 60 * NS
                if self.state in ('STOP', 'FINISHED') and now - self._interaction >= 420 * NS and self._sleep_at is None:
                    self._sleep_at = now + 30 * NS
            if self._sleep_at is not None and now >= self._sleep_at:
                self.latched = encode_tx(Operation.SLEEP, direction=Direction.COUNTER_CLOCKWISE)
                self._sleep_at = None; self.state = 'SLEEP'
                self.led.off(self._now_ms())
                self._event('sleep')
            if now >= self._next_tx:
                self._service_tick()
                self._next_tx += SERVICE_PERIOD_NS
        return self.twin.get_state()
