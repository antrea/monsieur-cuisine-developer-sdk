"""In-memory developer facade and portable deterministic recording/replay."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
from .model import ModelParameters, SimulationEngine
from .board import MCSVirtualPowerBoard
from .limits import MAX_ACTIONS, MAX_RECORD_BYTES, seconds_ns, check_work

class DigitalTwin:
    def __init__(self, *, seed: int=0, parameters: ModelParameters | None=None, record: bool=False):
        self.engine=SimulationEngine(parameters,seed=seed)
        self.board=MCSVirtualPowerBoard(self.engine)
        self.recording={'format_version':1,'seed':seed,'parameters':asdict(self.engine.parameters),
                        'synthetic':True,'actions':[]}
        self.record=record

    @property
    def state(self):return self.engine.state

    def _record(self, kind: str, arguments: dict, result=None) -> None:
        if self.record:self.recording['actions'].append({'kind':kind,'arguments':arguments,'result':result})

    def transact(self, request: bytes) -> bytes | None:
        result=self.board.transact(request)
        self._record('tx',{'hex':request.hex()},result.hex() if result is not None else None)
        return result

    def advance(self, seconds: float, *, cancel=None) -> dict:
        result=self.engine.advance(seconds,cancel=cancel)
        self._record('advance',{'seconds':seconds},result)
        return result

    def sensors(self, **values) -> None:
        self.engine.sensors(**values);self._record('sensors',values)

    def faults(self, **values) -> None:
        self.board.faults(**values);self._record('faults',values)

    def interrupt(self) -> None:
        self.engine.interrupt();self.board.pending.clear();self._record('interrupt',{})

    def disarm(self) -> None:
        """Synthetic session handoff: stop targets and discard delayed old replies."""
        self.engine.stop();self.board.pending.clear();self._record('disarm',{})

    def receive_ready(self) -> list[bytes]:
        result=self.board.ready();self._record('ready',{},[x.hex() for x in result]);return result

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.recording,indent=2),encoding='utf-8')

class InMemoryTransport:
    """Frame-oriented adapter, no OS device, socket or background thread."""
    def __init__(self, twin: DigitalTwin):self.twin=twin
    def exchange(self, frame: bytes) -> bytes | None:return self.twin.transact(frame)

def replay(recording: dict, *, compare: bool=True) -> DigitalTwin:
    """Replay validated local input data with a finite total physics-work budget."""
    if not isinstance(recording,dict):raise ValueError('recording must be an object')
    if recording.get('format_version')!=1:raise ValueError('unsupported recording format')
    actions=recording.get('actions')
    if not isinstance(actions,list) or len(actions)>MAX_ACTIONS:raise ValueError('invalid or excessive recording actions')
    try:encoded=json.dumps(recording,allow_nan=False)
    except (TypeError,ValueError) as error:raise ValueError('recording must contain finite JSON data') from error
    if len(encoded.encode('utf-8'))>MAX_RECORD_BYTES:raise ValueError('recording exceeds size budget')
    parameters=ModelParameters(**recording['parameters'])
    validator=DigitalTwin(seed=recording['seed'],parameters=parameters)
    total_ns=0;interrupted=False
    for action in actions:
        if not isinstance(action,dict) or not isinstance(action.get('arguments'),dict):raise ValueError('invalid recording action')
        kind=action.get('kind');args=action['arguments']
        if kind=='advance':
            if set(args)!={'seconds'}:raise ValueError('invalid advance arguments')
            total_ns+=seconds_ns(args['seconds']);check_work(total_ns,validator.engine._tick_ns)
        elif kind=='tx':
            if set(args)!={'hex'} or not isinstance(args['hex'],str) or len(args['hex'])>131072:raise ValueError('invalid TX data')
            if interrupted:raise ValueError('TX after interrupted recording session')
            validator.transact(bytes.fromhex(args['hex']))
        elif kind=='sensors':validator.sensors(**args)
        elif kind=='faults':validator.board.faults(**args)  # validate then remove faults before checking later TX
        elif kind in ('interrupt','disarm','ready'):
            if args:raise ValueError('unexpected action arguments')
            if kind=='interrupt':interrupted=True
        else:raise ValueError(f'unknown recording action {kind}')
        validator.board.faults()
    twin=DigitalTwin(seed=recording['seed'],parameters=ModelParameters(**recording['parameters']))
    for index,action in enumerate(recording['actions']):
        kind=action['kind'];args=action['arguments']
        if kind=='tx':
            rx=twin.transact(bytes.fromhex(args['hex']));result=rx.hex() if rx is not None else None
        elif kind=='advance':result=twin.advance(**args)
        elif kind=='sensors':result=twin.sensors(**args)
        elif kind=='faults':result=twin.faults(**args)
        elif kind=='interrupt':result=twin.interrupt()
        elif kind=='disarm':result=twin.disarm()
        elif kind=='ready':result=[x.hex() for x in twin.receive_ready()]
        else:raise ValueError(f'unknown recording action {kind}')
        if compare and result!=action.get('result'):raise ValueError(f'replay mismatch at action {index} ({kind})')
    return twin
