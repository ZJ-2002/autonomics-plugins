"""Real-image refusals of invalid methods, axes, critical data and publication."""

import argparse
import json
from pathlib import Path
import sys

import anndata as ad
import numpy as np

from embedding_compare import digest
from test_embedding_container import DEFAULTS, FAMILY, environment, execute, fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    arguments = parser.parse_args()
    arguments.evidence.mkdir()
    scalar_cases = [('pcs-zero', 'n_pcs', 0, 'n_pcs'), ('pcs-fraction', 'n_pcs', 4.5, 'n_pcs'),
        ('neighbors-one', 'n_neighbors', 1, 'n_neighbors'), ('neighbors-too-many', 'n_neighbors', 80, 'smaller'),
        ('hvg-zero', 'n_top_genes', 0, 'n_top_genes'), ('hvg-insufficient-rank', 'n_top_genes', 1, 'rank bound'),
        ('pcs-excessive', 'n_pcs', 1000, 'rank bound'), ('seed-negative', 'random_state', -1, 'random_state'),
        ('seed-excessive', 'random_state', 2**32, 'random_state'), ('resolution-zero', 'resolution', 0., 'resolution'),
        ('resolution-nan', 'resolution', float('nan'), 'finite'), ('min-dist-one', 'min_dist', 1., 'min_dist'),
        ('min-dist-negative', 'min_dist', -1., 'min_dist'), ('min-dist-infinite', 'min_dist', float('inf'), 'finite'),
        ('normalize-without-log', 'log1p', False, 'requires log1p=True')]
    named_cases = [(name, fragment) for name, fragment in [
        ('negative-X', 'nonnegative'), ('nan-X', 'finite real'), ('infinite-X', 'finite real'),
        ('complex-X', 'finite real'), ('missing-X', 'X is missing'), ('duplicate-cells', 'unique'),
        ('duplicate-genes', 'unique'), ('empty-cell-id', 'nonempty'), ('empty-gene-id', 'nonempty'),
        ('missing-used-PC', 'requested components'), ('nan-used-PC', 'finite real'),
        ('malformed-h5ad', 'file signature'), ('h5ad-exists', 'refusing to overwrite'),
        ('report-exists', 'refusing to overwrite'), ('output-directory', 'refusing to overwrite'),
        ('dangling-output', 'refusing to overwrite'), ('aliased-outputs', 'distinct'),
        ('input-overwrite', 'distinct'), ('bad-boolean', 'true or false'),
        ('second-link-failure', 'injected second link failure')]]
    records = []
    for name, key, value, fragment in [*scalar_cases, *[(name, None, None, fragment) for name, fragment in named_cases]]:
        directory = arguments.evidence / name
        directory.mkdir()
        settings = {**DEFAULTS, 'n_pcs': 4, 'n_neighbors': 5}
        fixture(directory, 'reuse-longer' if name in ['missing-used-PC', 'nan-used-PC'] else 'dense', settings)
        if key is not None:
            settings[key] = value
        data = ad.read_h5ad(directory / 'input.h5ad')
        if name in ['negative-X', 'nan-X', 'infinite-X', 'complex-X']:
            data.X = data.X.astype(complex if name == 'complex-X' else float)
            data.X[0, 0] = {'negative-X': -1, 'nan-X': np.nan, 'infinite-X': np.inf, 'complex-X': 1j}[name]
        elif name == 'missing-X':
            data.X = None
        elif name in ['duplicate-cells', 'empty-cell-id']:
            data.obs_names = [data.obs_names[1] if name == 'duplicate-cells' else '', *data.obs_names[1:]]
        elif name in ['duplicate-genes', 'empty-gene-id']:
            data.var_names = [data.var_names[1] if name == 'duplicate-genes' else '', *data.var_names[1:]]
        elif name == 'missing-used-PC':
            data.obsm['X_pca'] = data.obsm['X_pca'][:, :2]
        elif name == 'nan-used-PC':
            data.obsm['X_pca'][0, 0] = np.nan
        data.write_h5ad(directory / 'input.h5ad')
        variables = environment(directory, settings)
        sentinel = None
        if name in ['h5ad-exists', 'report-exists']:
            sentinel = directory / ('output.h5ad' if name == 'h5ad-exists' else 'report.json')
            sentinel.write_bytes(b'original-output-sentinel')
        elif name == 'malformed-h5ad':
            (directory / 'input.h5ad').write_bytes(b'not HDF5')
        elif name == 'output-directory':
            (directory / 'output.h5ad').mkdir()
        elif name == 'dangling-output':
            (directory / 'output.h5ad').symlink_to('missing.h5ad')
        elif name == 'aliased-outputs':
            variables['AUTONOMICS_OUTPUT1'] = variables['AUTONOMICS_OUTPUT0']
        elif name == 'input-overwrite':
            variables['AUTONOMICS_OUTPUT0'] = variables['AUTONOMICS_INPUT0']
        elif name == 'bad-boolean':
            variables['SC_P_BOOL_SCALE'] = 'not-a-boolean'
        before = digest(directory / 'input.h5ad')
        command = [sys.executable, str(FAMILY / 'scripts/embedding.py')]
        if name == 'second-link-failure':
            code = "import os,runpy; original=os.link; calls=[]\ndef link(*args,**kwargs):\n calls.append(1)\n if len(calls)==2: raise OSError('injected second link failure')\n return original(*args,**kwargs)\nos.link=link\nrunpy.run_path(" + repr(str(FAMILY / 'scripts/embedding.py')) + ",run_name='__main__')"
            command = [sys.executable, '-c', code]
        result = execute(command, directory, 'declared-node-script', variables)
        assert result.returncode != 0 and fragment in result.stderr.decode(), result.stderr.decode()
        assert digest(directory / 'input.h5ad') == before
        for path in [directory / 'output.h5ad', directory / 'report.json']:
            if path == sentinel:
                assert path.read_bytes() == b'original-output-sentinel'
            else:
                assert not path.is_file(), 'Failed method published a normal output'
        assert not list(directory.glob('.embedding-*'))
        records.append({'case': name, 'specifically_refused': True, 'input_unchanged': True,
                        'normal_outputs_not_published': True, 'G0': False})
        print(name, 'PASS', flush=True)
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'cases': len(records), 'records': records,
        'crash_or_persistent_resume_claim': False, 'G0': False}, indent=2)+'\n')


if __name__ == '__main__':
    main()
