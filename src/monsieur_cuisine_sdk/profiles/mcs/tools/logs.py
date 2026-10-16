"""Offline JSONL chunk logs. No serial port is opened."""
from __future__ import annotations
from ..protocol import StreamParser, decode, ProtocolError

def analyze_records(records: list[dict]) -> dict:
    parsers={d:StreamParser() for d in ('tx','rx')};frames=[];anomalies=[];last={}
    last_time=-float('inf')
    for index,record in enumerate(records):
        direction=record.get('direction','rx');time=float(record.get('time',index))
        if direction not in parsers:raise ValueError('direction must be tx or rx')
        if time<last_time:anomalies.append({'record':index,'kind':'nonmonotonic_time'})
        last_time=time;p=parsers[direction]
        found=p.expire(now=time)+p.feed(bytes.fromhex(record['hex']),now=time)
        for raw in found:
            try:decoded=decode(raw,direction=direction)
            except ProtocolError as error:
                anomalies.append({'record':index,'kind':'layout','message':str(error)});continue
            seq=decoded['sequence']
            if direction in last:
                previous=last[direction];expected=(previous+1)&255
                if expected==0x66:expected=0x67
                if seq==previous:kind='repeated_sequence'
                elif seq!=expected:kind='sequence_gap_or_independent_counter'
                else:kind=None
                if kind:anomalies.append({'record':index,'kind':kind,'direction':direction,'previous':previous,'sequence':seq})
            last[direction]=seq
            fields=decoded['fields']
            if 'speed_level' in fields and not 0<=fields['speed_level']<=20:
                anomalies.append({'record':index,'kind':'motor_level_outside_studied_range'})
            if fields.get('error_name')=='UNKNOWN':anomalies.append({'record':index,'kind':'unknown_error_code'})
            frames.append({'time':time,'hex':raw.hex(),**decoded})
    diagnostics={}
    for direction,p in parsers.items():
        p.finish();diagnostics[direction]=list(p.errors)
    return {'frames':frames,'anomalies':anomalies,'stream_diagnostics':diagnostics,
            'sequence_caveat':'Repeated values and gaps are diagnostics, not proven loss or ACK behavior.'}

def telemetry_rows(analysis: dict) -> list[dict]:
    rows=[]
    for frame in analysis['frames']:
        if frame['direction']!='rx' or 'actual_temperature' not in frame['fields']:continue
        f=frame['fields']
        rows.append({'time':frame['time'],'level':f['speed_level'],'temperature':f['actual_temperature'],
                     'weight':f['weight_raw'],'error':f['error'],'sequence':frame['sequence']})
    return rows
