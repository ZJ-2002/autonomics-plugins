"""Managed toy reproduction of the published family origin/result-contract gaps."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = 'plugins/frozen-b-project/scripts/project.py'
BASELINE = '646ab3c'
BASELINE_SHA = '3ee6b367ca19fbcf1bea2711ba78795b022a0d8697b088f846d3799c025d36e8'
FIXTURE = 'tests/test_frozen_b_project.py'
FIXTURE_SHA = '41e976ccd5f185b1b2d4ccd2b175eee98fd2c254f4c2b15535947afc17c06db4'


def current():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-b-family-contract-fixed'
    output.mkdir(mode=0o700)
    paths = [SOURCE, 'plugins/frozen-b-project/scripts/run-intake.py', 'plugins/frozen-b-project/scripts/run-family.py',
        FIXTURE, 'tests/test_frozen_b_family_contract.py',
        'tests/prove_frozen_b_family_contract.py']
    hashes = {}
    for relative in paths:
        source = ROOT / relative
        target = output / 'source' / relative
        target.parent.mkdir(parents=True,exist_ok=True)
        data = source.read_bytes(); target.write_bytes(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    code = '''import json,sys,unittest
names=['tests.test_frozen_b_project.FrozenProjectTests',
 'tests.test_frozen_b_family_contract.FamilyContractTests']
suite=unittest.defaultTestLoader.loadTestsFromNames(names)
result=unittest.TextTestRunner(verbosity=2).run(suite)
with open(sys.argv[1],'x') as handle:json.dump(dict(tests=result.testsRun,failures=len(result.failures),
 errors=len(result.errors),skipped=len(result.skipped)),handle,indent=2)
sys.exit(0 if result.wasSuccessful() else 1)
'''
    with (output / 'stdout.log').open('x') as stdout,(output / 'stderr.log').open('x') as stderr:
        run = subprocess.run([sys.executable,'-B','-c',code,str(output / 'actual-tests.json')],cwd=ROOT,
            stdout=stdout,stderr=stderr,timeout=60)
    actual = json.loads((output / 'actual-tests.json').read_text())
    if run.returncode or actual != dict(tests=17,failures=0,errors=0,skipped=0):
        raise RuntimeError('All 17 frozen-project/family unit tests must actually execute')
    if hashes != {relative:hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in paths}:
        raise RuntimeError('Source changed during fixed-contract proof')
    (output / 'verification.json').write_text(json.dumps(dict(status='SEVENTEEN_FROZEN_B_ENGINEERING_CONTRACT_TESTS_PASSED',
        actual=actual,source_sha256=hashes,official_R_executed=False,actual_production_or_study_executed=False,
        production_intake_or_family_positive_DAG_qualified=False,g0_granted=False),indent=2)+'\n')


def main():
    if not os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') or sys.argv[1:] not in [[],['--current']]:
        raise RuntimeError('Managed synthetic baseline proof required')
    if sys.argv[1:] == ['--current']:
        return current()
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-b-family-contract-baseline'
    output.mkdir(mode=0o700)
    code = subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':'+SOURCE])
    if hashlib.sha256(code).hexdigest() != BASELINE_SHA:
        raise RuntimeError('Exact published baseline source required')
    fixture_code = subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':'+FIXTURE])
    if hashlib.sha256(fixture_code).hexdigest() != FIXTURE_SHA:
        raise RuntimeError('Exact published baseline fixture source required')
    revision = subprocess.check_output(['git','-C',str(ROOT),'rev-parse',BASELINE+'^{commit}'],text=True).strip()
    (output / 'baseline-project.py').write_bytes(code)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    (output / 'fixture-source.py').write_bytes(fixture_code)
    fixtures = types.ModuleType('published_family_fixtures')
    fixtures.__file__ = str(ROOT / FIXTURE)
    exec(compile(fixture_code,'published-baseline-fixture.py','exec'),fixtures.__dict__)
    module = types.ModuleType('frozen_family_baseline')
    exec(compile(code,'published-baseline-project.py','exec'),module.__dict__)
    fixtures.project = module
    with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as directory:
        toy = Path(directory)
        paths, lock = fixtures.fixture(toy)
        case = fixtures.FrozenProjectTests(); case.paths = paths; case.lock = lock
        original = case.family_inputs()
        module.family(original,lock)
        sources = output / 'synthetic-source'; sources.mkdir()
        for name,path in paths.items(): (sources / name).write_bytes(path.read_bytes())
        (sources / 'toy-lock.json').write_bytes(module.canonical(lock))
        records = []
        for name in ['delete_source_files','wrong_scope','grant_authorization','replace_source_hashes']:
            receipt = module.strict_json(original['intake'])
            if name == 'delete_source_files': receipt.pop('source_files')
            elif name == 'wrong_scope': receipt['scope'] = 'UNRELATED_ARBITRARY_INTAKE'
            elif name == 'grant_authorization': receipt.update(scientific_authorization=True,formal_authorized=True,G0=True,
                metadata_certificate_is_not_full_scientific_permission=False)
            else: receipt['source_files'] = {key:dict(sha256='0'*64,bytes=1) for key in module.INPUTS}
            raw = {**original,'intake':module.canonical(receipt)}
            result = module.family(raw,lock)
            target = output / name; target.mkdir()
            for key,value in raw.items(): (target / (key+'.input')).write_bytes(value)
            for key,value in result.items(): (target / key).write_bytes(value)
            records.append(dict(case=name,invalid_contract_accepted=True,rows=len(module.rows(result['family.tsv']))))
        for field,value,index in [('log2_expression_difference','Inf',0),('standard_error','-0.1',0),
                ('moderated_df','NaN',0),('ci_lower','999',0),('log2_expression_difference','1.0',1),('G0','TRUE',0)]:
            results = module.rows(original['results']); results[index][field] = value
            if field == 'G0':
                for row in results[1:]: row[field] = 'FALSE'
            data = module.table(list(results[0]),results)
            audit = module.strict_json(original['limma_audit'])
            audit['plugin_transport_output_sha256']['results'] = module.identity(data)['sha256']
            raw = {**original,'results':data,'limma_audit':module.canonical(audit)}
            result = module.family(raw,lock)
            name = field+'_'+str(index); target = output / name; target.mkdir()
            for key,content in raw.items(): (target / (key+'.input')).write_bytes(content)
            for key,content in result.items(): (target / key).write_bytes(content)
            records.append(dict(case=name,invalid_contract_accepted=True,rows=len(module.rows(result['family.tsv']))))
    if len(records) != 10: raise RuntimeError('All ten baseline defects must actually execute')
    (output / 'verification.json').write_text(json.dumps(dict(
        status='TEN_INVALID_FAMILY_CONTRACTS_ACCEPTED_BY_PUBLISHED_BASELINE',baseline_revision=revision,
        baseline_source_sha256=BASELINE_SHA,baseline_fixture_sha256=FIXTURE_SHA,cases=records,actual_production_or_study_executed=False,
        official_R_executed=False,source_locks_rewritten_in_production=False,g0_granted=False),indent=2)+'\n')


if __name__ == '__main__': main()
