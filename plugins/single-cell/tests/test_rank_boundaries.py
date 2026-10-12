import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from rank_fixtures import fixture


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/rank_genes_groups.py'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--source-script', type=Path, default=SCRIPT)
    parser.add_argument('--case', action='append')
    arguments = parser.parse_args()
    cases = ['duplicate-cells', 'duplicate-genes', 'empty-cell-ID', 'empty-gene-ID', 'missing-groupby', 'missing-label', 'singleton', 'one-group', 'absent-reference', 'bad-method', 'zero-n-genes', 'noninteger-n-genes', 'selected-X-NaN', 'selected-X-infinity', 'selected-X-none', 'noncanonical-sparse', 'stale-marker', 'stale-report', 'stale-H5AD', 'dangling-output', 'alias-outputs', 'input-overwrite', 'blocked-parent', 'H5-write-fault', 'third-link-fault', 'input-mutation']
    cases.append('replacement-symlink-rollback')
    if arguments.case:
        assert set(arguments.case) <= set(cases)
        cases = [name for name in cases if name in arguments.case]
    results = []
    for name in cases:
        directory = arguments.evidence / name
        directory.mkdir(parents=True)
        data = fixture()
        groupby, method, reference, requested = 'group', 't-test', 'rest', '100'
        if name == 'duplicate-cells':
            data.obs_names = ['same'] * data.n_obs
        if name == 'duplicate-genes':
            data.var_names = ['same'] * data.n_vars
        if name == 'empty-cell-ID':
            data.obs_names = [''] + data.obs_names.tolist()[1:]
        if name == 'empty-gene-ID':
            data.var_names = [''] + data.var_names.tolist()[1:]
        if name == 'missing-groupby':
            groupby = 'absent'
        if name == 'missing-label':
            data.obs['group'] = data.obs['group'].astype(object)
            data.obs.iloc[0, data.obs.columns.get_loc('group')] = None
        if name == 'singleton':
            data.obs['group'] = pd.Categorical(['one'] + ['many'] * 35)
        if name == 'one-group':
            data.obs['group'] = pd.Categorical(['one'] * 36)
        if name == 'absent-reference':
            reference = 'absent'
        if name == 'bad-method':
            method = 'unsupported'
        if name == 'zero-n-genes':
            requested = '0'
        if name == 'noninteger-n-genes':
            requested = '1.5'
        if name == 'selected-X-NaN':
            data.X[-1, -1] = np.nan
        if name == 'selected-X-infinity':
            data.X[-1, -1] = np.inf
        if name == 'selected-X-none':
            data.raw = data.copy()
            data.X = None
        if name == 'noncanonical-sparse':
            rows = np.arange(36)
            data.X = sp.coo_matrix((np.ones(72), (np.repeat(rows, 2), np.zeros(72, dtype=int))), shape=data.shape).tocsr()
            data.X = sp.csr_matrix((np.ones(72), np.zeros(72, dtype=int), np.arange(0, 73, 2)), shape=data.shape)
        source = directory / 'input.h5ad'
        data.write_h5ad(source)
        outputs = [directory / name for name in ['markers.parquet', 'report.json', 'output.h5ad']]
        old = {}
        if name.startswith('stale-'):
            position = {'stale-marker': 0, 'stale-report': 1, 'stale-H5AD': 2}[name]
            outputs[position].write_bytes(b'PREVIOUS_RESULT')
            old[str(outputs[position])] = outputs[position].read_bytes()
        if name == 'dangling-output':
            outputs[0].symlink_to('not-created')
        if name == 'alias-outputs':
            outputs[2] = outputs[0]
        if name == 'input-overwrite':
            outputs[2] = source
            old[str(source)] = source.read_bytes()
        if name == 'blocked-parent':
            blocked = directory / 'blocked'
            blocked.write_bytes(b'NOT_A_DIRECTORY')
            outputs[2] = blocked / 'output.h5ad'
        env = dict(os.environ, SC_P_STR_GROUPBY=groupby, SC_P_STR_METHOD=method, SC_P_STR_REFERENCE=reference, SC_P_INT_N_GENES=requested)
        env['AUTONOMICS_INPUT0'] = str(source)
        env.update({f'AUTONOMICS_OUTPUT{position}': str(path) for position, path in enumerate(outputs)})
        if name in {'H5-write-fault', 'third-link-fault', 'input-mutation', 'replacement-symlink-rollback'}:
            driver = directory / 'inject.py'
            code = "import importlib.util,os\ns=importlib.util.spec_from_file_location('subject'," + repr(str(arguments.source_script)) + ")\nm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
            if name == 'H5-write-fault':
                code += "def fault(*args,**kwargs): raise OSError('injected H5 write failure')\nm.ad.AnnData.write_h5ad=fault\n"
            elif name == 'third-link-fault':
                code += "original=m.os.link\ncalls=0\ndef fault(*args,**kwargs):\n global calls\n calls+=1\n if calls==3: raise OSError('injected third-link failure')\n return original(*args,**kwargs)\nm.os.link=fault\n"
            elif name == 'replacement-symlink-rollback':
                code += "original=m.os.link\ncalls=0\nfirst=None\ndef fault(*args,**kwargs):\n global calls,first\n calls+=1\n if calls==1: first=args\n if calls==3:\n  os.unlink(first[1])\n  os.symlink(first[0],first[1])\n  raise OSError('injected replacement-symlink rollback')\n return original(*args,**kwargs)\nm.os.link=fault\n"
            else:
                code += "original=m.ad.AnnData.write_h5ad\ndef fault(*args,**kwargs):\n result=original(*args,**kwargs)\n with open(os.environ['AUTONOMICS_INPUT0'],'ab') as stream: stream.write(b'MUTATED')\n return result\nm.ad.AnnData.write_h5ad=fault\n"
            driver.write_text(code + 'm.run()\n')
            command = [sys.executable, str(driver)]
        else:
            command = [sys.executable, str(arguments.source_script)]
        process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
        (directory / 'stdout.txt').write_text(process.stdout)
        (directory / 'stderr.txt').write_text(process.stderr)
        (directory / 'exit.txt').write_text(str(process.returncode) + '\n')
        assert process.returncode != 0, name
        for path, content in old.items():
            assert Path(path).read_bytes() == content
        if name == 'replacement-symlink-rollback':
            assert outputs[0].is_symlink(), 'rollback deleted a replacement link not owned by this execution'
        for path in outputs:
            if str(path) in old or (name in {'dangling-output', 'replacement-symlink-rollback'} and path == outputs[0]):
                continue
            assert not os.path.lexists(path), name
        assert not list(directory.glob('.rank-genes-*')), name
        results.append({'case': name, 'specific_failure': process.stderr[-500:], 'exit': process.returncode, 'no_new_normal_ports': True, 'old_artifacts_preserved': True})
        print(name, 'REFUSED', flush=True)
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'cases': results, 'status': 'ACTUAL_ENTRYPOINT_REFUSALS_AND_ORDINARY_PUBLICATION_ROLLBACK_PASS', 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
