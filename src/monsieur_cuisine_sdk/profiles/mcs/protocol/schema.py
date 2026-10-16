"""Absolute byte tables for canonical OB envelopes; original factual specification."""
from dataclasses import dataclass, asdict
from .types import parse_frame

@dataclass(frozen=True)
class FieldSpec:
    name: str
    offset: int
    size: int
    encoding: str
    evidence: str='CONFIRMED_IN_APK'

ENVELOPE=(FieldSpec('header',0,1,'AA'),FieldSpec('length',1,2,'u16be; frame size minus 1'),
          FieldSpec('bitmap_size',3,1,'u8'),FieldSpec('bitmap',4,2,'4F42'),
          FieldSpec('subtype',6,1,'u8'),FieldSpec('sequence',7,1,'u8; not guaranteed ACK'))
TX_FIELDS=ENVELOPE+tuple(FieldSpec(*x) for x in (
    ('opcode',8,2,'u16be'),('temperature',10,6,'level:u8,const:u16be,unit:u8,reserved:2'),
    ('motor',16,3,'level:u8,direction:u8,turbo:u8'),('function',19,1,'u8'),
    ('scale',20,2,'body:u8,mode:u8'),('timers',22,9,'current,countdown,appointment; HMS each'),
    ('light',31,2,'type:u8,brightness:u8'),('button',33,1,'u8'),('remarks',34,4,'opaque'),
    ('checksum',38,1,'sum bytes 1..37 modulo 256')))
RX_FIELDS=ENVELOPE+tuple(FieldSpec(*x) for x in (
    ('opcode',8,2,'u16be'),('firmware',10,2,'u16be'),('state',12,3,'bits + 2 reserved'),
    ('error',15,1,'u8'),('return_code',16,1,'u8; semantics UNKNOWN'),
    ('temperature',17,8,'level:s8,returned:s16be,actual:s16be,unit:s8,reserved:2'),
    ('motor',25,3,'level:s8,direction:s8,turbo:s8'),('function',28,1,'u8'),
    ('scale',29,7,'unit/decimals:u8,weight:s32be,state:u8,calibration:u8'),
    ('timers',36,9,'current,countdown,appointment; unsigned HMS each'),
    ('light',45,1,'raw byte; Java signed getter'),('button',46,1,'raw'),
    ('checksum',47,1,'sum bytes 1..46 modulo 256')))

def inspect_frame(raw: bytes, *, direction: str='rx') -> list[dict]:
    f=parse_frame(raw)
    if direction not in ('tx','rx'):raise ValueError('direction must be tx or rx')
    fields=RX_FIELDS if direction=='rx' else TX_FIELDS
    sizes=(48,) if direction=='rx' else (35,39)
    canonical=(f.bitmap==b'OB' and f.subtype==0 and len(raw) in sizes and
               f.opcode in (0x0801,0x0802,0x0803,0x0805))
    rows=[]
    for offset,value in enumerate(raw):
        matches=[x for x in fields if x.offset<=offset<x.offset+x.size] if canonical else []
        if offset==len(raw)-1:
            name='checksum'
        else:name=matches[0].name if matches else 'raw'
        rows.append({'offset':offset,'hex':f'{value:02X}','unsigned':value,
                     'signed':value if value<128 else value-256,'field':name})
    return rows
