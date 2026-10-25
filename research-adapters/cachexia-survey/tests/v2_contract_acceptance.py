import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = [
    'research-adapters/cachexia-survey/scripts/survey.R',
    'research-adapters/cachexia-survey/scripts/bind_contract.R',
    'research-adapters/cachexia-survey/manifest.toml',
    'research-adapters/cachexia-survey/TECHNICAL_DATA_CONTRACT_V2.md',
    'research-adapters/cachexia-survey-typed-values/scripts/typed_values.py',
    'research-adapters/cachexia-survey-typed-values/manifest.toml',
    'tests/test_survey_v2_technical_contract.py',
    'tests/test_survey_v2_typed_values.py',
    'tests/test_survey_typed_values.py',
]


def identities():
    return {name: dict(bytes=(ROOT / name).stat().st_size,
        sha256=hashlib.sha256((ROOT / name).read_bytes()).hexdigest()) for name in FILES}


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'survey-v2-method-only-contract'
    permanent.mkdir(mode=0o700)
    shutil.copyfile(__file__, permanent / 'driver.py')
    before = identities()
    suite = unittest.TestSuite()
    case_ids = []
    for name in ['test_survey_v2_technical_contract', 'test_survey_v2_typed_values', 'test_survey_typed_values']:
        specification = importlib.util.spec_from_file_location('tests.' + name, ROOT / 'tests' / (name + '.py'))
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        for case_class in unittest.defaultTestLoader.loadTestsFromModule(module):
            for case in case_class:
                case_ids.append(case.id())
                suite.addTest(case)
    assert len(case_ids) == len(set(case_ids)) == 22
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    (permanent / 'tests.log').write_text(output.getvalue())
    assert result.wasSuccessful() and result.testsRun == 22 and not result.skipped
    assert identities() == before
    for name in FILES:
        target = permanent / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    report = dict(schema='SURVEY_V2_METHOD_ONLY_CONTRACT_INCREMENT_V1', source_files=before,
        cases=case_ids, tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        added_R_kinds=11, added_typed_kinds=1, old_manifest_nodes_preserved=True,
        accepted_input_roles=['SYNTHETIC_TECHNICAL_INPUT', 'EMPIRICAL_TECHNICAL_INPUT'],
        method_schema_version=2, installed_version_selector='AUTONOMICS_TECHNICAL_CONTRACT_VERSION',
        actual_scope='SELF_CLEANING_R_GUARD_PROVENANCE_AST_AND_PYTHON_PARSER_TESTS_NOT_SURVEY_MODEL_OR_ARROW_CONTAINER_EXECUTION',
        numerical_official_call_ASTs_unchanged=True, reference_revision='f3715049facecc04abf8778ac71e01abb5b4b0e4',
        upstream_state_reopened_by_typed=False, typed_logical_columns_and_ports_unchanged=True,
        statistical_fits=0, real_scientific_inputs=0, containers=0, production_changes=0,
        frozen_DAG_rebound=False, scientific_authorization_granted=False, g0_granted=False)
    (permanent / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(tests_run=result.testsRun, evidence=str(permanent / 'verification.json'))))


if __name__ == '__main__':
    main()
