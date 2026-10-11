"""Passive constructor/fit observer; no replaced methods or fabricated values."""

import json
import os
from pathlib import Path
import runpy
import sys


records = []


def observe(frame, event, argument):
    if event != 'call' or frame.f_code.co_name not in ['__init__', 'fit', 'fit_transform']:
        return
    instance = frame.f_locals.get('self')
    if instance is not None and type(instance).__name__ in ['PyNNDescentTransformer', 'KNeighborsTransformer']:
        records.append({'class': type(instance).__name__, 'method': frame.f_code.co_name,
                        'source': frame.f_code.co_filename})


target = sys.argv[1]
sys.argv = [target, *sys.argv[2:]]
sys.setprofile(observe)
try:
    runpy.run_path(target, run_name='__main__')
finally:
    sys.setprofile(None)
    Path(os.environ['BACKEND_TRACE_PATH']).write_text(json.dumps({'observations': records,
        'passive_profile_no_replaced_methods_or_fabricated_results': True, 'G0': False}, indent=2)+'\n')
