"""Managed technical validation only; no real scientific input is executed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('intake_toy_tests', HERE / 'test_intake.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
intake = tests.intake
family = intake.family
STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'a-real-input-v1-toy'
    permanent.mkdir(mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.IntakeTests)
    with (permanent / 'tests.txt').open('x') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    source = permanent / 'toy-results.tsv'
    source.write_bytes(b'analysis_id\tmethod\tp\tstatus\treason\nA_X01_M06\tIVW_TOY_NOT_RESEARCH\t0.02\tESTIMATED\t\nA_X01_M01\tIVW_TOY_NOT_RESEARCH\tNA\tFAILED\ttoy worker failed\nA_X01_M02\tIVW_TOY_NOT_RESEARCH\tNA\tNOT_ESTIMABLE\ttoy no instruments\n')
    rds = permanent / 'toy-original.RDS'
    made = subprocess.run(['/usr/bin/Rscript', '--vanilla', '-e', 'saveRDS(list(scope="SYNTHETIC_TOY_NOT_RESEARCH",p=0.02),commandArgs(TRUE)[1])', str(rds)], capture_output=True)
    family.require(made.returncode == 0, 'Toy original RDS creation failed')
    source_sha = sha(source)
    rows = [dict(analysis_id=identifier, status=status, source_id='synthetic-toy', selector=dict(analysis_id=identifier),
        p_column='p' if status == 'ESTIMATED' else None, estimator='IVW_TOY_NOT_RESEARCH', analysis_id_column='analysis_id',
        method_column='method', status_column='status', failure_reason_column=None if status == 'ESTIMATED' else 'reason',
        rds=dict(path=str(rds), sha256=sha(rds)) if status == 'ESTIMATED' else None)
        for identifier,status in [('A_X01_M06','ESTIMATED'),('A_X01_M01','FAILED'),('A_X01_M02','NOT_ESTIMABLE')]]
    request = dict(schema=intake.REQUEST,scope=intake.SCOPE,sources=[dict(source_id='synthetic-toy',path=str(source),sha256=source_sha)],
        seen_history=[dict(source_id='synthetic-toy',sha256=source_sha,declaration='ALREADY_SEEN_NOT_INDEPENDENT',seen_at='2026-01-01T00:00:00+00:00')],edges=rows)
    request_path = permanent / 'toy-request.json'
    request_path.write_bytes(family.json_bytes(request))
    command = [sys.executable, '-B', str(HERE / 'intake.py'), '--frozen-source', *[str(STUDY / record[0]) for record in family.SOURCES],
        '--request',str(request_path),'--output',str(permanent / 'chain'),'--rscript','/usr/bin/Rscript']
    completed = subprocess.run(command,capture_output=True)
    (permanent / 'driver.stdout').write_bytes(completed.stdout)
    (permanent / 'driver.stderr').write_bytes(completed.stderr)
    family.require(completed.returncode == 0, 'Toy full chain failed; see retained stderr')
    chain = permanent / 'chain'
    assembled = family.table((chain / 'real-family.tsv').read_bytes())
    vectors = family.table((chain / 'official/real-adjusted.tsv').read_bytes())
    family.require(len(assembled) == 564 and len(vectors) == 840 and
        all(row['p_primary'] == 'NA' for row in assembled) and all(float(row['q_primary']) == 1 for row in vectors), 'Toy pending qualification/missing propagation changed')
    by_id = {row['analysis_id']:row for row in assembled}
    family.require(by_id['A_X01_M06']['observed_p'] == '0.02' and by_id['A_X01_M01']['execution_status'] == 'FAILED'
        and by_id['A_X01_M02']['execution_status'] == 'NOT_ESTIMABLE', 'Toy results/failure transport failed')
    # 篡改输入RDS，必须阻断；不重跑官方统计计算。
    original_rds_bytes = rds.read_bytes()
    rds.write_bytes(original_rds_bytes + b'TOY_TAMPER')
    rejected = False
    try:
        intake.assemble([STUDY / record[0] for record in family.SOURCES], request_path)
    except ValueError:
        rejected = True
    rds.write_bytes(original_rds_bytes)
    family.require(rejected, 'Tampered RDS must be rejected')
    assembly_receipt = family.strict_json((chain / 'real-assembly.json').read_bytes())
    family.require(assembly_receipt['decision_state_counts'] == dict(PENDING=275,O2=1) and
        by_id['A_X01_M06']['primary_qualification'] == 'OVERLAP_UNRESOLVED' and
        len(assembly_receipt['decision_evidence']) == 2, 'Actual frozen O2/pending decision identities required')
    report = dict(schema='A_REAL_INPUT_V1_TOY_VALIDATION', tests_run=result.testsRun, tests_failures=len(result.failures),
        tests_errors=len(result.errors), full_chain_actual_exit=completed.returncode, estimated_input='SYNTHETIC_TOY_NOT_RESEARCH',
        frozen_sources_verified=9, actual_decision_state_counts=assembly_receipt['decision_state_counts'], family_rows=564, adjustment_rows=840, official_RDS_readback_vectors=6,
        official_RDS_readback_values=840, tampered_input_RDS_rejected=rejected, input_RDS_verified='BYTE_IDENTITY_ONLY_NOT_NUMERICAL_CONCORDANCE',
        scientific_authorization_granted=False,g0_granted=False,
        artifacts={str(path.relative_to(permanent)):sha(path) for path in sorted(permanent.rglob('*')) if path.is_file()},
        source_sha256={str(path):sha(path) for path in [HERE/'intake.py', HERE/'test_intake.py', HERE/'validate_toy.py',
            HERE.parents[1]/'frozen-a-family-adjustment/real-intake-v1/adjust_real.R']})
    (permanent / 'verification.json').write_bytes(family.json_bytes(report))
    for path in permanent.rglob('*'):
        if path.is_file(): path.chmod(0o600)
    print(json.dumps(dict(evidence=str(permanent/'verification.json'),sha256=sha(permanent/'verification.json'),tests_run=result.testsRun,actual_exit=0)))


if __name__ == '__main__':
    main()
