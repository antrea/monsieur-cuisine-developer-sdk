"""Offline MCS 1.2.14.15 protocol analysis. No I/O to hardware or network.

Format derived from MultoSerialPortCommand, MCCommandSetting and OperationStruct.
The simulator produces synthetic examples; it does not emulate controller firmware.
"""
from __future__ import annotations
import argparse
import json
import math
from dataclasses import dataclass

TEMPERATURES=(0,37,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130)
ERRORS={0:'NORMAL',1:'SERIAL_PORT_ERROR',3:'MOTOR_FAILURE',4:'VOLTAGE_OVERLOAD',
        5:'MOTOR_ERROR',6:'DRY_BURN_ALARM',7:'OVER_TEMPERATURE_PROTECTION',
        8:'TIMEOUT_PROTECTION',9:'OTHER_ERROR'}
FUNCTIONS={0:'stop',1:'manual_or_ramp_or_rice',3:'steam_or_kettle',4:'roast',5:'knead',
           6:'short_cleaning',7:'long_cleaning',8:'egg',9:'sous_vide',10:'slow_cook',
           11:'fermentation',12:'puree',13:'smoothie',15:'sleep',198:'turbo'}
OPERATION_CODES={0x0801,0x0802,0x0803,0x0805}

class ProtocolError(ValueError):
    pass

def uint(value:int,bits:int,name:str)->int:
    if type(value) is not int or not 0<=value<(1<<bits):
        raise ProtocolError(f'{name} must be an unsigned {bits}-bit integer')
    return value

def pack(payload:bytes,*,sequence:int=1,subtype:int=0,bitmap:bytes=b'OB')->bytes:
    """Serialize envelope; length excludes AA, includes checksum."""
    uint(sequence,8,'sequence');uint(subtype,8,'subtype')
    if len(payload)<2:raise ProtocolError('payload must include a two-byte opcode')
    if not 1<=len(bitmap)<=255:raise ProtocolError('bitmap size must be 1..255')
    body=bytes([len(bitmap)])+bytes(bitmap)+bytes([subtype,sequence])+bytes(payload)
    size=len(body)+3
    uint(size,16,'length')
    protected=size.to_bytes(2,'big')+body
    return b'\xaa'+protected+bytes([sum(protected)&255])

@dataclass
class Sequence:
    """One serializer counter. Legacy and Multo serializers have separate counters."""
    value:int=0
    def next(self)->int:
        uint(self.value,8,'counter')
        self.value=(self.value+1)&255
        if self.value==0x66:self.value=0x67
        return self.value

def unpack(frame:bytes)->dict:
    frame=bytes(frame)
    if len(frame)<4:raise ProtocolError('incomplete envelope')
    if frame[0]!=0xaa:raise ProtocolError('invalid header')
    size=int.from_bytes(frame[1:3],'big')
    if len(frame)!=size+1:raise ProtocolError('declared length mismatch')
    if (sum(frame[1:-1])&255)!=frame[-1]:raise ProtocolError('checksum mismatch')
    bitmap_size=frame[3]
    start=6+bitmap_size
    if not bitmap_size or len(frame)<start+3:raise ProtocolError('bitmap/payload bounds')
    payload=frame[start:-1]
    return {'length':size,'frame_size':len(frame),'bitmap':frame[4:4+bitmap_size].hex(),
            'subtype':frame[4+bitmap_size],'sequence':frame[5+bitmap_size],
            'opcode':f'{int.from_bytes(payload[:2],"big"):04X}',
            'payload_hex':payload.hex(),'checksum':frame[-1]}

def timer_bytes(seconds:int)->bytes:
    uint(seconds,32,'seconds')
    if seconds>255*3600+3599:raise ProtocolError('timer hour overflow')
    return bytes([seconds//3600,(seconds//60)%60,seconds%60])

def encode_operation(*,opcode:int=0x0802,speed_level:int=0,reverse:bool=False,
                     temperature_level:int=0,constant_temperature:int=0,
                     function:int=0,seconds:int=0,scale_mode:int=0,
                     sequence:int=1,legacy:bool=False,turbo_lock:int=0,button:int=0)->bytes:
    """Offline field encoder, not a validation of hardware-safe combinations.

    Legacy sleep/turbo frames have no four-byte Remarks field. Constant-temperature
    high byte reproduces the APK's (byte)(temperature << 8), i.e. zero.
    """
    uint(opcode,16,'opcode')
    if opcode not in OPERATION_CODES:raise ProtocolError('unsupported operation opcode')
    if type(reverse) is not bool:raise ProtocolError('reverse must be bool')
    if type(speed_level) is not int or not 0<=speed_level<=20:raise ProtocolError('speed level must be 0..20')
    if type(temperature_level) is not int or not 0<=temperature_level<len(TEMPERATURES):raise ProtocolError('temperature level must be 0..20')
    for value,name in ((function,'function'),(scale_mode,'scale mode'),(turbo_lock,'turbo lock'),(button,'button')):uint(value,8,name)
    uint(constant_temperature,8,'constant temperature')
    temperature=bytes([temperature_level,0,constant_temperature,0,0,0])
    motor=bytes([speed_level,int(reverse),turbo_lock])
    timers=b'\0'*3+timer_bytes(seconds)+b'\0'*3
    payload=(opcode.to_bytes(2,'big')+temperature+motor+bytes([function,0,scale_mode])+
             timers+b'\0\0'+bytes([button])+(b'' if legacy else b'\0'*4))
    return pack(payload,sequence=sequence)

def encode_manual(*,speed:int=0,temperature:int=0,seconds:int=0,reverse:bool=False,sequence:int=1)->bytes:
    if type(speed) is not int or not 0<=speed<=10:raise ProtocolError('UI speed must be 0..10')
    if type(temperature) is not int or temperature not in TEMPERATURES:raise ProtocolError('temperature absent from APK manual levels')
    uint(seconds,32,'seconds')
    if not 0<=seconds<=5940:raise ProtocolError('manual time outside extracted 0..5940 s range')
    return encode_operation(speed_level=speed*2,temperature_level=TEMPERATURES.index(temperature),
                            function=1,seconds=seconds,reverse=reverse,sequence=sequence)

def encode_ota(subcommand:int,*,data:bytes=b'',packet_sequence:int=0,sequence:int=1)->bytes:
    """Serialize documented OTA messages offline. No firmware is interpreted."""
    uint(subcommand,8,'subcommand')
    if subcommand==1:
        if len(data)!=16:raise ProtocolError('OTA init requires exactly 16 metadata bytes')
        tail=bytes(data)
    elif subcommand==2:
        if len(data)>256:raise ProtocolError('OTA segment exceeds 256 bytes')
        uint(packet_sequence,16,'OTA sequence')
        tail=packet_sequence.to_bytes(2,'big')+bytes(data).ljust(256,b'\0')
    elif subcommand in (3,4,6):
        if data:raise ProtocolError('OTA query/confirm has no metadata payload')
        tail=b''
    else:raise ProtocolError('unsupported outbound OTA subcommand')
    return pack(bytes([0xfe,subcommand])+tail,sequence=sequence)

def decode(frame:bytes,*,direction:str='rx')->dict:
    if direction not in ('rx','tx'):raise ProtocolError('direction must be rx or tx')
    result=unpack(frame)
    result.update({'direction':direction,'evidence':'CONFIRMED IN APK',
                   'evidence_scope':'Envelope and explicitly decoded fields only','hardware_verified':False})
    payload=bytes.fromhex(result['payload_hex']);opcode=int(result['opcode'],16)
    result['fields']={}
    if result['bitmap']!='4f42' or result['subtype']!=0:
        result['limitations']=['Unsupported bitmap/subtype: only envelope decoded; payload remains opaque.']
        result['semantics']='UNKNOWN'
        return result
    fields=result['fields']
    if opcode in OPERATION_CODES:
        if direction=='tx':
            if len(payload) not in (26,30):raise ProtocolError('operation TX payload must be 26 (legacy) or 30 bytes')
            fields.update({'temperature_level':payload[2],'constant_temperature_raw':int.from_bytes(payload[3:5],'big'),
                           'temperature_unit':payload[5],'speed_level':payload[8],'reverse_raw':payload[9],
                           'turbo_lock':payload[10],'function':payload[11],'scale_mode':payload[13],
                           'countdown_hms':list(payload[17:20]),'legacy_no_remarks':len(payload)==26})
            fields['function_name']=FUNCTIONS.get(fields['function'],'UNKNOWN')
        else:
            if len(payload)!=39:raise ProtocolError('OperationStruct RX payload must be 39 bytes')
            state=payload[4];weight=int.from_bytes(payload[22:26],'big',signed=True)
            signed=lambda b:b if b<128 else b-256
            fields.update({'firmware_version':int.from_bytes(payload[2:4],'big'),
                           'state_raw':state,'state_remarks':payload[5:7].hex(),
                           'lid_open':bool(state&0x80),'cup_ntc_absent':bool(state&0x40),
                           'temperature_hl_bit':bool(state&0x20),'motor_clockwise_bit':bool(state&8),
                           'scale_stable_bit':bool(state&4),'error':payload[7],
                           'error_name':ERRORS.get(payload[7],'UNKNOWN'),'return_code':payload[8],
                           'temperature_level':signed(payload[9]),'temperature_level_raw':payload[9],
                           'returned_temperature':int.from_bytes(payload[10:12],'big',signed=True),
                           'actual_temperature':int.from_bytes(payload[12:14],'big',signed=True),
                           'temperature_unit':signed(payload[14]),'temperature_unit_raw':payload[14],
                           'speed_level':signed(payload[17]),'speed_level_raw':payload[17],
                           'ui_speed':int(signed(payload[17])/2),'direction_raw':payload[18],
                           'direction_signed':signed(payload[18]),
                           'turbo_key':signed(payload[19]),'turbo_key_raw':payload[19],'function':payload[20],
                           'weight_raw':weight,'weight_decimal_point':payload[21]&15,'weight_unit':payload[21]>>4,
                           'scale_state':payload[26],'calibration_step':payload[27],
                           'countdown_hms':list(payload[31:34]),'light_raw':payload[37],'button_raw':payload[38]})
            fields['countdown_ms']=sum(x*y for x,y in zip(fields['countdown_hms'],(3600000,60000,1000)))
            result['limitations']=['No RPM conversion demonstrated; bit polarities represent APK interpretation, not electrical measurements.']
    elif opcode>>8==0xfe:
        sub=opcode&255
        if direction=='tx':
            required={1:18,2:260,3:2,4:2,6:2}.get(sub)
            if required is None:
                result['semantics']='UNKNOWN';result['limitations']=['Unknown OTA opcode; envelope decoded and payload preserved only.']
            if required is not None and len(payload)!=required:raise ProtocolError('OTA TX payload size mismatch')
            if sub==1:fields['metadata_hex']=payload[2:].hex()
            elif sub==2:fields.update({'packet_sequence':int.from_bytes(payload[2:4],'big'),'segment_hex':payload[4:].hex()})
        else:
            required={1:3,2:4,3:19,4:3,5:5,6:5}.get(sub)
            if required is None:
                result['semantics']='UNKNOWN';result['limitations']=['Unknown OTA opcode; envelope decoded and payload preserved only.']
            if required is not None and len(payload)!=required:raise ProtocolError('OTA RX payload size mismatch')
            if sub==2:fields['packet_sequence']=int.from_bytes(payload[2:4],'big')
            elif sub in (1,3,4,5,6):fields['return_code']=payload[2]
            if sub in (5,6):fields['version']=int.from_bytes(payload[3:5],'big')
            if sub==3:fields['metadata_hex']=payload[3:].hex()
    else:
        result['semantics']='UNKNOWN'
        result['limitations']=['Opcode semantic decoder not implemented; payload preserved verbatim.']
    return result

class StreamParser:
    """Bounded offline stream parser. expire() resolves incomplete-frame ambiguity.

    A plausible incomplete prefix is retained until explicit timeout. This avoids
    mistaking embedded AA/payload bytes for a new frame.
    """
    def __init__(self,*,max_frame:int=4096,timeout:float=1.0):
        if type(max_frame) is not int or not 10<=max_frame<=65536:raise ValueError('max_frame must be an integer in 10..65536')
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:raise ValueError('timeout must be finite and positive')
        self.max_frame=max_frame;self.timeout=timeout;self.buffer=bytearray();self.errors=[];self.since=None
    def feed(self,data:bytes,*,now:float=0.0)->list[bytes]:
        if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('stream time must be finite numeric')
        if not isinstance(data,(bytes,bytearray,memoryview)):raise ValueError('stream data must be bytes-like')
        if len(data)>4096:
            frames=[]
            for offset in range(0,len(data),4096):frames.extend(self.feed(data[offset:offset+4096],now=now))
            return frames
        self.buffer.extend(data);frames=[]
        while self.buffer:
            if self.buffer[0]!=0xaa:
                try:n=self.buffer.index(0xaa)
                except ValueError:n=len(self.buffer)
                del self.buffer[:n];self.errors.append({'kind':'noise','count':n});self.since=None
                continue
            if self.since is None:self.since=now
            if len(self.buffer)<3:break
            total=int.from_bytes(self.buffer[1:3],'big')+1
            if total<10 or total>self.max_frame:
                del self.buffer[0];self.errors.append({'kind':'length','declared':total});self.since=None;continue
            if len(self.buffer)<total:break
            candidate=bytes(self.buffer[:total])
            try:unpack(candidate)
            except ProtocolError as error:
                del self.buffer[0];self.errors.append({'kind':'corrupt','reason':str(error)});self.since=None;continue
            frames.append(candidate);del self.buffer[:total];self.since=None
        return frames
    def expire(self,*,now:float)->list[bytes]:
        if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('stream time must be finite numeric')
        if self.buffer and self.since is not None and now-self.since>=self.timeout:
            del self.buffer[0];self.since=None;self.errors.append({'kind':'timeout'})
        return self.feed(b'',now=now)

class SyntheticBoard:
    """Simplified deterministic demonstration, never a firmware/safety model."""
    def __init__(self):
        self.last_command=None;self.error=0;self.weight=0;self.temperature=20;self.sequence=Sequence()
    def transact(self,request:bytes,*,drop_response:bool=False)->bytes|None:
        parsed=decode(request,direction='tx');opcode=int(parsed['opcode'],16)
        if opcode not in OPERATION_CODES:raise ProtocolError('simulator supports operation commands only')
        self.last_command=parsed
        if drop_response:return None
        fields=parsed['fields'];payload=bytearray(39)
        payload[:2]=opcode.to_bytes(2,'big');payload[2:4]=(3069).to_bytes(2,'big')
        payload[7]=uint(self.error,8,'synthetic error');payload[9]=fields['temperature_level']
        payload[12:14]=int(self.temperature).to_bytes(2,'big',signed=True)
        stopped=fields['function']==0
        payload[17]=0 if stopped else fields['speed_level'];payload[18]=fields['reverse_raw'];payload[20]=fields['function']
        payload[22:26]=int(self.weight).to_bytes(4,'big',signed=True)
        payload[31:34]=bytes(fields['countdown_hms'])
        return pack(payload,sequence=self.sequence.next())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hex_frame',nargs='?');parser.add_argument('--direction',choices=('rx','tx'),default='rx')
    parser.add_argument('--demo',action='store_true')
    args=parser.parse_args()
    if args.demo:
        request=encode_manual(speed=2,temperature=60,seconds=90)
        response=SyntheticBoard().transact(request)
        output={'synthetic':True,'tx':decode(request,direction='tx'),'rx':decode(response)}
    elif args.hex_frame:output=decode(bytes.fromhex(args.hex_frame),direction=args.direction)
    else:parser.error('provide a hexadecimal frame or --demo')
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
