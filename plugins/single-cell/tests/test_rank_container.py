import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from rank_compare import compare
from rank_fixtures import fixture


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/rank_genes_groups.py'
REFERENCE = Path(__file__).with_name('rank_reference.py')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--reference-library', type=Path, required=True)
    arguments = parser.parse_args()
    cases = [(method, 'dense', 'rest', 100) for method in ['wilcoxon', 't-test', 't-test_overestim_var', 'logreg']]
    cases += [(method, 'csr', 'NA', 5) for method in ['wilcoxon', 't-test', 't-test_overestim_var', 'logreg']]
    cases += [(method, 'csc', 'rest', 1) for method in ['wilcoxon', 't-test', 't-test_overestim_var', 'logreg']]
    cases += [('wilcoxon', 'tied', 'rest', 100), ('t-test', 'float32', 'rest', 100), ('t-test_overestim_var', 'raw-ignored', 'rest', 100), ('logreg', 'two-groups', 'rest', 100), ('t-test', 'reordered', 'NA', 100), ('wilcoxon', 'existing-result', 'rest', 100)]
    results = []
    for method, kind, reference, n_genes in cases:
        name = method + '-' + kind + '-' + reference + '-' + str(n_genes)
        directory = arguments.evidence / name
        directory.mkdir(parents=True)
        request = {'groupby': 'group', 'method': method, 'reference': reference, 'n_genes': n_genes}
        (directory / 'request.json').write_text(json.dumps(request) + '\n')
        fixture(kind).write_h5ad(directory / 'input.h5ad')
        reference_env = dict(os.environ, PYTHONPATH=str(arguments.reference_library))
        author = subprocess.run([sys.executable, str(REFERENCE), str(directory)], env=reference_env, capture_output=True, text=True, timeout=180)
        (directory / 'author.stdout.txt').write_text(author.stdout)
        (directory / 'author.stderr.txt').write_text(author.stderr)
        assert author.returncode == 0, (name, author.stderr)
        environment = dict(os.environ, SC_P_STR_GROUPBY='group', SC_P_STR_METHOD=method, SC_P_STR_REFERENCE=reference, SC_P_INT_N_GENES=str(n_genes))
        environment['AUTONOMICS_INPUT0'] = str(directory / 'input.h5ad')
        environment.update({f'AUTONOMICS_OUTPUT{number}': str(directory / name) for number, name in enumerate(['markers.parquet', 'report.json', 'output.h5ad'])})
        actual = subprocess.run([sys.executable, str(SCRIPT)], env=environment, capture_output=True, text=True, timeout=180)
        (directory / 'actual.stdout.txt').write_text(actual.stdout)
        (directory / 'actual.stderr.txt').write_text(actual.stderr)
        assert actual.returncode == 0, (name, actual.stderr)
        result = compare(directory)
        (directory / 'COMPARISON.json').write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
        print(name, 'PASS', flush=True)
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'status': 'ALL_FOUR_ORIGINAL_METHOD_BRANCHES_WHOLE_AUTHOR_RESULTS_AND_INTERFACE_MATCH', 'cases': results, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
