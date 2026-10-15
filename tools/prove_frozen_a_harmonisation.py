"""Replay frozen input qualification with official TwoSampleMR, without MR fitting."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_opentargets_direct_files import sealed_archive

FAMILY = ROOT / 'research-adapters/frozen-a-harmonisation'
STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')
AUDIT = '03_AUDIT/G0_v4.3.2_2026-10-11/'
INPUTS = [AUDIT + name for name in ['A_LD_CLUMPED_INSTRUMENTS.tsv', 'A_OUTCOME_MATCHES.tsv',
    'A_ANALYSIS_CONFIG.json', 'G0_V432_CERTIFICATE.json', 'R_DEPENDENCY_LOCK.tsv']]
INPUTS += ['02_EXECUTION/g0_v432_methods.R']
PRODUCTS = ['A_HARMONIZED_INPUT_AUDIT.tsv', 'A_FROZEN_EXPLORATORY_INPUT.tsv',
            'A_HARMONIZATION_QUALIFICATION.json']
IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
OWNER = Path.home() / '.autonomics/containers-overlay/SOFTWARE_INSTALLATION_OWNER.json'
OWNER_SHA = '7d88bee121dbbdc974787b64cbcccc1e5304a09e805303d897d3ea28ef7d2bbc'
FRESH = 'd585c6c7ef5f49b7bc3845d722572eec'
FRESH_SEAL = 'ae4bdb186263789615ad6123376b2c9a090f850e2f0920528eb79f53a9b81bf7'
BLOCK_SHA = '50be9627766c996714e1c18ef7c32862ed2f9807814a9f61b5b3bd7c476e4f1d'
SOURCE_SHA = 'f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd'
PACKAGE_SESSION = '4f717274ece54f4396b8097b4db0ad8a'
PACKAGE_SEAL = 'bf9ce79a277c51193bb7a8af3be6ca7c9231f14567d9e7f1d0fbcc7016364f48'
PACKAGE_FUNCTIONS_SHA = '127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73'
PACKAGE_DESCRIPTION_SHA = '911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def regular(path):
    require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), 'Unaliased regular file required')
    return path


def digest(path):
    with regular(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def qualification_block(text):
    begin_marker = '} else if(mode=="qualify-A") {\n'
    end_marker = '\n} else if(mode=="test") {'
    require(text.count(begin_marker) == text.count(end_marker) == 1, 'Unique original qualification branch required')
    require(text.index(end_marker) > text.index(begin_marker), 'Original qualification branch markers are out of order')
    value = text.split(begin_marker, 1)[1].split(end_marker, 1)[0]
    require(hashlib.sha256(value.encode()).hexdigest() == BLOCK_SHA, 'Original qualification block changed')
    return value


def source_records():
    records = {name: dict(bytes=(STUDY / name).stat().st_size, sha256=digest(STUDY / name)) for name in INPUTS}
    require(records[INPUTS[-1]]['sha256'] == SOURCE_SHA, 'Frozen scientific code changed')
    return records


def inspected_backend(output):
    require(digest(OWNER) == OWNER_SHA, 'Reviewed software owner changed')
    owner = json.loads(OWNER.read_text())
    for name in ['storage', 'runroot']:
        expected = owner[name]
        actual = Path(expected['path']).stat()
        require((actual.st_dev, actual.st_ino, actual.st_uid, actual.st_gid) ==
            (expected['device'], expected['inode'], expected['uid'], expected['gid']), 'Backend ownership changed')
    shim = regular(Path(os.environ['AUTONOMICS_PODMAN_PROGRAM']))
    require("'--tmpdir'" in shim.read_text(), 'Managed ownership-aware Podman entry required')
    prefix = [str(shim), *owner['runtime_backend']]
    process = subprocess.run([*prefix, 'image', 'inspect', IMAGE], check=True, capture_output=True, text=True, timeout=60)
    (output / 'image-inspect.json').write_text(process.stdout)
    actual = json.loads(process.stdout)[0]
    expected = next(item for item in owner['installed'] if item['label'] == 'A')
    require(expected['reference'] == IMAGE and actual['Digest'] == expected['installed_manifest_sha256'] and
        'sha256:' + actual['Id'].removeprefix('sha256:') == expected['image_config_digest'] and
        actual['RootFS']['Layers'] == expected['ordered_diff_ids'], 'Actual official image identity differs')
    write(output / 'runtime-identity.json', dict(image=IMAGE, owner_sha256=OWNER_SHA, shim_sha256=digest(shim),
        backend=owner['runtime_backend'], no_build_or_pull=True, production_restarted=False))
    return prefix


def resource_admission(output):
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        memory[name] = int(value.split()[0]) * 1024
    free = shutil.disk_usage(output).free
    require(memory['MemAvailable'] >= 5 * 1024**3 and free >= 2 * 1024**3,
        'One GiB container plus system reserve and disk budget required')
    write(output / 'resource-admission.json', dict(mem_available_bytes=memory['MemAvailable'],
        disk_free_bytes=free, container_memory_bytes=1024**3, container_cpus=1, max_concurrent_containers=1))


def execute(prefix, source, directory, definition, inputs, *, reference=False):
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
        '--memory=1g', '--pids-limit=64', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=64m', '-v', str(source) + ':/code:ro', '-v', str(directory) + ':/work:rw']
    for index, filename in enumerate(inputs):
        require(filename.parent == directory and digest(filename) is not None, 'Owned input copy required')
        command += ['-e', 'AUTONOMICS_INPUT' + str(index) + '=/work/' + filename.name]
    for index, output in enumerate(definition['ports']['outputs']):
        command += ['-e', 'AUTONOMICS_OUTPUT' + str(index) + '=/work/' + output['path']]
    script = '/work/reference.R' if reference else '/code/' + definition['command']['script_file']
    command += ['--entrypoint=Rscript', IMAGE, '--vanilla', script]
    write(directory / 'command.json', command)
    process = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (directory / 'stdout.log').write_text(process.stdout)
    (directory / 'stderr.log').write_text(process.stderr)
    write(directory / 'execution.json', dict(actual_exit=process.returncode, image=IMAGE, method_fit=False,
        scientific_authorization_granted=False, g0_granted=False))
    return process


def copied_inputs(directory, before):
    result = []
    for index, name in enumerate(INPUTS):
        target = directory / ('input' + str(index))
        shutil.copyfile(STUDY / name, target)
        require(digest(target) == before[name]['sha256'], 'Owned source copy identity differs')
        result.append(target)
    return result


def original_postcheck(output):
    script = STUDY / '02_EXECUTION/verify_g0_v432.py'
    require(digest(script) == '1a928da15243316facd63358c9f33dbc69f399de41b1f7b8f341f05c647a1073',
        'Original byte verifier changed')
    process = subprocess.run(['/usr/bin/python3', '-I', '-B', str(script)], capture_output=True, text=True, timeout=600)
    (output / 'post-verifier.stdout.json').write_text(process.stdout)
    (output / 'post-verifier.stderr.log').write_text(process.stderr)
    report = json.loads(process.stdout)
    require(process.returncode == 0 and report['passed'] is True and report['read_only'] is True and
        report['errors'] == [] and report['hash_checks'] == 46786 and report['unique_file_hashes'] == 23669 and
        report['scientific_results_computed'] is False and report['all_project_scientific_gates_passed'] is False,
        'Actual original whole-root post-verification required')
    return dict(actual_exit=process.returncode, hash_checks=46786, unique_files=23669, new_g0_granted=False)


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-harmonisation'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    archives = Path.home() / '.local/state/autonomics/validation-archives'
    sealed_archive(archives / FRESH, FRESH_SEAL, successful=True)
    sealed_archive(archives / PACKAGE_SESSION, PACKAGE_SEAL, successful=True)
    package_proof = json.loads((archives / PACKAGE_SESSION /
        'artifacts/permanent/frozen-a-package-identity/verification.json').read_text())
    require(package_proof['exact_image'] == IMAGE and package_proof['observed_container_RemoteSha'] is None and
        package_proof['observed_host_RemoteSha'] == 'd4df21929fdabeb2f89686ffaad0db5f56973d64' and
        package_proof['container_description_sha256'] == PACKAGE_DESCRIPTION_SHA and
        package_proof['function_identity']['function_count'] == 171 and
        package_proof['function_identity']['aggregate_sha256'] == PACKAGE_FUNCTIONS_SHA and
        package_proof['canonical_host_package_files_unchanged'] is True, 'Actual full namespace official reference proof required')
    before = source_records()
    source = output / 'source'
    shutil.copytree(FAMILY, source, ignore=shutil.ignore_patterns('__pycache__'))
    original_sources = {path.relative_to(FAMILY).as_posix(): digest(path) for path in FAMILY.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
    require(original_sources == {path.relative_to(source).as_posix(): digest(path) for path in source.rglob('*') if path.is_file()}, 'Code snapshot differs')
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    require(manifest['image']['reference'] == IMAGE and len(manifest['nodes']) == 1, 'Single official harmonisation node required')
    definition = manifest['nodes'][0]
    require(len(definition['ports']['inputs']) == 6 and len(definition['ports']['outputs']) == 5 and not definition.get('params'),
        'Exact frozen six-input five-output contract required')
    resource_admission(output)
    prefix = inspected_backend(output)
    positive = output / 'positive'
    positive.mkdir()
    inputs = copied_inputs(positive, before)
    process = execute(prefix, source, positive, definition, inputs)
    require(process.returncode == 0, 'Actual official harmonisation adapter failed')
    provenance = json.loads((positive / 'INPUT_METHOD_PROVENANCE.json').read_text())
    require(provenance['input_sha256'] == [before[name]['sha256'] for name in INPUTS] and
        provenance['adapter_sha256'] == digest(source / definition['command']['script_file']) and
        provenance['original_scientific_code_sha256'] == SOURCE_SHA and provenance['qualify_A_block_sha256'] == BLOCK_SHA and
        provenance['original_qualify_A_branch_evaluated'] is True and provenance['R'] == '4.6.1' and
        provenance['TwoSampleMR'] == '0.7.11' and provenance['TwoSampleMR_RemoteSha'] is None and
        provenance['package_description_sha256'] == PACKAGE_DESCRIPTION_SHA and
        provenance['package_namespace_function_count'] == 171 and
        provenance['package_namespace_aggregate_sha256'] == PACKAGE_FUNCTIONS_SHA and
        provenance['source_commit_supported_by_frozen_host_identity'] == 'd4df21929fdabeb2f89686ffaad0db5f56973d64' and
        provenance['package_identity_proof_session'] == PACKAGE_SESSION and
        provenance['n_clumped'] == provenance['n_qualified'] == 39 and
        provenance['additional_config_envelope_checked_without_reselection'] is True and
        all(provenance[name] is False for name in ['raw_GWAS_QC_reexecuted', 'PLINK_or_LD_reexecuted',
            'MR_estimates_computed', 'original_full_project_verifier_executed', 'scientific_authorization_granted',
            'formal_scientific_pass_granted', 'G0']), 'Complete official package and restricted authority provenance required')
    ports = []
    for index, port in enumerate(definition['ports']['outputs']):
        path = positive / port['path']
        require(path.stat().st_size > 0, 'All five declared outputs must exist and be readable')
        ports.append(dict(port=index, name=port['path'], bytes=path.stat().st_size, sha256=digest(path)))
    require('no MR estimates computed' in (positive / 'harmonisation.log').read_text(),
        'Actual qualification log required')
    comparisons = []
    for name in PRODUCTS:
        actual = positive / name
        expected = STUDY / AUDIT / name
        require(actual.read_bytes() == expected.read_bytes(), 'Complete frozen qualification bytes differ: ' + name)
        comparisons.append(dict(product=name, bytes=actual.stat().st_size, sha256=digest(actual), canonical_sha256=digest(expected)))
    reference = output / 'reference'
    reference.mkdir()
    reference_inputs = copied_inputs(reference, before)
    block = qualification_block(reference_inputs[-1].read_text())
    program = '''options(stringsAsFactors=FALSE,warn=1)
Sys.setenv(OMP_NUM_THREADS=1,OPENBLAS_NUM_THREADS=1,MKL_NUM_THREADS=1)
set.seed(432202610)
stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("TwoSampleMR"))=="0.7.11")
read_tsv<-function(name) read.delim(file.path("/work",if(name=="A_LD_CLUMPED_INSTRUMENTS.tsv") "input0" else "input1"),check.names=FALSE,colClasses="character")
write_tsv<-function(x,name) write.table(x,file.path("/work",name),sep="\\t",row.names=FALSE,quote=FALSE,na="NA")
write_json<-function(x,name) jsonlite::write_json(x,file.path("/work",name),pretty=TRUE,auto_unbox=TRUE,na="null",null="null")
''' + block
    (reference / 'reference.R').write_text(program)
    result = execute(prefix, source, reference, definition, reference_inputs, reference=True)
    require(result.returncode == 0, 'Independent original official qualification reference failed')
    for name in PRODUCTS:
        require((positive / name).read_bytes() == (reference / name).read_bytes(), 'Independent official reference bytes differ')
    negatives = []
    for index in range(6):
        directory = output / ('wrong-input-' + str(index))
        directory.mkdir()
        copies = copied_inputs(directory, before)
        copies[index].write_bytes(copies[index].read_bytes() + b'\n')
        result = execute(prefix, source, directory, definition, copies)
        normal = [port['path'] for port in definition['ports']['outputs'] if port['path'] != 'harmonisation.log' and (directory / port['path']).exists()]
        require(type(result.returncode) is int and result.returncode == 2 and
            'Only the exact six frozen harmonisation inputs are supported' in result.stderr and not normal,
            'Expected source refusal requires exact exit2/diagnostic/no normal outputs')
        negatives.append(dict(input_port=index, actual_exit=result.returncode, normal_outputs=0))
    collision = output / 'existing-output'
    collision.mkdir()
    copies = copied_inputs(collision, before)
    sentinel = collision / definition['ports']['outputs'][0]['path']
    sentinel.write_bytes(b'PREEXISTING_FOREIGN_OUTPUT\n')
    identity = sentinel.stat().st_dev, sentinel.stat().st_ino, digest(sentinel)
    result = execute(prefix, source, collision, definition, copies)
    require(result.returncode == 2 and 'overwrite' in result.stderr.lower() and
        (sentinel.stat().st_dev, sentinel.stat().st_ino, digest(sentinel)) == identity and
        not any((collision / port['path']).exists() for port in definition['ports']['outputs'][1:]),
        'Existing outputs must be refused before computation or log mutation')
    require(before == source_records() and digest(OWNER) == OWNER_SHA, 'Original inputs or software owner changed')
    require(original_sources == {path.relative_to(FAMILY).as_posix(): digest(path) for path in FAMILY.rglob('*') if path.is_file() and '__pycache__' not in path.parts}, 'Candidate source changed during proof')
    post = original_postcheck(output)
    write(output / 'verification.json', dict(status='SCOPED_DIRECT_OFFICIAL_HARMONISATION_PROVEN_DAG_PENDING',
        source_files=original_sources, canonical_input_sha256=before, products=comparisons, output_ports=ports,
        declared_inputs=6, declared_outputs=5, real_variants=39, independent_original_reference=True,
        original_qualify_A_block_sha256=BLOCK_SHA, wrong_source_refusals=negatives,
        package_identity_proof_session=PACKAGE_SESSION, package_identity_proof_manifest_sha256=PACKAGE_SEAL,
        existing_output_identity_preserved=True, canonical_sources_unchanged=True, post_verifier=post,
        raw_GWAS_QC_or_PLINK_executed=False, MR_estimates_computed=False, current_DAG_executed=False,
        production_restarted=False, scientific_release_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
