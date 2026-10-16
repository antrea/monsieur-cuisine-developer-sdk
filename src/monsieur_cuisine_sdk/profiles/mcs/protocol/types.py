"""Typed accessors; raw frames are retained for every decoded message."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum, IntEnum
import json
from ._baseline import ProtocolError, decode, pack, unpack, timer_bytes, uint, OPERATION_CODES

PROFILE = 'mc30-1.2.14.15'

class Evidence(str, Enum):
    CONFIRMED_IN_APK = 'CONFIRMED_IN_APK'
    INFERRED = 'INFERRED'
    UNKNOWN = 'UNKNOWN'
    HARDWARE_VERIFIED = 'HARDWARE_VERIFIED'

class Direction(str, Enum):
    TX = 'tx'
    RX = 'rx'

class ErrorCode(IntEnum):
    NORMAL=0
    SERIAL_PORT_ERROR=1
    MOTOR_FAILURE=3
    VOLTAGE_OVERLOAD=4
    MOTOR_ERROR=5
    DRY_BURN_ALARM=6
    OVER_TEMPERATURE_PROTECTION=7
    TIMEOUT_PROTECTION=8
    OTHER_ERROR=9

@dataclass(frozen=True)
class Frame:
    raw: bytes
    opcode: int
    sequence: int
    subtype: int
    bitmap: bytes
    payload: bytes
    checksum: int

    def to_dict(self) -> dict:
        return {**unpack(self.raw), 'raw_hex': self.raw.hex(),
                'evidence': Evidence.CONFIRMED_IN_APK.value, 'hardware_verified': False}

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)

def parse_frame(raw: bytes) -> Frame:
    result = unpack(raw)
    return Frame(bytes(raw), int(result['opcode'],16), result['sequence'],
                 result['subtype'], bytes.fromhex(result['bitmap']),
                 bytes.fromhex(result['payload_hex']), result['checksum'])

def _canonical(frame: Frame) -> None:
    if frame.bitmap != b'OB' or frame.subtype != 0:
        raise ProtocolError('typed operational decoder requires OB bitmap and subtype 0; use parse_frame for raw data')

@dataclass(frozen=True)
class OperationCommand:
    frame: Frame
    temperature_level: int
    constant_temperature: int
    speed_level: int
    direction_raw: int
    turbo_lock: int
    function: int
    scale_body: int
    scale_mode: int
    seconds: int
    current_hms: bytes
    appointment_hms: bytes
    light: bytes
    button: int
    remarks: bytes
    legacy: bool

def _seconds(hms: bytes) -> int:
    if hms[1] > 59 or hms[2] > 59:
        raise ProtocolError('invalid HMS minute/second')
    return hms[0]*3600+hms[1]*60+hms[2]

def decode_command(raw: bytes) -> OperationCommand:
    frame = parse_frame(raw); _canonical(frame)
    if frame.opcode not in OPERATION_CODES:
        raise ProtocolError('not an operational command')
    decode(raw, direction='tx')  # shared layout validation
    p=frame.payload
    return OperationCommand(frame,p[2],int.from_bytes(p[3:5],'big'),p[8],p[9],p[10],
                            p[11],p[12],p[13],_seconds(p[17:20]),p[14:17],p[20:23],
                            p[23:25],p[25],p[26:],len(p)==26)

@dataclass(frozen=True)
class Telemetry:
    """All meaningful values plus raw Frame; reserved bytes remain in frame.payload."""
    opcode: int = 0x0802
    firmware_version: int = 0
    state: int = 4
    error: int = 0
    return_code: int = 0
    temperature_level: int = 0
    returned_temperature: int = 0
    actual_temperature: int = 22
    temperature_unit: int = 0
    speed_level: int = 0
    direction_raw: int = 0
    turbo_key: int = 0
    function: int = 0
    weight: int = 0
    weight_format: int = 0
    scale_state: int = 0
    calibration_step: int = 0
    seconds: int = 0
    light: int = 0
    button: int = 0
    frame: Frame | None = None

    def to_dict(self) -> dict:
        result=asdict(self)
        result['frame']=self.frame.to_dict() if self.frame else None
        return result

def _sint(value: int, bits: int, name: str) -> bytes:
    if type(value) is not int or not -(1<<(bits-1)) <= value < (1<<(bits-1)):
        raise ProtocolError(f'{name} must be signed {bits}-bit')
    return value.to_bytes(bits//8,'big',signed=True)

def encode_telemetry(t: Telemetry, *, sequence: int = 1) -> bytes:
    if t.opcode not in OPERATION_CODES:
        raise ProtocolError('unsupported telemetry opcode')
    p=bytearray(39);p[:2]=t.opcode.to_bytes(2,'big')
    p[2:4]=uint(t.firmware_version,16,'firmware').to_bytes(2,'big')
    for index,value,name in ((4,t.state,'state'),(7,t.error,'error'),(8,t.return_code,'return'),
        (18,t.direction_raw,'direction'),(20,t.function,'function'),(21,t.weight_format,'weight format'),
        (26,t.scale_state,'scale state'),(27,t.calibration_step,'calibration'),(37,t.light,'light'),(38,t.button,'button')):
        p[index]=uint(value,8,name)
    p[9:10]=_sint(t.temperature_level,8,'temperature level')
    p[10:12]=_sint(t.returned_temperature,16,'returned temperature')
    p[12:14]=_sint(t.actual_temperature,16,'actual temperature')
    p[14:15]=_sint(t.temperature_unit,8,'unit')
    p[17:18]=_sint(t.speed_level,8,'speed')
    p[19:20]=_sint(t.turbo_key,8,'turbo')
    p[22:26]=_sint(t.weight,32,'weight')
    p[31:34]=timer_bytes(t.seconds)
    return pack(p,sequence=sequence)

def decode_telemetry(raw: bytes) -> Telemetry:
    f=parse_frame(raw);_canonical(f)
    if f.opcode not in OPERATION_CODES:raise ProtocolError('not operational telemetry')
    d=decode(raw)['fields'];p=f.payload
    return Telemetry(f.opcode,d['firmware_version'],d['state_raw'],d['error'],d['return_code'],
        d['temperature_level'],d['returned_temperature'],d['actual_temperature'],d['temperature_unit'],
        d['speed_level'],d['direction_raw'],d['turbo_key'],d['function'],d['weight_raw'],p[21],
        d['scale_state'],d['calibration_step'],_seconds(p[31:34]),d['light_raw'],d['button_raw'],f)

def detect_profile(raw: bytes, *, direction: str = 'rx') -> dict:
    """Detect compatible layout, never infer installed APK version from wire data."""
    f=parse_frame(raw)
    known = f.bitmap==b'OB' and f.subtype==0
    expected = (39,) if direction=='rx' else (26,30)
    if direction not in ('tx','rx'):raise ProtocolError('direction must be tx or rx')
    ota_subs=(1,2,3,4,5,6) if direction=='rx' else (1,2,3,4,6)
    compatible=known and ((f.opcode in OPERATION_CODES and len(f.payload) in expected) or
                         (f.opcode>>8==0xfe and (f.opcode&255) in ota_subs))
    if compatible:
        try:
            if f.opcode in OPERATION_CODES:
                (decode_command if direction=='tx' else decode_telemetry)(raw)
            else:decode(raw,direction=direction)
        except ProtocolError:compatible=False
    return {'compatible_layouts':[PROFILE] if compatible else [], 'version_detected':None,
            'evidence':'INFERRED','hardware_verified':False}
