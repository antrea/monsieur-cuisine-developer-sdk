"""Recovery parser with bounded diagnostics and explicit interrupted-stream finish."""
from collections import deque
from ._baseline import StreamParser as BaselineParser

class StreamParser(BaselineParser):
    def __init__(self, *, max_frame: int=4096, timeout: float=1.0, max_errors: int=1024):
        super().__init__(max_frame=max_frame,timeout=timeout)
        if type(max_errors) is not int or max_errors<1:raise ValueError('max_errors must be positive')
        self.errors=deque(maxlen=max_errors)

    def finish(self) -> bytes:
        """Return and discard incomplete tail at end of recording/session."""
        tail=bytes(self.buffer)
        if tail:self.errors.append({'kind':'interrupted','count':len(tail)})
        self.buffer.clear();self.since=None
        return tail
