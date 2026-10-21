import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT=Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES=Path.home()/'.local/state/autonomics/validation-archives'
BASE='fa642cb03d16009352dba5caa0971fb4f848a847'


def require(condition,message):
    if not condition:
        raise RuntimeError(message)


def main():
    sys.path.insert(0,str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    session='9615f0f810d94b61a1c3bb70e5f66af5'
    seal='d32ca36bed875dc108975d89fddbcb28dc4666c0ce0e8c5fc0115f35240a4bf1'
    require(verify_archive(ARCHIVES,session,seal)['positive_worker_exit_verified'],'Actual image identity proof not qualified')
    proof=json.loads((ARCHIVES/session/'artifacts/permanent/mrlap-registry-reference-repair/verification.json').read_text())
    require(proof['passed'] and proof['identical_config_and_uncompressed_layers']
        and proof['old_manifest_unknown_reproduced'] and proof['anonymous_replacement_manifest_and_config_verified'],
        'Require actual old failure and exact replacement identity')
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'mrlap-registry-source-repair'
    output.mkdir(mode=0o700)
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    names=['plugins/mrlap/manifest.toml','plugins/mrlap/scripts/mrlap.sh',
        'evidence/mrlap-registry-reference-repair-20261021.json','tests/test_mrlap_registry_reference.py']
    sources={name:(ROOT/name).read_bytes() for name in names}
    original=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+names[0]])
    require(sources[names[0]].replace(proof['new_reference'].encode(),proof['old_reference'].encode())==original
        and sources[names[0]]!=original,'Exactly one registry reference edit required')
    original_script=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+names[1]])
    require(sources[names[1]]==original_script,'Method script must not change')
    before=tomllib.loads(original.decode());after=tomllib.loads(sources[names[0]].decode())
    before['image'].pop('reference');after['image'].pop('reference')
    require(before==after,'All parameters, ports, resources, panels and documentation must remain unchanged')
    tested=subprocess.run(['python3','-B','-m','unittest','discover','-s',str(ROOT/'tests'),
        '-p','test_mrlap_registry_reference.py','-v'],capture_output=True,timeout=30)
    (output/'unit-tests.stdout').write_bytes(tested.stdout)
    (output/'unit-tests.stderr').write_bytes(tested.stderr)
    require(tested.returncode==0 and b'Ran 3 tests' in tested.stderr and b'\nOK\n' in tested.stderr,'Three actual source regression tests required')
    require(all((ROOT/name).read_bytes()==raw for name,raw in sources.items()),'Selected source changed during checks')
    for name,raw in sources.items():
        destination=output/'source'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(raw)
    report=dict(schema='MRLAP_REGISTRY_SOURCE_REPAIR_QUALIFICATION_V1',passed=True,
        base_plugin_commit=BASE,identity_session=session,identity_seal=seal,
        source_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in sources.items()},
        exact_single_reference_edit=True,method_script_unchanged=True,
        parameters_ports_panels_resources_unchanged=True,actual_source_regression_tests_passed=3,
        image_config=proof['local_images'][0]['config'],identical_uncompressed_layers=len(proof['local_images'][0]['diff_ids']),
        production_deployed=False,new_method_executions=0,new_software_admissions=0,
        scientific_release_granted=False,g0_granted=False)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
