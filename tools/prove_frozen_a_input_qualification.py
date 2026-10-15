"""Controlled direct replay of frozen raw GWAS qualification, not a DAG or MR run."""

import csv
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prove_frozen_a_harmonisation import AUDIT, OWNER, OWNER_SHA, STUDY, digest, original_postcheck, require, write
from tools.reconcile_ab_evidence_index import verify_archive

FAMILY = ROOT / 'research-adapters/frozen-a-input-qualification'
SOURCE_PINS = {
    'manifest.toml': 'eb62df8d8ee4e4c18d84b66a141c6ec51e35cceff5dd42017c8723e470e4b908',
    'scripts/qualify.py': '81421c4467c4d204e576949b9a364dd487ffb647e9e429bb922ed7938b1f5a69',
    'contracts/source-lock.json': 'e06791ba99a612a8a503975f32486ac9f28a891be38af1477e2c8c79a6ca052c',
    'README.md': '7a0921b70dba788e3bd0be3a599f3fb4795d18ad50f09dc73cd8a960419f0d39',
}
IMAGE = 'docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d'
CONFIG = 'ea130d51594b38acddd30f9f2542a38c37736000f1710fb8c1058b6c3e613f8c'
PYTHON_SESSION = 'f65435f9ab8548d7bfcbe18e1247180e'
PYTHON_SEAL = 'ee5c7c2b914a174ad3f7248efcc1bd5a9e5908c86dc8ad164f52cddcb25fd127'
PLINK_SESSION = 'd0ec748b477e4297aac69ec57b5c959d'
PLINK_SEAL = 'b3b6aba624d6baea07163ff4a2b3804e9cb127e7a279611b4a580c46c24e48af'
KNOWN_BUILD = 'autonomics-validation-0806db6c6fb2498fa0fe03a8a49fd609.service'
PANEL = STUDY / '04_DATA/LD_REF_1000G_EUR_489'
INPUT_PATHS = [STUDY / '04_DATA/G0_MINIMUM_A/GCST90652391.h.tsv.gz',
    STUDY / '04_DATA/G0_MINIMUM_A/GCST90002393.h.tsv.gz', STUDY / AUDIT / 'A_ANALYSIS_CONFIG.json',
    STUDY / AUDIT / 'G0_V432_CERTIFICATE.json', STUDY / '02_EXECUTION/prepare_minimum_g0.py',
    STUDY / '02_EXECUTION/verify_minimum_ld.py', STUDY / '04_SOFTWARE/bin/plink', PANEL / 'manifest.json',
    STUDY / '02_EXECUTION/SOFTWARE_LOCK.tsv']
SCOPE = 'FROZEN_X01_M06_RAW_QC_AND_PLINK_QUALIFICATION_ONLY_NOT_MR_OR_G0'


def ordinary(path):
    require(path.is_absolute() and path.resolve(strict=True) == path and
        not any(parent.is_symlink() for parent in [path, *path.parents]) and stat.S_ISREG(path.lstat().st_mode),
        'Unaliased canonical regular source required')
    return path


def source_facts(paths, contract):
    require(len(paths) == len(contract['inputs']) == 9, 'Exact nine source roles required')
    facts = []
    for index, (path, expected) in enumerate(zip(paths, contract['inputs'], strict=True)):
        before = ordinary(path).stat()
        require(expected['port'] == index and path.name == expected['name'] and
            before.st_size == expected['bytes'], 'Source size or role differs')
        actual = digest(path)
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mode) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mode) and actual == expected['sha256'],
            'Canonical source changed or differs from frozen identity')
        facts.append(dict(port=index, name=path.name, bytes=before.st_size, sha256=actual,
            resolved_path=str(path), device=before.st_dev, inode=before.st_ino, mode=stat.S_IMODE(before.st_mode)))
    return facts


def panel_facts(panel, manifest):
    entries = manifest['files']
    expected_names = {f'1000G.EUR.QC.{chromosome}.{suffix}' for chromosome in range(1, 23)
                      for suffix in ['bed', 'bim', 'fam']}
    require(len(entries) == 66 and {item['path'] for item in entries} == expected_names,
        'Complete unique 66-file panel identity required')
    require(sum(item['size'] for item in entries) == 1593837597, 'Exact frozen panel byte budget differs')
    result = {}
    for entry in entries:
        path = ordinary(panel / entry['path'])
        info = path.stat()
        require(info.st_size == entry['size'] and 'sha256:' + digest(path) == entry['sha256'], 'Frozen panel payload differs')
        if path.suffix == '.fam':
            with path.open() as handle:
                require(sum(1 for _ in handle) == 489, 'Exact 489-participant panel required')
        result[entry['path']] = dict(bytes=info.st_size, sha256=entry['sha256'], device=info.st_dev, inode=info.st_ino)
    return result


def check_known_build(text, actual_exit):
    values = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    require(set(values) == {'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlPID'} and
        actual_exit in {0, 1} and values['LoadState'] in {'loaded', 'not-found'} and
        values['ActiveState'] in {'inactive', 'failed'} and values['SubState'] in {'dead', 'failed'} and
        values['MainPID'] == values['ControlPID'] == '0', 'Known large build is active or cannot be proven stopped')
    return values


def resource_admission(output):
    command = ['/usr/bin/systemctl', '--user', 'show', KNOWN_BUILD, '--property=LoadState', '--property=ActiveState',
               '--property=SubState', '--property=MainPID', '--property=ControlPID']
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (output / 'known-build.stdout').write_text(result.stdout)
    (output / 'known-build.stderr').write_text(result.stderr)
    write(output / 'known-build-observation.json', dict(unit=KNOWN_BUILD, command=command, actual_exit=result.returncode))
    build = check_known_build(result.stdout, result.returncode)
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    free = shutil.disk_usage(output).free
    result = subprocess.run(['/usr/bin/btrfs', 'filesystem', 'usage', '-b', '/home'],
        capture_output=True, text=True, timeout=30)
    (output / 'btrfs.stdout').write_text(result.stdout)
    (output / 'btrfs.stderr').write_text(result.stderr)
    require(result.returncode == 0, 'Actual Btrfs accounting unavailable')
    unallocated = re.search(r'^\s*Device unallocated:\s*(\d+)\s*$', result.stdout, re.MULTILINE)
    metadata = re.search(r'^Metadata,DUP: Size:\s*(\d+), Used:\s*(\d+) \([\d.]+%\)$', result.stdout, re.MULTILINE)
    require(unallocated and metadata and int(unallocated[1]) >= 2 * 1024**3 and int(metadata[2]) / int(metadata[1]) < .9 and
        available >= 6 * 1024**3 and free >= 4 * 1024**3, 'Current memory/disk/Btrfs task plus system reserve inadequate')
    write(output / 'resource-admission.json', dict(mem_available_bytes=available, disk_free_bytes=free,
        container_memory_bytes=2 * 1024**3, container_cpus=1, required_system_reserve_bytes=4 * 1024**3,
        known_build_current_observation=build, btrfs_unallocated_bytes=int(unallocated[1]),
        btrfs_metadata_size=int(metadata[1]), btrfs_metadata_used=int(metadata[2]),
        maximum_our_heavy_containers=1, global_idle_or_peak_memory_guaranteed=False))


def prerequisite_archives(archives):
    python = verify_archive(archives, PYTHON_SESSION, PYTHON_SEAL)
    plink = verify_archive(archives, PLINK_SESSION, PLINK_SEAL)
    require(python['positive_worker_exit_verified'] and plink['positive_worker_exit_verified'], 'Runtime/source proof worker must have actual zero exit')
    runtime = json.loads((Path(python['artifact_root']) / 'permanent/frozen-a-python-runtime/verification.json').read_text())
    author = json.loads((Path(plink['artifact_root']) / 'permanent/frozen-a-plink-official-source/EVIDENCE.json').read_text())
    require(runtime['status'] == 'OFFICIAL_CPYTHON_3_14_7_IMAGE_INSTALLED_NONFIT_SMOKE_ONLY' and
        runtime['image'] == IMAGE and runtime['config_sha256'] == CONFIG and runtime['actual_smoke']['version'] == '3.14.7' and
        runtime['original_software_owner_sha256'] == OWNER_SHA and runtime['original_software_owner_unchanged'] is True and
        runtime['g0_granted'] is False and author['passed'] is True and author['canonical_unchanged'] is True and
        author['author_binary']['sha256'] == '03ed6dd8882fddee7a89396c59ea56e4b17bbc4411d3049910e5d713fc8a135f' and
        author['author_binary']['bytes'] == 41730792 and author['author_archive']['status'] == 200 and
        author['author_archive']['url'] == 'https://s3.amazonaws.com/plink1-assets/plink_linux_x86_64_20231211.zip' and
        author['executable_executed'] is False and author['g0_granted'] is False, 'Exact official Python and author PLINK proof required')
    return runtime, [dict(session=record['session'], manifest_sha256=record['manifest_sha256'],
        all_members_rehashed=True, files=record['files'], bytes=record['bytes']) for record in [python, plink]]


def backend(output, runtime):
    require(digest(ordinary(OWNER)) == OWNER_SHA, 'Original shared software owner differs')
    owner = json.loads(OWNER.read_text())
    for key in ['storage', 'runroot']:
        expected = owner[key]
        actual = Path(expected['path']).stat()
        require((actual.st_dev, actual.st_ino, actual.st_uid, actual.st_gid) ==
            (expected['device'], expected['inode'], expected['uid'], expected['gid']), 'Shared runtime ownership differs')
    shim = ordinary(Path(os.environ['AUTONOMICS_PODMAN_PROGRAM']))
    require("'--tmpdir'" in shim.read_text(), 'Managed ownership-aware runtime entry required')
    prefix = [str(shim), *owner['runtime_backend']]
    result = subprocess.run([*prefix, 'image', 'inspect', IMAGE], capture_output=True, text=True, timeout=60)
    (output / 'image-inspect.stdout.json').write_text(result.stdout)
    (output / 'image-inspect.stderr.log').write_text(result.stderr)
    require(result.returncode == 0, 'Already installed immutable runtime required; no pull fallback')
    records = json.loads(result.stdout)
    require(len(records) == 1 and records[0]['Digest'] == IMAGE.split('@', 1)[1] and
        records[0]['Id'].removeprefix('sha256:') == CONFIG and
        records[0]['RootFS']['Layers'] == runtime['installed_diff_ids'], 'Actual fixed Python image identity differs')
    write(output / 'runtime-identity.json', dict(owner_sha256=OWNER_SHA, managed_shim_sha256=digest(shim),
        image=IMAGE, config_sha256=CONFIG, no_pull=True, no_build=True, production_restarted=False))
    return prefix


def execute(prefix, source, directory, definition, *, bad=False):
    inputs = list(INPUT_PATHS)
    if bad:
        bad_config = Path(os.environ['TMPDIR']) / 'wrong-frozen-a-config.json'
        bad_config.write_bytes(inputs[2].read_bytes() + b'\n')
        inputs[2] = bad_config
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=2g',
        '--pids-limit=64', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=64m', '-v', str(source) + ':/code:ro', '-v', str(directory) + ':/work:rw',
        '-v', str(PANEL) + ':/panels/ld_ref:ro', '-e', 'PYTHONDONTWRITEBYTECODE=1']
    for parent in sorted({path.parent for path in inputs}):
        command += ['-v', str(parent) + ':' + str(parent) + ':ro']
    for index, path in enumerate(inputs):
        command += ['-e', 'AUTONOMICS_INPUT' + str(index) + '=' + str(path)]
    for index, port in enumerate(definition['ports']['outputs']):
        command += ['-e', 'AUTONOMICS_OUTPUT' + str(index) + '=/work/' + port['path']]
    command += ['--entrypoint=python3', IMAGE, '-I', '-B', '/code/' + definition['command']['script_file']]
    write(directory / 'command.json', command)
    result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    (directory / 'stdout.log').write_text(result.stdout)
    (directory / 'stderr.log').write_text(result.stderr)
    write(directory / 'execution.json', dict(actual_exit=result.returncode, image=IMAGE,
        container_memory_bytes=2 * 1024**3, method_fit=False, g0_granted=False))
    return result


def table(path):
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t', strict=True)
        rows = list(reader)
    require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
        all(None not in row and all(value is not None for value in row.values()) for row in rows), 'Complete rectangular table required')
    return rows


def validate_commands(executions, qc, ld):
    require(len(executions) == 26, 'Exactly thirteen clump and thirteen paircheck commands required')
    grouped = [[item for item in executions if item['phase'] == phase] for phase in ['clump', 'haplotype_paircheck']]
    require(all(len(group) == 13 for group in grouped) and len({item['chromosome'] for item in grouped[0]}) == 13 and
        [item['chromosome'] for item in grouped[0]] == sorted(item['chromosome'] for item in grouped[0]) ==
        [item['chromosome'] for item in grouped[1]], 'Complete uniquely ordered chromosome executions required')
    for group, original, phase in zip(grouped, [qc['commands'], ld['commands']], ['clump', 'haplotype_paircheck'], strict=True):
        require(len(original) == 13, 'Original command record incomplete')
        for item, recorded in zip(group, original, strict=True):
            argv = item['argv']
            chromosome = item['chromosome']
            require(type(chromosome) is int and 1 <= chromosome <= 22 and type(item['actual_exit']) is int and
                item['actual_exit'] == 0 and recorded == dict(argv=argv, exit=0), 'Actual PLINK command failed or source receipt differs')
            project = Path(argv[0]).parents[2]
            output = project / '03_AUDIT/G0_v4.3.2_2026-10-11'
            prefix = [str(project / '04_SOFTWARE/bin/plink'), '--bfile', f'/panels/ld_ref/1000G.EUR.QC.{chromosome}']
            if phase == 'clump':
                expected = prefix + ['--clump', str(output / 'A_CLUMP_INPUT.tsv'), '--clump-p1', '5e-8', '--clump-p2', '1',
                    '--clump-r2', '0.001', '--clump-kb', '10000', '--threads', '1', '--memory', '1024', '--out', str(output / 'clumping' / f'chr{chromosome}')]
            else:
                expected = prefix + ['--extract', str(output / 'clumping/retained_ids.txt'), '--r2', 'dprime', '--ld-window', '99999',
                    '--ld-window-kb', '10000', '--ld-window-r2', '0', '--threads', '1', '--memory', '1024', '--out',
                    str(output / 'clumping' / f'haplotype_paircheck_chr{chromosome}')]
            require(argv == expected and str(project).startswith('/work/.frozen-a-input-stage-'), 'Exact unchanged source PLINK argv required')


def validate_official_archive(path, provenance, instruments, summary):
    declared = provenance['official_archive_members']
    require(isinstance(declared, list) and 0 < len(declared) <= 128 and
        len({item['path'] for item in declared}) == len(declared), 'Complete unique official artifact inventory required')
    expected = {item['path']: item for item in declared}
    observed = []
    total = 0
    with tarfile.open(path, 'r:') as archive:
        members = archive.getmembers()
        require(len(members) == len(expected) and {item.name for item in members} == set(expected), 'Full official tar membership differs')
        for member in members:
            name = Path(member.name)
            require(member.isfile() and len(name.parts) == 2 and name.parts[0] == 'clumping' and
                name.name not in {'.', '..'} and not name.is_absolute() and member.size <= 16 * 1024**2,
                'Only bounded ordinary stage-confined official files allowed')
            total += member.size
            require(total <= 16 * 1024**2, 'Official artifact budget exceeded')
            payload = archive.extractfile(member).read(16 * 1024**2 + 1)
            record = expected[member.name]
            require(len(payload) == member.size == record['bytes'] and hashlib.sha256(payload).hexdigest() == record['sha256'],
                'Official artifact payload differs')
            if name.name.startswith('haplotype_paircheck_chr') and name.suffix == '.ld':
                lines = payload.decode().splitlines()
                require(lines, 'Official LD header missing')
                header = lines[0].split()
                for line in lines[1:]:
                    values = line.split()
                    require(len(values) == len(header), 'Official LD row truncated')
                    observed.append(dict(zip(header, values, strict=True)))
    positions = {row['snp']: (int(row['chr37']), int(row['pos37'])) for row in instruments}
    require(len(instruments) == len(positions) == 39, 'All 39 retained instrument identities required')
    pairs = {tuple(sorted([first, second])) for first, second in itertools.combinations(positions, 2)
        if positions[first][0] == positions[second][0] and abs(positions[first][1] - positions[second][1]) <= 10000000}
    actual = {}
    for row in observed:
        first, second = row['SNP_A'], row['SNP_B']
        pair = tuple(sorted([first, second]))
        require(pair in pairs and pair not in actual and
            (int(row['CHR_A']), int(row['BP_A'])) == positions[first] and
            (int(row['CHR_B']), int(row['BP_B'])) == positions[second] and 0 <= float(row['R2']) < .001,
            'Official LD pair missing, duplicated, out of scope or invalid')
        actual[pair] = (positions[first][0], abs(positions[first][1] - positions[second][1]), float(row['R2']))
    published = {tuple(sorted([row['SNP1'], row['SNP2']])):
        (int(row['chr37']), int(row['distance_bp']), float(row['haplotype_r2'])) for row in summary}
    require(len(summary) == len(published) == len(actual) == len(pairs) == 11 and set(actual) == pairs and published == actual,
        'All eleven expected official/published LD pairs must match exactly')
    return dict(files=len(expected), bytes=total, complete_haplotype_pairs=11)


def validate_positive(directory, definition, contract, before, panel_before):
    names = [port['path'] for port in definition['ports']['outputs']]
    require(len(names) == len(set(names)) == 12 and all(ordinary(directory / name).stat().st_size > 0 for name in names),
        'All twelve real declared outputs must be ordinary, nonempty and readable')
    provenance = json.loads((directory / names[9]).read_text())
    require(provenance['scope'] == SCOPE and provenance['Python'] == '3.14.7' and
        provenance['PLINK_version'] == 'PLINK v1.90b7.2 64-bit (11 Dec 2023)' and provenance['input_sources'] == before and
        {name: {key: record[key] for key in ['bytes', 'sha256']} for name, record in provenance['panel_sources'].items()} ==
        {name: {key: record[key] for key in ['bytes', 'sha256']} for name, record in panel_before.items()} and
        provenance['panel_digest'] == contract['panel_digest'] and provenance['adapter_sha256'] == SOURCE_PINS['scripts/qualify.py'] and
        all(provenance[name] is True for name in ['original_qualify_a_executed', 'original_verify_minimum_ld_executed',
            'original_source_fallback_forbidden', 'sources_unchanged', 'panel_unchanged', 'tool_source_permissions_unchanged']) and
        all(provenance[name] is False for name in ['source_functions_modified', 'raw_inputs_copied', 'panel_copied',
            'harmonisation_executed', 'MR_estimates_computed', 'original_full_project_verifier_executed',
            'scientific_authorization_granted', 'formal_scientific_pass_granted', 'G0']), 'Complete official-source and false-authority provenance required')
    require(provenance['tool_copy_sha256'] == before[6]['sha256'], 'Private PLINK copy differs from the author-bound input')
    comparisons = []
    for name, expected in contract['existing_expected_outputs'].items():
        actual = directory / name
        canonical = STUDY / AUDIT / name
        require(digest(actual) == expected == digest(canonical) and actual.read_bytes() == canonical.read_bytes(),
            'Complete frozen small output differs: ' + name)
        comparisons.append(dict(name=name, bytes=actual.stat().st_size, sha256=expected))
    require(len(comparisons) == 7, 'Exactly seven byte-comparable frozen products required')
    for name, count in [('A_GWS_CANDIDATES.tsv', 3139), ('A_LD_EXCLUSIONS.tsv', 122), ('A_OUTCOME_MATCHES.tsv', 3139),
                        ('A_CLUMP_INPUT.tsv', 3017), ('A_LD_CLUMPED_INSTRUMENTS.tsv', 39), ('A_RETAINED_HAPLOTYPE_LD.tsv', 11)]:
        require(len(table(directory / name)) == count, 'Complete output row count differs: ' + name)
    qc = json.loads((directory / names[7]).read_text())
    ld = json.loads((directory / names[8]).read_text())
    validate_commands(provenance['subprocess_executions'], qc, ld)
    for name, actual in [(names[7], qc), (names[8], ld)]:
        canonical = json.loads((STUDY / AUDIT / name).read_text())
        require({key: value for key, value in actual.items() if key != 'commands'} ==
            {key: value for key, value in canonical.items() if key != 'commands'}, 'Complete source facts differ outside explicit new command paths')
    require(provenance['original_small_output_sha256'] == {name: digest(directory / name) for name in names[:9]},
        'Every original output must retain its actual hash')
    archive = validate_official_archive(directory / names[11], provenance, table(directory / names[5]), table(directory / names[6]))
    envelope = provenance['complete_pair_envelope']
    require(envelope['retained_variants'] == 39 and envelope['expected_pairs'] == envelope['observed_pairs'] == 11 and
        envelope['inclusive_window_bp'] == 10000000 and envelope['strict_haplotype_r2_upper_bound'] == .001 and
        envelope['maximum_haplotype_r2'] == .000912602 and 'independently recomputed 11' in (directory / names[10]).read_text(),
        'Complete pair envelope and original verification log required')
    return dict(ports=[dict(port=index, name=name, bytes=(directory / name).stat().st_size, sha256=digest(directory / name))
        for index, name in enumerate(names)], byte_equal_products=comparisons, official_artifacts=archive,
        clump_commands=13, paircheck_commands=13, raw_rows=[8086215, 39824509], g0_granted=False)


def validate_negative(result, directory, definition):
    normal = [port['path'] for index, port in enumerate(definition['ports']['outputs']) if index != 10]
    require(type(result.returncode) is int and result.returncode == 2 and
        ('Frozen input bytes differ: A_ANALYSIS_CONFIG.json' in result.stderr or
         'Frozen input SHA256 differs: A_ANALYSIS_CONFIG.json' in result.stderr) and
        not any((directory / name).exists() or (directory / name).is_symlink() for name in normal),
        'Exact source mismatch refusal required; OOM or runtime failure is not a successful guard')


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed validation required')
    require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) for value in SOURCE_PINS.values()),
        'Final two-GiB source is not yet frozen; real execution unavailable')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-input-qualification'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    resource_admission(output)
    runtime, prerequisites = prerequisite_archives(Path.home() / '.local/state/autonomics/validation-archives')
    write(output / 'verified-prerequisites.json', prerequisites)
    source = output / 'source'
    source.mkdir()
    for name, expected in SOURCE_PINS.items():
        require(digest(ordinary(FAMILY / name)) == expected, 'Candidate source changed')
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FAMILY / name, target)
        require(digest(target) == expected, 'Candidate source snapshot differs')
    contract = json.loads((source / 'contracts/source-lock.json').read_text())
    manifest = tomllib.loads((source / 'manifest.toml').read_text())
    require(manifest['plugin_name'] == 'frozen-a-input-qualification' and manifest['image']['reference'] == IMAGE and
        len(manifest['nodes']) == 1 and manifest['nodes'][0]['kind'] == 'frozen_a_v432_input_qualification', 'Exact official raw-QC kind required')
    definition = manifest['nodes'][0]
    require(len(definition['ports']['inputs']) == 9 and len(definition['ports']['outputs']) == 12 and
        not definition.get('params') and definition['resources']['memory'] == '2Gi', 'Exact nine-input/twelve-output two-GiB contract required')
    prefix = backend(output, runtime)
    before = source_facts(INPUT_PATHS, contract)
    panel_manifest = json.loads(INPUT_PATHS[7].read_text())
    panel_before = panel_facts(PANEL, panel_manifest)
    positive = output / 'positive'
    positive.mkdir()
    result = execute(prefix, source, positive, definition)
    require(result.returncode == 0, 'Actual original raw QC and official PLINK failed')
    checked = validate_positive(positive, definition, contract, before, panel_before)
    write(output / 'positive-verification.json', checked)
    negative = output / 'wrong-config'
    negative.mkdir()
    result = execute(prefix, source, negative, definition, bad=True)
    validate_negative(result, negative, definition)
    require(before == source_facts(INPUT_PATHS, contract) and panel_before == panel_facts(PANEL, panel_manifest) and
        digest(OWNER) == OWNER_SHA and all(digest(FAMILY / name) == expected == digest(source / name)
        for name, expected in SOURCE_PINS.items()), 'Original input/panel/source/owner changed during direct proof')
    post = original_postcheck(output)
    write(output / 'verification.json', dict(status='SCOPED_DIRECT_FROZEN_RAW_QC_OFFICIAL_PLINK_PROVEN_DAG_PENDING',
        source_sha256=SOURCE_PINS, prerequisites=prerequisites, actual_inputs=9, actual_outputs=12,
        full_byte_equal_small_products=7, retained_IVs=39, complete_haplotype_pairs=11,
        clump_commands=13, paircheck_commands=13, negative_config_actual_exit=2, negative_normal_outputs=0,
        raw_inputs_copied=False, panel_copied=False, canonical_inputs_unchanged=True, panel_unchanged=True,
        original_post_verifier=post, current_DAG_executed=False, harmonisation_executed=False,
        MR_estimates_computed=False, production_restarted=False, current_daemon_verified=False,
        scientific_release_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
