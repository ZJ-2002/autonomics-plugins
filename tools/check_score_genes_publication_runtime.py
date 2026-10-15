"""Inner official-runtime proof for bounded scoring I/O; the outer runner owns containers."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ORIGINAL_SHA = '9cad19728810b8e9c9933fed33f556870419a985a12f1485ce61d4f4da8c58e8'
FIXED_SHA = 'dc2815e79b289327ef4ef3c15bf744c1e1557063692b9989c77b2002bf47f774'
SUITE_SHA = '36fd415ea047213c022c0c4fe781e7b70295255277162afda903debbe6ccb78c'
SCIENTIFIC_CASES = {
    'test_dense_unclamped_control', 'test_sparse', 'test_raw_axis',
    'test_missing_and_duplicate_members', 'test_nonfinite_all_cell_summary',
    'test_no_controls_is_failure', 'test_axis_collision_is_failure',
}
PUBLICATION_CASES = ('input-alias', 'existing-output', 'missing-report-parent')
FOREIGN_H5AD = b'FOREIGN_H5AD_SENTINEL_NOT_SCIENTIFIC_DATA\n'
FOREIGN_REPORT = b'FOREIGN_REPORT_SENTINEL_NOT_SCIENTIFIC_DATA\n'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def ordinary(path, expected):
    require(path.is_file() and not path.is_symlink(), 'Ordinary supplied source file required')
    require(sha(path) == expected, 'Exact original/fixed/suite source identity required')
    return path


def load_suite(path):
    specification = importlib.util.spec_from_file_location('official_score_genes_frozen_suite', path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    actual = {name for name in dir(module.OfficialScoringTests) if name.startswith('test_')}
    require(actual == SCIENTIFIC_CASES, 'Original seven scientific cases must remain complete and unchanged')
    return module


class ObservedResult(unittest.TextTestResult):
    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.observations = []

    def startTest(self, test):
        self.observations.append(dict(test_id=test.id(), status='STARTED'))
        super().startTest(test)

    def addSuccess(self, test):
        self.observations[-1]['status'] = 'SUCCESS'
        super().addSuccess(test)

    def addFailure(self, test, error):
        self.observations[-1]['status'] = 'FAILURE'
        super().addFailure(test, error)

    def addError(self, test, error):
        self.observations[-1]['status'] = 'ERROR'
        super().addError(test, error)

    def addSkip(self, test, reason):
        self.observations[-1].update(status='SKIP', reason=reason)
        super().addSkip(test, reason)


def scientific_suite(module, script, output):
    output.mkdir()
    scripts = output / 'scripts'
    scripts.mkdir()
    shutil.copyfile(script, scripts / 'score_genes.py')
    require(sha(scripts / 'score_genes.py') == sha(script), 'Suite transport changed supplied method script')
    previous = module.ROOT
    module.ROOT = output
    stream = io.StringIO()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.OfficialScoringTests)
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=ObservedResult).run(suite)
    finally:
        module.ROOT = previous
    (output / 'unittest.log').write_text(stream.getvalue())
    record = dict(tests_run=result.testsRun, actual_cases=result.observations,
        failures=[dict(test_id=test.id(), traceback=text) for test, text in result.failures],
        errors=[dict(test_id=test.id(), traceback=text) for test, text in result.errors],
        skipped=[dict(test_id=test.id(), reason=reason) for test, reason in result.skipped],
        original_suite_unchanged=True, fixture_scope='SYNTHETIC_METHOD_TEST_NOT_RESEARCH')
    write(output / 'verification.json', record)
    require(result.testsRun == 7 and len(result.observations) == 7 and not result.failures and
        not result.errors and not result.skipped and result.wasSuccessful() and
        {entry['test_id'].rsplit('.', 1)[-1] for entry in result.observations} == SCIENTIFIC_CASES and
        all(entry['status'] == 'SUCCESS' for entry in result.observations),
        'All seven unchanged official numerical/boundary cases must actually execute successfully')
    return record


def invoke(script, source, outputs, output):
    environment = dict(os.environ, AUTONOMICS_INPUT0=str(source),
        AUTONOMICS_OUTPUT0=str(outputs[0]), AUTONOMICS_OUTPUT1=str(outputs[1]),
        SC_P_JSON_GENE_SETS='{"score":["G0","G1"]}', SC_P_INT_CTRL_SIZE='50', SC_P_INT_RANDOM_STATE='0')
    command = [sys.executable, '-B', str(script)]
    process = subprocess.run(command, env=environment, capture_output=True, timeout=120)
    (output / 'method.stdout').write_bytes(process.stdout)
    (output / 'method.stderr').write_bytes(process.stderr)
    record = dict(command=command, actual_exit=process.returncode, script_sha256=sha(script),
        inputs=['input.h5ad'], declared_outputs=['output.h5ad', 'report.json'],
        scientific_authorization_granted=False)
    write(output / 'execution.json', record)
    return process, record


def publication_case(module, script, implementation, case, root):
    import anndata as ad

    output = root / (implementation + '-' + case)
    output.mkdir()
    source = output / 'input.h5ad'
    module.OfficialScoringTests().fixture().write_h5ad(source)
    before = sha(source)
    outputs = [output / 'output.h5ad', output / 'report.json']
    if case == 'input-alias':
        outputs[1] = source
    elif case == 'existing-output':
        outputs[0].write_bytes(FOREIGN_H5AD)
        outputs[1].write_bytes(FOREIGN_REPORT)
    else:
        outputs[1] = output / 'missing-report-directory' / 'report.json'
    process, execution = invoke(script, source, outputs, output)
    original = implementation == 'original'
    expected_exit = 2 if not original or case == 'missing-report-parent' else 0
    require(type(process.returncode) is int and process.returncode == expected_exit,
        'Actual original/fixed method exit differs in ' + implementation + '/' + case)
    if original and case == 'input-alias':
        require(sha(source) != before and json.loads(source.read_text())['operation'] == 'gene_set_score' and
            outputs[0].is_file(), 'Original input-to-report corruption was not actually reproduced')
        ad.read_h5ad(outputs[0])
    elif original and case == 'existing-output':
        require(outputs[0].read_bytes() != FOREIGN_H5AD and outputs[1].read_bytes() != FOREIGN_REPORT and
            json.loads(outputs[1].read_text())['operation'] == 'gene_set_score',
            'Original overwrite of both foreign output files was not reproduced')
        ad.read_h5ad(outputs[0])
    elif original:
        require(outputs[0].is_file() and not outputs[1].exists() and
            b'gene_set_score:' in process.stderr and str(outputs[1].parent).encode() in process.stderr,
            'Original failed method did not leave the expected normal H5AD half-product')
        ad.read_h5ad(outputs[0])
    else:
        require(sha(source) == before and b'gene_set_score:' in process.stderr,
            'Fixed method changed input or omitted its actual failure diagnostic')
        if case == 'existing-output':
            require(outputs[0].read_bytes() == FOREIGN_H5AD and outputs[1].read_bytes() == FOREIGN_REPORT and
                b'Existing output must not be overwritten' in process.stderr,
                'Fixed method failed to preserve both foreign sentinels')
        elif case == 'input-alias':
            require(not outputs[0].exists() and b'Existing output must not be overwritten' in process.stderr,
                'Fixed alias rejection published a new normal output or failed for another reason')
        else:
            require(not outputs[0].exists() and not outputs[1].exists() and
                b'No such file or directory' in process.stderr and str(outputs[1].parent).encode() in process.stderr,
                'Fixed missing-parent preflight left a normal product or failed for another reason')
    if case != 'input-alias' or not original:
        require(sha(source) == before, 'Method unexpectedly changed its input source')
    record = dict(case=case, implementation=implementation, actual_exit=execution['actual_exit'],
        baseline_defect_reproduced=original, fixed_refusal_proven=not original,
        input_before_sha256=before, input_after_sha256=sha(source),
        output_h5ad_present=outputs[0].is_file(), report_present=outputs[1].is_file(),
        scientific_authorization_granted=False)
    write(output / 'verification.json', record)
    return record


def descriptor_h5ad_readback(module, output):
    import anndata as ad
    import numpy as np
    import pandas as pd

    directory = output / 'descriptor-h5ad-readback'
    directory.mkdir()
    descriptor, name = tempfile.mkstemp(prefix='owned-', suffix='.h5ad', dir=directory)
    named = Path(name)
    original = os.fstat(descriptor)
    try:
        requested = module.OfficialScoringTests().fixture()
        requested.write_h5ad(Path('/proc/self/fd') / str(descriptor), compression='lzf')
        observed = ad.read_h5ad(named)
        actual = os.fstat(descriptor)
        require((actual.st_dev, actual.st_ino) == (original.st_dev, original.st_ino) and
            (named.stat().st_dev, named.stat().st_ino) == (actual.st_dev, actual.st_ino),
            'AnnData descriptor write changed its owned inode')
        np.testing.assert_array_equal(observed.X, requested.X)
        pd.testing.assert_frame_equal(observed.obs, requested.obs)
        pd.testing.assert_frame_equal(observed.var, requested.var)
        record = dict(actual_official_AnnData_write_h5ad_and_readback=True,
            writer_filename='/proc/self/fd/<owned_descriptor>', owned_inode_preserved=True,
            rows=requested.n_obs, columns=requested.n_vars, full_X_and_axes_equal=True,
            h5ad_bytes=named.stat().st_size, h5ad_sha256=sha(named),
            scope='DESCRIPTOR_COMPATIBILITY_NOT_STATISTICAL_CERTIFICATION')
        write(directory / 'verification.json', record)
        return record
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-script', type=Path, required=True)
    parser.add_argument('--fixed-script', type=Path, required=True)
    parser.add_argument('--suite-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    original = ordinary(arguments.original_script, ORIGINAL_SHA)
    fixed = ordinary(arguments.fixed_script, FIXED_SHA)
    suite_source = ordinary(arguments.suite_source, SUITE_SHA)
    identities = dict(original_script=sha(original), fixed_script=sha(fixed), suite_source=sha(suite_source))
    arguments.output.mkdir(parents=True, exist_ok=False)
    versions = {name: importlib.metadata.version(name) for name in ['scanpy', 'anndata', 'numpy', 'scipy', 'pandas', 'h5py']}
    write(arguments.output / 'runtime.json', dict(packages=versions, scientific_authorization_granted=False))
    require(versions['scanpy'] == '1.11.3' and versions['anndata'] == '0.11.4', 'Exact existing official scoring runtime required')
    module = load_suite(suite_source)
    compatibility = descriptor_h5ad_readback(module, arguments.output)
    scientific = {}
    for label, script in [('original', original), ('fixed', fixed)]:
        scientific[label] = scientific_suite(module, script, arguments.output / ('official-suite-' + label))
    cases = []
    for label, script in [('original', original), ('fixed', fixed)]:
        for case in PUBLICATION_CASES:
            cases.append(publication_case(module, script, label, case, arguments.output))
    require(identities == dict(original_script=sha(original), fixed_script=sha(fixed), suite_source=sha(suite_source)),
        'Original, candidate or unchanged scientific suite source changed')
    summary = dict(schema='SCORING_PUBLICATION_OFFICIAL_RUNTIME_V1',
        status='SCOPED_OFFICIAL_SCORING_AND_PUBLICATION_DIRECT_RUNTIME_PROVEN',
        source_sha256=identities, packages=versions, scientific_suites=scientific,
        actual_scientific_suite_cases=14, publication_cases=cases,
        actual_original_defect_reproductions=3, actual_fixed_path_refusals=3,
        descriptor_h5ad_compatibility=compatibility, actual_DAG_executed=False,
        official_scores_not_UCell_or_singscore=True, real_research_inputs_used=False,
        production_deployed=False, scientific_authorization_granted=False, g0_granted=False,
        container_stoppage='OUTER_MANAGED_RUNNER_MUST_RECONCILE')
    write(arguments.output / 'SUMMARY.json', summary)
    print(json.dumps(dict(scientific_suite_cases=14, original_defects=3, fixed_refusals=3,
        descriptor_compatibility=True, G0=False)))


if __name__ == '__main__':
    main()
