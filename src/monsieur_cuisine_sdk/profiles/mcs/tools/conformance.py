"""Portable black-box checks. Pass another encoder callable to check compatibility."""
from __future__ import annotations
import hashlib
from ..protocol import encode_manual, encode_operation, encode_ota, decode, TEMPERATURES

def vectors() -> list[dict]:
    rows=[]
    for i in range(300):
        args={'speed':i%11,'temperature':TEMPERATURES[i%21],'seconds':(i*19)%5941,
              'reverse':bool(i%2),'sequence':i%256}
        rows.append({'kind':'manual','arguments':args,'hex':encode_manual(**args).hex()})
    for i in range(300):
        args={'speed_level':i%21,'temperature_level':i%21,'constant_temperature':i%256,
              'function':(0,1,3,4,5,198)[i%6],'seconds':i*79,'scale_mode':i%2,
              'sequence':i%256,'legacy':bool(i%2),'turbo_lock':i%11,'button':i%7}
        rows.append({'kind':'operation','arguments':args,'hex':encode_operation(**args).hex()})
    for i in range(300):
        sub=(1,2,3,4,6)[i%5]
        data=bytes((i+j)%256 for j in range(16 if sub==1 else i%257 if sub==2 else 0))
        args={'subcommand':sub,'data_hex':data.hex(),'packet_sequence':i*17,'sequence':i%256}
        actual={k:v for k,v in args.items() if k!='data_hex'};actual['data']=data
        rows.append({'kind':'ota','arguments':args,'hex':encode_ota(**actual).hex()})
    return rows

def check_vectors(rows: list[dict], *, manual=encode_manual, operation=encode_operation, ota=encode_ota) -> dict:
    failures=[];digest=hashlib.sha256()
    for index,row in enumerate(rows):
        args=dict(row['arguments'])
        if row['kind']=='ota':args['data']=bytes.fromhex(args.pop('data_hex'))
        try:
            raw={'manual':manual,'operation':operation,'ota':ota}[row['kind']](**args)
            if raw.hex()!=row['hex']:failures.append({'index':index,'reason':'bytes differ'})
            decode(raw,direction='tx');digest.update(raw)
        except (ValueError,TypeError,KeyError) as error:failures.append({'index':index,'reason':str(error)})
    return {'count':len(rows),'passed':not failures,'failures':failures,'sha256':digest.hexdigest(),
            'scope':'synthetic codec conformance; no hardware verification'}
