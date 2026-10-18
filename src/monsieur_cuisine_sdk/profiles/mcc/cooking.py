"""Optional virtual host latch/timers, reconstructed from static build-292 app logic.

This sits above a DigitalTwin, not inside controller firmware simulation. A
100 ms latch collapses changes before transmission. Timer phases are an explicit
deterministic interpretation of static app code, not executed Android UI code.
"""
import math

from .oem_policy import max_time_ms
from .protocol.codec import Direction, Operation, decode_frame, encode_tx


class CookingHost:
    def __init__(self, twin):
        if twin.model.value != 'mcc':
            raise ValueError('CookingHost requires an MCC twin')
        self.twin = twin
        self.generation = twin.generation
        self.state = 'STOP'
        self.latched = twin.profile.encode_stop()
        self._running_command = None
        self._next_tx = twin.now_ns + 100_000_000
        self._next_idle_check = twin.now_ns + 60_000_000_000
        self._interaction = twin.now_ns
        self._finish_at = self._pause_stop_at = self._sleep_at = None
        self._remaining = 0
        self._turbo_at = self._turbo_started = None
        self.turbo_warning = False

    def _check(self):
        self.twin._check_owner()
        if self.twin.generation != self.generation or self.twin.model.value != 'mcc':
            raise ValueError('host session belongs to an old device generation')

    def start(self, speed=2, direction='cw', temperature=0, seconds=0):
        self._check()
        if type(seconds) is not int or not 0 <= seconds <= 5940:
            raise ValueError('host duration must be integer seconds 0..5940')
        command = self.twin.profile.encode_start(speed, direction, temperature)
        actual_speed = decode_frame(command).speed_level
        limit = max_time_ms(actual_speed) * 1_000_000
        self.latched = self._running_command = command
        self._finish_at = self.twin.now_ns + min(seconds * 10**9 if seconds else limit, limit)
        self._pause_stop_at = self._sleep_at = None
        self.state = 'RUN'; self._interaction = self.twin.now_ns

    def stop(self):
        self._check()
        direction = decode_frame(self.latched).direction or Direction.COUNTER_CLOCKWISE
        self.latched = encode_tx(Operation.STOP, direction=direction)
        self._finish_at = self._pause_stop_at = self._turbo_at = self._turbo_started = None
        self.state = 'STOP'; self.turbo_warning = False; self._interaction = self.twin.now_ns

    def pause(self):
        self._check()
        self._remaining = max(0, (self._finish_at or self.twin.now_ns) - self.twin.now_ns)
        direction = decode_frame(self.latched).direction
        self.latched = encode_tx(Operation.STOP, direction=direction)
        self._finish_at = None
        self._pause_stop_at = self.twin.now_ns + 30 * 10**9
        self.state = 'PAUSE'

    def resume(self):
        self._check()
        if self.state != 'PAUSE' or self._running_command is None:
            raise ValueError('host is not paused')
        frame = decode_frame(self._running_command)
        self.latched = self.twin.profile.encode_start(frame.speed_level,
            'cw' if frame.direction == Direction.CLOCKWISE else 'ccw',
            self.twin.profile.capabilities['temperature_values'][frame.temperature_level])
        self._finish_at = self.twin.now_ns + self._remaining
        self._pause_stop_at = None; self.state = 'RUN'

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
        state = self.twin.get_state()
        if state.lid_open or state.temperature >= 60 or state.target_temperature >= 60 or state.error_code:
            raise ValueError('manual turbo host entry gate')
        self._turbo_at = self.twin.now_ns + 100_000_000
        self._interaction = self.twin.now_ns

    def wake(self):
        self._check(); self.stop()
        # Static App.wakeUpMachine sends workMode=0, direction LEFT.
        self.latched = encode_tx(Operation.STOP, direction=Direction.COUNTER_CLOCKWISE)
        self._sleep_at = None

    def advance(self, seconds):
        self._check()
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 86400:
            raise ValueError('bounded finite virtual seconds required')
        end = self.twin.now_ns + round(seconds * 10**9)
        while self.twin.now_ns < end:
            deadlines = [end, self._next_tx, self._next_idle_check]
            deadlines += [n for n in (self._finish_at, self._pause_stop_at, self._sleep_at, self._turbo_at)
                          if n is not None and n > self.twin.now_ns]
            next_time = min(deadlines)
            self.twin.advance((next_time - self.twin.now_ns) / 1e9)
            now = self.twin.now_ns
            state = self.twin.get_state()
            if self.state == 'RUN' and (state.lid_open or state.error_code == 6):
                self.pause()
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
                self.stop(); self.state = 'FINISHED'
            if self._pause_stop_at is not None and now >= self._pause_stop_at:
                self.stop()
            if now >= self._next_idle_check:
                self._next_idle_check += 60 * 10**9
                if self.state in ('STOP', 'FINISHED') and now - self._interaction >= 420 * 10**9 and self._sleep_at is None:
                    self._sleep_at = now + 30 * 10**9
            if self._sleep_at is not None and now >= self._sleep_at:
                self.latched = encode_tx(Operation.SLEEP, direction=Direction.COUNTER_CLOCKWISE)
                self._sleep_at = None; self.state = 'SLEEP'
            if now >= self._next_tx:
                self.twin.feed(self.latched)
                self._next_tx += 100_000_000
        return self.twin.get_state()
