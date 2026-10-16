"""Independent, original offline codec. Importing this package never loads Tk."""
from ._baseline import (TEMPERATURES, ERRORS, FUNCTIONS, OPERATION_CODES,
                       ProtocolError, Sequence, pack, unpack, timer_bytes,
                       encode_operation, encode_manual, encode_ota, decode as _decode, uint)
from .types import (Evidence, Direction, ErrorCode, Frame, OperationCommand,
                    Telemetry, parse_frame, decode_command, decode_telemetry,
                    encode_telemetry, detect_profile, PROFILE)
from .stream import StreamParser
from .schema import TX_FIELDS, RX_FIELDS, inspect_frame

def decode(frame: bytes, *, direction: str='rx') -> dict:
    result=_decode(frame,direction=direction)
    result['evidence']='CONFIRMED_IN_APK'
    return result

__all__ = [name for name in globals() if not name.startswith('_')]
