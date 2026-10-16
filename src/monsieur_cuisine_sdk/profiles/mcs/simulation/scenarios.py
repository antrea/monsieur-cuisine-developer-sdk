"""JSON-only scenarios: ordered inputs, deterministic samples, declarative checks."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import operator
from pathlib import Path
from ..protocol import encode_manual, encode_operation, encode_ota
from .api import DigitalTwin
from .model import ModelParameters
from .limits import MAX_ACTIONS, MAX_SAMPLES, MAX_RECORD_BYTES, SimulationCancelled, seconds_ns, check_work

OPERATORS={'eq':operator.eq,'lt':operator.lt,'le':operator.le,'gt':operator.gt,'ge':operator.ge}

@dataclass
class ScenarioResult:
    twin: DigitalTwin
    samples: list[dict]
    checks: list[dict]

    @property
    def passed(self) -> bool:return all(x['passed'] for x in self.checks)

def run_scenario(scenario: dict | str | Path, *, cancel=None) -> ScenarioResult:
    if isinstance(scenario,(str,Path)):
        path=Path(scenario)
        if path.stat().st_size>MAX_RECORD_BYTES:raise ValueError('scenario exceeds size budget')
        scenario=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(scenario,dict):raise ValueError('scenario must be an object')
    if cancel is not None and not callable(cancel):raise ValueError('cancel must be callable')
    if scenario.get('format_version')!=1:raise ValueError('unsupported scenario format')
    duration=scenario.get('duration',10);period=scenario.get('sample_period',0.2)
    for value in (duration,period):
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('invalid scenario timing')
    if period<=0:raise ValueError('invalid sample period')
    twin=DigitalTwin(seed=scenario.get('seed',0),parameters=ModelParameters(**scenario.get('parameters',{})),record=True)
    check_work(seconds_ns(duration,name='duration'),twin.engine._tick_ns)
    events=scenario.get('events',[])
    if not isinstance(events,list) or len(events)>MAX_ACTIONS:raise ValueError('invalid or excessive scenario events')
    for e in events:
        if not isinstance(e,dict):raise ValueError('scenario event must be an object')
        if type(e.get('at')) not in (int,float) or not math.isfinite(e['at']) or not 0<=e['at']<=duration:
            raise ValueError('event time outside scenario')
    events=sorted(enumerate(events),key=lambda x:(x[1]['at'],x[0]))
    # Validate all known operations and assertions before any physics is evaluated.
    validator=DigitalTwin(seed=scenario.get('seed',0),parameters=twin.engine.parameters)
    for _,event in events:
        action=event.get('action');args=event.get('values',{})
        if not isinstance(args,dict):raise ValueError('scenario values must be an object')
        if action in ('manual','operation','ota'):
            encoder={'manual':encode_manual,'operation':encode_operation,'ota':encode_ota}[action]
            validator.transact(encoder(**args))
        elif action=='hex':
            if not isinstance(event.get('hex'),str) or len(event['hex'])>131072:raise ValueError('invalid scenario HEX')
            validator.transact(bytes.fromhex(event['hex']))
        elif action=='sensors':validator.sensors(**args)
        elif action=='faults':validator.faults(**args);validator.faults()
        elif action=='interrupt':
            if args:raise ValueError('unexpected interrupt arguments')
            validator.interrupt()
        elif action=='ready':
            if args:raise ValueError('unexpected ready arguments')
        else:raise ValueError(f'unsupported scenario action {action}')
    expectations=scenario.get('expect',[])
    if not isinstance(expectations,list) or len(expectations)>MAX_ACTIONS:raise ValueError('invalid or excessive expectations')
    for check in expectations:
        if not isinstance(check,dict) or check.get('field') not in twin.state.snapshot() or check.get('op','eq') not in OPERATORS:
            raise ValueError('unknown scenario assertion')
        if 'value' not in check:raise ValueError('scenario assertion requires value')
    # Integer-nanosecond schedule avoids drift and orders same-time inputs before sampling.
    schedule=[(seconds_ns(e['at'],name='event time'),0,i,e) for i,e in events]
    end=seconds_ns(duration,name='duration');step=seconds_ns(period,name='sample_period')
    if step<1:raise ValueError('sample_period below clock resolution')
    if end//step+1+bool(end%step)>MAX_SAMPLES:raise ValueError('excessive samples after clock rounding')
    schedule += [(t,1,0,None) for t in range(0,end+1,step)]
    if end%step:schedule.append((end,1,0,None))
    samples=[]
    for time_ns,kind,index,event in sorted(schedule,key=lambda x:x[:3]):
        if cancel is not None and cancel():raise SimulationCancelled('scenario cancelled')
        delta=time_ns-twin.engine.clock.nanoseconds
        if delta:twin.advance(delta/1e9,cancel=cancel)
        if kind==1:samples.append(twin.state.snapshot());continue
        action=event['action'];args=event.get('values',{})
        if action in ('manual','operation','ota'):
            encoder={'manual':encode_manual,'operation':encode_operation,'ota':encode_ota}[action]
            twin.transact(encoder(**args))
        elif action=='hex':twin.transact(bytes.fromhex(event['hex']))
        elif action=='sensors':twin.sensors(**args)
        elif action=='faults':twin.faults(**args)
        elif action=='interrupt':twin.interrupt()
        elif action=='ready':twin.receive_ready()
        else:raise ValueError(f'unsupported scenario action {action}')
    checks=[];state=twin.state.snapshot()
    for check in expectations:
        field=check['field'];op=check.get('op','eq')
        if field not in state or op not in OPERATORS:raise ValueError('unknown scenario assertion')
        actual=state[field];passed=OPERATORS[op](actual,check['value'])
        checks.append({**check,'actual':actual,'passed':passed})
    return ScenarioResult(twin,samples,checks)

def demo_scenario() -> dict:
    return {'format_version':1,'name':'Synthetic reversal and tare','seed':7,'duration':8,
        'events':[{'at':0,'action':'manual','values':{'speed':4,'temperature':60,'seconds':30}},
                  {'at':2,'action':'sensors','values':{'mass':450}},
                  {'at':3,'action':'operation','values':{'opcode':0x0803,'scale_mode':1}},
                  {'at':4,'action':'manual','values':{'speed':3,'reverse':True,'seconds':30}},
                  {'at':7,'action':'operation','values':{'function':0}}],
        'expect':[{'field':'actual_level','value':0},{'field':'weight','value':0}]}
