"""Managed, incremental File wiring evidence. Never invokes official R or a DAG."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import unittest

HERE = Path(__file__).resolve().parent
BASELINE_SESSION = '3fddecd8263d4166888d41f582b35dca'
BASELINE_SEAL = 'c555dce6ba321e9048f65b571fef841e09acfadd646e97145455fa01589fdf68'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline():
    root = Path.home() / '.local/state/autonomics/validation-archives' / BASELINE_SESSION
    session = json.loads((root / 'SESSION.json').read_bytes())
    manifest = root / 'artifacts/MANIFEST.json'
    assert digest(manifest) == BASELINE_SEAL == session['manifest_sha256']
    assert session['state'] == 'CLEANED' and session['worker_exit_status'] == session['launcher_exit_status'] == 0
    members = json.loads(manifest.read_bytes())['files']
    actual = {str(p.relative_to(root / 'artifacts')) for p in (root / 'artifacts').rglob('*') if p.is_file()}
    assert actual == set(members) | {'MANIFEST.json'}
    for name, identity in members.items():
        path = root / 'artifacts' / name
        assert path.stat().st_size == identity['bytes'] and digest(path) == identity['sha256'], name
    directory = root / 'artifacts/permanent/a-real-input-v1-toy'
    verification = json.loads((directory / 'verification.json').read_bytes())
    for name, checksum in verification['source_sha256'].items():
        assert digest(Path(name)) == checksum, name
    assert verification['tests_run'] == 10 and verification['tests_failures'] == verification['tests_errors'] == 0
    assert verification['full_chain_actual_exit'] == 0
    assert verification['official_RDS_readback_vectors'] == 6 and verification['official_RDS_readback_values'] == 840
    return dict(session=BASELINE_SESSION, seal=BASELINE_SEAL, rehashed_archive_members=len(members),
        rehashed_current_tested_sources=verification['source_sha256'], verification_path=str(directory / 'verification.json'),
        verification_sha256=digest(directory / 'verification.json'), prior_tests_rerun=0,
        prior_official_adjustment_rerun=False,
        prior_official_rds=dict(vectors=6, values=840, sha256=digest(directory / 'chain/official/real-adjustment.RDS')))


def main():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'a-real-intake-file-wiring'
    output.mkdir(mode=0o700)
    before = {str(p.relative_to(HERE)): digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    prior = baseline()
    (output / 'baseline-verification.json').write_text(json.dumps(prior, indent=2) + '\n')
    source = output / 'candidate-source'
    source.mkdir()
    for name in before:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / name, destination)
    os.environ['A_DAG_CASE_EVIDENCE_ROOT'] = str(output)
    spec = importlib.util.spec_from_file_location('wiring_acceptance_tests', HERE / 'test_wiring.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.WiringTests)
    with (output / 'tests.txt').open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    after = {str(p.relative_to(HERE)): digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    assert before == after
    report = dict(schema='A_REAL_INTAKE_INCREMENTAL_FILE_WIRING_V1', actual_new_tests=result.testsRun,
        tests_failures=len(result.failures), tests_errors=len(result.errors), actual_exit=0 if result.wasSuccessful() else 1,
        baseline=prior, candidate_source_sha256=before, source_unchanged_during_tests=True,
        original_v1_algorithm_tests_rerun=0, official_R_executions=0,
        actual_isolated_sdk_dag_executions=0, actual_container_executions=0,
        tested_scope='DIRECT_ISOLATED_FILE_MATERIALIZATION_AND_SUBPROCESS_FAILURE_ONLY',
        assembly_rows=564 if result.wasSuccessful() else None, vector_rows=840 if result.wasSuccessful() else None,
        official_rds_six_vectors='REUSED_SEALED_BASELINE_NOT_NEW_R_EXECUTION',
        pending=['NEW_CANDIDATE_SDK_MANIFEST_COMPILATION', 'NATIVE_DAG_IMPORT_AND_SCHEDULER_EXECUTION',
            'PINNED_OFFICIAL_R_IMAGE_RUNTIME_PREFLIGHT_AND_CONNECTED_EXECUTION', 'PRODUCTION_INSTALLATION',
            'FINITE_PRIMARY_QUALIFICATION_INTERFACE'],
        scientific_authorization_granted=False, g0_granted=False,
        artifacts={str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(verification=str(output / 'verification.json'), sha256=digest(output / 'verification.json'),
        actual_new_tests=result.testsRun, actual_exit=report['actual_exit'])))
    raise SystemExit(report['actual_exit'])


if __name__ == '__main__':
    main()
