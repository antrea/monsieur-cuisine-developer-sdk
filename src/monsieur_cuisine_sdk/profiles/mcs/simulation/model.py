"""Configurable synthetic physics. No coefficient or interlock is hardware verified."""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from collections import deque
import math
import random
from .limits import MAX_TICKS, SimulationCancelled, seconds_ns

@dataclass(frozen=True)
class ModelParameters:
    tick_seconds: float = 0.02
    acceleration: float = 8.0
    deceleration: float = 12.0
    ambient: float = 22.0
    heating_rate: float = 2.0
    cooling_coefficient: float = 0.02
    heater_lag: float = 0.6
    stability_seconds: float = 0.5
    overload_grams: float = 5000.0
    noise_grams: float = 0.0
    lid_interlock: bool = True
    ntc_interlock: bool = True
    overtemperature: float = 150.0
    command_timeout: float = 0.0  # disabled; no hardware watchdog inferred
    timeline_limit: int = 10000

    def __post_init__(self):
        for f in fields(self):
            value=getattr(self,f.name)
            if f.name in ('lid_interlock','ntc_interlock'):
                if type(value) is not bool:raise ValueError(f'{f.name} must be bool')
            elif f.name=='timeline_limit':
                if type(value) is not int or value<1:raise ValueError('timeline_limit must be positive integer')
            elif type(value) not in (int,float) or not math.isfinite(value):
                raise ValueError(f'{f.name} must be finite numeric')
        if not 0.001<=self.tick_seconds<=1:raise ValueError('tick_seconds must be 0.001..1')
        for name in ('acceleration','deceleration','heater_lag','overload_grams'):
            if getattr(self,name)<=0:raise ValueError(f'{name} must be positive')
        for name in ('heating_rate','cooling_coefficient','stability_seconds','noise_grams','command_timeout'):
            if getattr(self,name)<0:raise ValueError(f'{name} must be nonnegative')
        if not -100<=self.ambient<self.overtemperature<=1000:
            raise ValueError('ambient/overtemperature outside synthetic model range')
        # Explicit local model bounds keep accepted settings representable and useful.
        limits={'acceleration':1e6,'deceleration':1e6,'heating_rate':1000,
                'heater_lag':1e6,'overload_grams':1e8,'noise_grams':1e6,
                'stability_seconds':86400,'command_timeout':86400}
        for name,maximum in limits.items():
            if getattr(self,name)>maximum:raise ValueError(f'{name} exceeds synthetic model limit {maximum:g}')
        if self.cooling_coefficient*self.tick_seconds>1:
            raise ValueError('cooling_coefficient * tick_seconds must be <=1 for stable integration')
        if self.timeline_limit>100000:raise ValueError('timeline_limit exceeds 100000')

@dataclass
class VirtualClock:
    nanoseconds: int = 0

    @property
    def now(self) -> float:return self.nanoseconds/1_000_000_000

    def advance(self, seconds: float) -> None:
        self.nanoseconds+=seconds_ns(seconds)

@dataclass
class MachineState:
    time: float=0.0
    function: int=0
    requested_level: float=0.0
    actual_level: float=0.0  # signed virtual level, not RPM
    reverse: bool=False
    target_temperature: float=0.0
    temperature: float=22.0
    heater_power: float=0.0
    temperature_level: int=0
    mass: float=0.0
    tare_offset: float=0.0
    weight: float=0.0
    stable: bool=True
    stable_elapsed: float=0.0
    lid_open: bool=False
    ntc_present: bool=True
    error: int=0
    scale_state: int=0
    calibration_step: int=0
    remaining: float=0.0
    timer_active: bool=False
    light_type: int=0
    light: int=0
    button: int=0
    turbo_lock: int=0
    firmware: int=1  # virtual identifier, deliberately not historical MCU3069
    last_command_time: float=0.0
    interrupted: bool=False
    temperature_saturated: bool=False
    weight_saturated: bool=False

    def snapshot(self) -> dict:return asdict(self)

class SimulationEngine:
    """Fixed grid evolution. Advance partitioning is invariant absent intervening inputs.

    Fractional ticks are retained by the clock; state evolves at complete tick boundaries.
    Timeline is bounded; full session inputs belong in a separate recording.
    """
    def __init__(self, parameters: ModelParameters | None=None, *, seed: int=0):
        if type(seed) is not int:raise ValueError('seed must be integer')
        self.parameters=parameters or ModelParameters()
        self.seed=seed;self.random=random.Random(seed);self.clock=VirtualClock()
        self.state=MachineState(temperature=self.parameters.ambient,stable_elapsed=self.parameters.stability_seconds)
        self.timeline=deque(maxlen=self.parameters.timeline_limit)
        self._ticks=0;self._tick_ns=round(self.parameters.tick_seconds*1e9)
        self.timeline.append(self.state.snapshot())

    def sensors(self, **values) -> None:
        allowed={'mass','lid_open','ntc_present','error','temperature','button'}
        if set(values)-allowed:raise ValueError('unknown sensor field')
        # Validate the entire update before changing any state.
        for name,value in values.items():
            if name in ('lid_open','ntc_present'):
                if type(value) is not bool:raise ValueError(f'{name} must be bool')
            elif name in ('error','button'):
                if type(value) is not int or not 0<=value<=255:raise ValueError(f'{name} must be u8')
            elif type(value) not in (int,float) or not math.isfinite(value):raise ValueError(f'{name} must be finite')
            elif name=='mass' and abs(value)>1e8:raise ValueError('mass outside model range')
            elif name=='temperature' and not -100<=value<=1000:raise ValueError('temperature outside model range')
        s=self.state
        if 'mass' in values and values['mass']!=s.mass:
            s.stable=False;s.stable_elapsed=0
        for name,value in values.items():setattr(s,name,value)
        if 'temperature' in values:s.temperature_saturated=False
        if 'mass' in values:s.weight_saturated=False
        s.weight=s.mass-s.tare_offset
        s.scale_state=4 if abs(s.weight)>self.parameters.overload_grams else 0

    def stop(self) -> None:
        s=self.state;s.function=0;s.requested_level=0;s.target_temperature=0
        s.remaining=0;s.timer_active=False

    def interrupt(self) -> None:
        self.state.interrupted=True;self.stop()

    def advance(self, seconds: float, *, cancel=None) -> dict:
        """Advance bounded work; cancellation is for discarded background jobs.

        Synthetic temperatures saturate at -100..1000 C and weights at signed s32.
        Saturation is exposed in MachineState and is not a physical sensor policy.
        """
        delta_ns=seconds_ns(seconds)
        target_ns=self.clock.nanoseconds+delta_ns
        target=target_ns//self._tick_ns
        if target-self._ticks>MAX_TICKS:raise ValueError('advance exceeds simulation tick work budget')
        if cancel is not None and not callable(cancel):raise ValueError('cancel must be callable')
        if cancel is not None and cancel():raise SimulationCancelled('simulation cancelled')
        self.clock.nanoseconds=target_ns
        while self._ticks<target:
            if cancel is not None and self._ticks%256==0 and cancel():
                self.clock.nanoseconds=self._ticks*self._tick_ns
                raise SimulationCancelled('simulation cancelled')
            self._ticks+=1
            self._step(self._tick_ns/1e9)
        return self.state.snapshot()

    def _step(self, dt: float) -> None:
        p=self.parameters;s=self.state;s.time=self._ticks*self._tick_ns/1e9
        if p.command_timeout and s.function and s.time-s.last_command_time>=p.command_timeout:
            s.error=8;self.stop()
        if s.temperature>=p.overtemperature:s.error=7
        blocked=bool(s.error or s.interrupted or (p.lid_interlock and s.lid_open) or
                     (p.ntc_interlock and not s.ntc_present))
        target=0.0 if blocked else s.requested_level*(-1 if s.reverse else 1)
        # A reversal must first reach zero. No direct jump across direction.
        reversing=s.actual_level*target<0
        effective=0.0 if reversing else target
        accelerating=abs(effective)>abs(s.actual_level) and not reversing
        delta=(p.acceleration if accelerating else p.deceleration)*dt
        if abs(effective-s.actual_level)<=delta:s.actual_level=effective
        else:s.actual_level+=math.copysign(delta,effective-s.actual_level)
        demand=1.0 if not blocked and s.target_temperature>s.temperature else 0.0
        s.heater_power+=(demand-s.heater_power)*(1-math.exp(-dt/p.heater_lag))
        s.temperature+=(p.heating_rate*s.heater_power-p.cooling_coefficient*(s.temperature-p.ambient))*dt
        s.temperature_saturated=not -100<=s.temperature<=1000
        s.temperature=max(-100.0,min(1000.0,s.temperature))
        s.stable_elapsed+=dt;s.stable=s.stable_elapsed+1e-12>=p.stability_seconds
        noise=self.random.gauss(0,p.noise_grams) if p.noise_grams else 0.0
        s.weight=s.mass-s.tare_offset+noise
        s.weight_saturated=not -(1<<31)<=s.weight<=(1<<31)-1
        s.weight=max(float(-(1<<31)),min(float((1<<31)-1),s.weight))
        s.scale_state=4 if abs(s.weight)>p.overload_grams else 0
        if s.timer_active and not blocked:
            s.remaining=max(0,s.remaining-dt)
            if s.remaining<1e-9:self.stop()
        self.timeline.append(s.snapshot())
