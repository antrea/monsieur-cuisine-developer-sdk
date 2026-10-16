"""Local parser/headless/native-GUI measurements; reports observations, no targets.

Each sample uses a new process. Python allocation peaks are tracemalloc values,
not process RSS. Timing includes allocation tracking overhead. GUI requires Tk
and a display; process wall time additionally includes interpreter startup.
"""
from __future__ import annotations
import argparse
import gc
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc


def peak_rss():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        values = Counters();values.cb = ctypes.sizeof(values)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        return values.PeakWorkingSetSize if query(current(), ctypes.byref(values), values.cb) else None
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform == 'darwin' else value*1024
    except ImportError:return None


def worker(kind, model, count):
    tracemalloc.start()
    started = time.perf_counter()
    from monsieur_cuisine_sdk import DigitalTwin
    twin = DigitalTwin(model, record=False)
    units = 1
    if kind == 'parser':
        from monsieur_cuisine_sdk.framing import SelectedStream
        parser = SelectedStream(model)
        raw = twin.profile.encode_start(3, 'cw', 60)
        units = count*32
        decoded = 0
        for _ in range(count):decoded += len(parser.feed(raw*32))
        assert decoded == units
    elif kind == 'headless':
        units = count
        twin.start_motor(3, 'cw', 60)
        for _ in range(count):twin.advance(.02);twin.sample()
    else:
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        root = tk.Tk();app = DesktopApp(root, twin);app.running = False
        root.update_idletasks();root.update()
        first_paint = time.perf_counter()-started
        app.close();app=root=None;gc.collect()
    elapsed = time.perf_counter()-started
    _, peak = tracemalloc.get_traced_memory();tracemalloc.stop()
    return {'kind': kind, 'model': model, 'units': units, 'seconds': elapsed,
            'units_per_second': units/elapsed, 'first_paint_seconds': first_paint if kind == 'gui' else None,
            'python_alloc_peak_bytes': peak, 'process_peak_rss_bytes': peak_rss()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json', type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--count', type=int, default=300)
    parser.add_argument('--no-gui', action='store_true')
    parser.add_argument('--worker', choices=('parser','headless','gui'))
    parser.add_argument('--model', choices=('mcc','mcs'), default='mcc')
    args = parser.parse_args(argv)
    if not 1<=args.repeat<=10 or not 1<=args.count<=10000:raise ValueError('repeat1..10 and count1..10000 required')
    if args.worker:
        print(json.dumps(worker(args.worker,args.model,args.count)));return 0
    environment = dict(os.environ);environment['PYTHONPATH'] = str(args.root.resolve()/'src')
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    rows = []
    for kind in (('parser','headless') if args.no_gui else ('parser','headless','gui')):
        for model in ('mcc','mcs'):
            samples = []
            for _ in range(args.repeat):
                started = time.perf_counter()
                completed = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',kind,
                    '--model',model,'--count',str(args.count)],cwd=args.root.parent,env=environment,capture_output=True,text=True,timeout=120)
                if completed.returncode:raise ValueError(f'{kind}/{model} failed: '+completed.stderr)
                result = json.loads(completed.stdout);result['process_wall_seconds'] = time.perf_counter()-started
                samples.append(result)
            rows.append({'kind':kind,'model':model,'samples':samples,
                         'median_seconds':statistics.median(row['seconds'] for row in samples),
                         'median_units_per_second':statistics.median(row['units_per_second'] for row in samples),
                         'median_first_paint_seconds':statistics.median(row['first_paint_seconds'] for row in samples) if kind=='gui' else None,
                         'median_process_wall_seconds':statistics.median(row['process_wall_seconds'] for row in samples)})
    report = {'python':platform.python_version(),'platform':platform.platform(),'repeat':args.repeat,'count':args.count,
              'measurements':rows,'qualification':'local observations; tracemalloc overhead included; Python allocation peak != process peak RSS; no threshold or cross-platform performance claim'}
    if args.json:
        args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
