"""Synthetic controller policy over the verified wire format; never firmware emulation."""
from __future__ import annotations
import math
from ..protocol import (Sequence, ProtocolError, TEMPERATURES, FUNCTIONS, parse_frame,
    decode_command, encode_telemetry, Telemetry, encode_ota, decode, pack, uint)
from .model import SimulationEngine
from .limits import MAX_PENDING

class UnsupportedCommand(ProtocolError):
    """A valid wire message outside the model's explicitly supported behavior."""

class MCSVirtualPowerBoard:
    def __init__(self, engine: SimulationEngine | None=None):
        self.engine=engine or SimulationEngine();self.sequence=Sequence()
        self.drop_next=0;self.corrupt_next=0;self.delay_seconds=0.0
        self.pending: list[tuple[float,bytes]]=[]
        self.last_tx: bytes | None=None;self.last_rx: bytes | None=None
        self.metadata=b'\0'*16

    def faults(self, *, drop_next: int=0, corrupt_next: int=0, delay_seconds: float=0) -> None:
        for value in (drop_next,corrupt_next):
            if type(value) is not int or value<0:raise ValueError('fault counts must be nonnegative integers')
        if type(delay_seconds) not in (int,float) or not math.isfinite(delay_seconds) or delay_seconds<0:
            raise ValueError('delay_seconds must be finite and nonnegative')
        self.drop_next=drop_next;self.corrupt_next=corrupt_next;self.delay_seconds=float(delay_seconds)

    def transact(self, request: bytes) -> bytes | None:
        # A rejected response must not leave a newly applied command or sequence.
        before=self.engine.state.snapshot();counter=self.sequence.value;metadata=self.metadata
        if self.delay_seconds and not self.drop_next and len(self.pending)>=MAX_PENDING:
            raise ProtocolError('synthetic delayed response queue is full')
        try:return self._transact(request)
        except (ValueError,OverflowError):
            for name,value in before.items():setattr(self.engine.state,name,value)
            self.sequence.value=counter;self.metadata=metadata
            raise

    def _transact(self, request: bytes) -> bytes | None:
        frame=parse_frame(request)
        if frame.bitmap!=b'OB' or frame.subtype!=0:
            raise UnsupportedCommand('virtual board only supports OB / subtype 0')
        if self.engine.state.interrupted:raise UnsupportedCommand('session interrupted; create a new twin')
        if frame.opcode>>8==0xfe:
            response=self._ota(request)
        else:
            c=decode_command(request);s=self.engine.state
            # Reject before mutation. Unknown fields remain visible in c.frame.
            if c.frame.opcode==0x0805:raise UnsupportedCommand('0805 behavior is unknown')
            if c.frame.opcode==0x0803:
                if c.scale_mode!=1:raise UnsupportedCommand('only scale mode 1 (tare) is modeled')
                s.tare_offset=s.mass;s.weight=0;s.scale_state=0;s.weight_saturated=False;s.stable=False;s.stable_elapsed=0
            elif c.frame.opcode==0x0802:
                if c.function not in FUNCTIONS:raise UnsupportedCommand('unknown function')
                if c.speed_level>20 or c.direction_raw not in (0,1) or c.temperature_level>=len(TEMPERATURES) or c.constant_temperature>255:
                    raise UnsupportedCommand('operational parameter outside studied model profile')
                s.function=c.function;s.reverse=bool(c.direction_raw)
                s.requested_level=float(c.speed_level)
                if c.function==198 and c.speed_level==0 and c.turbo_lock:
                    s.requested_level=20.0  # deliberately artificial turbo policy
                s.temperature_level=c.temperature_level
                s.target_temperature=float(c.constant_temperature or TEMPERATURES[c.temperature_level])
                s.remaining=float(c.seconds);s.timer_active=bool(c.seconds)
                s.light_type,s.light=c.light;s.button=c.button;s.turbo_lock=c.turbo_lock
                s.last_command_time=self.engine.clock.now
                if c.function in (0,15):self.engine.stop()
            elif c.frame.opcode!=0x0801:raise UnsupportedCommand('unmodeled operation')
            response=self.telemetry(c.frame.opcode)
        self.last_tx=bytes(request)
        if self.drop_next:self.drop_next-=1;return None
        if self.corrupt_next:
            self.corrupt_next-=1;response=response[:-1]+bytes([response[-1]^1])
        self.last_rx=response
        if self.delay_seconds:
            self.pending.append((self.engine.clock.now+self.delay_seconds,response));return None
        return response

    def telemetry(self, opcode: int=0x0802) -> bytes:
        s=self.engine.state
        state=(0x80 if s.lid_open else 0)|(0x40 if not s.ntc_present else 0)|(
            8 if s.actual_level>0 else 0)|(4 if s.stable else 0)
        t=Telemetry(opcode=opcode,firmware_version=s.firmware,state=state,error=s.error,
            temperature_level=s.temperature_level,returned_temperature=round(s.target_temperature),
            actual_temperature=round(s.temperature),speed_level=round(abs(s.actual_level)),
            direction_raw=int(s.actual_level<0),turbo_key=min(s.turbo_lock,127),function=s.function,
            weight=round(s.weight),scale_state=s.scale_state,calibration_step=s.calibration_step,
            seconds=math.ceil(s.remaining),light=s.light,button=s.button)
        # Independent response counter; a request sequence is never promised as ACK.
        return encode_telemetry(t,sequence=self.sequence.next())

    def ready(self) -> list[bytes]:
        due=[data for at,data in sorted(self.pending,key=lambda item:item[0]) if at<=self.engine.clock.now+1e-12]
        self.pending=[(at,data) for at,data in self.pending if at>self.engine.clock.now+1e-12]
        return due

    def _ota(self, request: bytes) -> bytes:
        """Shape-only OTA emulator. Return=0 is synthetic, not proven success semantics."""
        f=parse_frame(request);d=decode(request,direction='tx');sub=f.opcode&255
        if sub not in (1,2,3,4,6):raise UnsupportedCommand('no documented FE05 TX / unsupported OTA')
        if sub==1:self.metadata=f.payload[2:];tail=b'\0'
        elif sub==2:tail=f.payload[2:4]
        elif sub==3:tail=b'\0'+self.metadata
        elif sub==4:tail=b'\0'
        else:tail=b'\0'+self.engine.state.firmware.to_bytes(2,'big')
        return pack(f.payload[:2]+tail,sequence=self.sequence.next())
