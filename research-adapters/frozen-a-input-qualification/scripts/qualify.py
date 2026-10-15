import contextlib
import csv
import hashlib
import importlib.util
import importlib.machinery
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile


INPUT_PINS = [
    ('GCST90652391.h.tsv.gz', 242104432, 'ed3b562cd73337e23d31c5facf8d2646eeb4399b14003513729f85743c5d4f16'),
    ('GCST90002393.h.tsv.gz', 2577239641, '8d0d508e5373af82839ed92a5dc9c175779ac2ad02dc8566c087b85ff77b568f'),
    ('A_ANALYSIS_CONFIG.json', 3499, '8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f'),
    ('G0_V432_CERTIFICATE.json', 2324, 'aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2'),
    ('prepare_minimum_g0.py', 11745, 'dfd51939dd2d7d6c5ed9322c047a86df0f65cbc0ac5522e69c008c8a698e9208'),
    ('verify_minimum_ld.py', 2841, '34ac788b92f17a8f2ce19596108eb8f7e5d1c21dbcf448b38e6c61e90dc3f7b0'),
    ('plink', 41730792, '03ed6dd8882fddee7a89396c59ea56e4b17bbc4411d3049910e5d713fc8a135f'),
    ('manifest.json', 11272, 'fe6a3d9717ea70714dcf1c8c9d15b2790501f030a93283042adebab3e8f1ed2b'),
    ('SOFTWARE_LOCK.tsv', 2319, '3deee8b8e390fc1da21886c170241515889c06adab0cbe74bc31c9d5d87675d6'),
]
OUTPUTS = ['A_INPUT_MANIFEST.json', 'A_GWS_CANDIDATES.tsv', 'A_LD_EXCLUSIONS.tsv',
    'A_OUTCOME_MATCHES.tsv', 'A_CLUMP_INPUT.tsv', 'A_LD_CLUMPED_INSTRUMENTS.tsv',
    'A_RETAINED_HAPLOTYPE_LD.tsv', 'A_QC_AND_LD.json', 'A_LD_PAIRWISE_ACCEPTANCE.json',
    'INPUT_METHOD_PROVENANCE.json', 'qualification.log', 'official-artifacts.tar']
EXPECTED_OUTPUT_SHA = {
    'A_INPUT_MANIFEST.json': '63cc4a1494778194996a8f349e430184ca0341e36404830624960867ba0ea185',
    'A_GWS_CANDIDATES.tsv': 'ab2708dd0500d72f7505c3187542c58e78e4674251b737d1e4c3e62b8b72d99a',
    'A_LD_EXCLUSIONS.tsv': 'bf60396a0b6dfa24e5208656a742af58d6f16bbc18ca6e5495ee543bc8c528fd',
    'A_OUTCOME_MATCHES.tsv': '20b5269c35c322a5491138cf5a95d8c0ebff085ca12a6fe0c09c9d472fec30cd',
    'A_CLUMP_INPUT.tsv': '52a140535afede920ed6c7cf1af62ec27ff4b75fd87b6679c5f08476871b8910',
    'A_LD_CLUMPED_INSTRUMENTS.tsv': '254c57122637840e6dc4f952e6a73ba1e660063442e7a2b2d6b5e194db25d85a',
    'A_RETAINED_HAPLOTYPE_LD.tsv': 'ad84c8501b97a0913a3ace84cb137fbb8ca009b773d34a759da3f72a829989b4',
}
PANEL = Path('/panels/ld_ref')
PANEL_DIGEST = 'sha256:9f483fd11fbb2e73a97ab1af172e45e569c7b8ed7edec5572e35a2b3fa614b21'
PLINK_VERSION = 'PLINK v1.90b7.2 64-bit (11 Dec 2023)'
ORIGINAL_SOURCE_LOCATIONS = [
    Path('/home/zj-normal/Downloads/autonomics_data/GCST90652391/harmonised/GCST90652391.h.tsv.gz'),
    Path('/home/zj-normal/Downloads/autonomics_data/data_sets/gwas_iv_audit/GCST90002393/harmonised/GCST90002393.h.tsv.gz'),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def regular(path):
    require(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode), 'Ordinary nonlinked file required')
    return path


def identity(path):
    info = regular(path).lstat()
    return info.st_dev, info.st_ino, info.st_size, digest(path)


def source_records(paths):
    require(len(paths) == len(INPUT_PINS), 'Exactly nine frozen inputs required')
    records = []
    for index, (path, (name, size, expected)) in enumerate(zip(paths, INPUT_PINS, strict=True)):
        info = regular(path).stat()
        require(info.st_size == size, 'Frozen input bytes differ: ' + name)
        actual = digest(path)
        require(actual == expected, 'Frozen input SHA256 differs: ' + name)
        records.append(dict(port=index, name=name, bytes=size, sha256=actual,
            resolved_path=str(path), device=info.st_dev, inode=info.st_ino, mode=stat.S_IMODE(info.st_mode)))
    return records


def table(path):
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t', strict=True)
        rows = list(reader)
    require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)) and
        all(None not in row and all(value is not None for value in row.values()) for row in rows),
        'Complete rectangular table required')
    return rows


def panel_records(panel, manifest_path):
    manifest = json.loads(regular(manifest_path).read_text())
    require(digest(manifest_path) == INPUT_PINS[7][2] and manifest['digest'] == PANEL_DIGEST and manifest['metadata']['population'] == 'EUR' and
        manifest['metadata']['genome_build'] == 'GRCh37', 'Exact frozen EUR/GRCh37 panel required')
    embedded_manifest = panel / 'manifest.json'
    if embedded_manifest.exists() or embedded_manifest.is_symlink():
        require(regular(embedded_manifest).read_bytes() == manifest_path.read_bytes(), 'Conflicting mounted panel manifest')
    expected_names = {f'1000G.EUR.QC.{chromosome}.{suffix}' for chromosome in range(1, 23) for suffix in ['bed', 'bim', 'fam']}
    entries = manifest['files']
    require(len(entries) == 66 and {item['path'] for item in entries} == expected_names and
        len({item['path'] for item in entries}) == 66, 'Complete unique 66-file panel manifest required')
    records = {}
    for item in entries:
        path = regular(panel / item['path'])
        require(type(item['size']) is int and item['size'] > 0 and path.stat().st_size == item['size'] and
            'sha256:' + digest(path) == item['sha256'], 'Frozen panel payload differs: ' + item['path'])
        info = path.stat()
        records[item['path']] = dict(bytes=info.st_size, sha256=item['sha256'], device=info.st_dev, inode=info.st_ino)
        if path.suffix == '.fam':
            with path.open() as handle:
                require(sum(1 for _ in handle) == 489, 'Exactly 489 LD reference participants required')
    return records


def complete_pair_envelope(instruments, observed, summary):
    positions = {}
    for row in instruments:
        identifier = row['snp']
        chromosome, position = int(row['chr37']), int(row['pos37'])
        require(identifier and identifier not in positions and 1 <= chromosome <= 22 and position > 0,
            'Unique positive retained variant coordinates required')
        positions[identifier] = chromosome, position
    expected = {tuple(sorted([first, second])) for first, second in itertools.combinations(positions, 2)
        if positions[first][0] == positions[second][0] and abs(positions[first][1] - positions[second][1]) <= 10000000}
    actual = {}
    for row in observed:
        first, second = row['SNP_A'], row['SNP_B']
        require(first != second and first in positions and second in positions, 'LD pair references unretained variants')
        pair = tuple(sorted([first, second]))
        require(pair in expected and pair not in actual, 'LD pair duplicate or outside the inclusive 10Mb family')
        require((int(row['CHR_A']), int(row['BP_A'])) == positions[first] and
            (int(row['CHR_B']), int(row['BP_B'])) == positions[second], 'Official LD pair coordinates differ')
        value = float(row['R2'])
        require(math.isfinite(value) and 0 <= value < .001, 'Official haplotype LD must be finite and strictly below 0.001')
        actual[pair] = (positions[first][0], abs(positions[first][1] - positions[second][1]), value)
    require(set(actual) == expected, 'Complete expected LD pair family required; missing pairs cannot pass')
    published = {}
    for row in summary:
        pair = tuple(sorted([row['SNP1'], row['SNP2']]))
        require(pair not in published, 'Duplicate published haplotype pair')
        published[pair] = int(row['chr37']), int(row['distance_bp']), float(row['haplotype_r2'])
    require(published == actual, 'Original published haplotype pair table differs from all official pairs')
    return dict(retained_variants=len(positions), expected_pairs=len(expected), observed_pairs=len(actual),
        inclusive_window_bp=10000000, strict_haplotype_r2_upper_bound=.001,
        maximum_haplotype_r2=max((value[2] for value in actual.values()), default=None))


class RestrictedPLINK:
    def __init__(self, program, panel, output):
        self.program, self.panel, self.output = program, panel, output
        self.executions = []

    def run(self, command, **kwargs):
        require(isinstance(command, list) and len(command) >= 3 and command[0] == str(self.program),
            'Source fallback copy, downloader or non-PLINK subprocess forbidden')
        require(command[1] == '--bfile', 'Only frozen PLINK bfile commands permitted')
        reference = Path(command[2])
        require(reference.parent == self.panel and reference.name.startswith('1000G.EUR.QC.'), 'Exact frozen panel prefix required')
        chromosome = int(reference.name.removeprefix('1000G.EUR.QC.'))
        require(1 <= chromosome <= 22, 'Autosomal panel required')
        if command[3:4] == ['--clump']:
            expected = [str(self.program), '--bfile', str(reference), '--clump', str(self.output / 'A_CLUMP_INPUT.tsv'),
                '--clump-p1', '5e-8', '--clump-p2', '1', '--clump-r2', '0.001', '--clump-kb', '10000',
                '--threads', '1', '--memory', '1024', '--out', str(self.output / 'clumping' / f'chr{chromosome}')]
            phase = 'clump'
        else:
            expected = [str(self.program), '--bfile', str(reference), '--extract', str(self.output / 'clumping/retained_ids.txt'),
                '--r2', 'dprime', '--ld-window', '99999', '--ld-window-kb', '10000', '--ld-window-r2', '0',
                '--threads', '1', '--memory', '1024', '--out', str(self.output / 'clumping' / f'haplotype_paircheck_chr{chromosome}')]
            phase = 'haplotype_paircheck'
        require(command == expected and kwargs == dict(capture_output=True, text=True),
            'Original PLINK argv, phased statistic or resource contract differs')
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        self.executions.append(dict(phase=phase, chromosome=chromosome, argv=command, actual_exit=result.returncode))
        return result


def load_source(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    specification = importlib.util.spec_from_loader(name, loader)
    require(specification is not None and specification.loader is not None, 'Original source loader unavailable')
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def run_qualification(inputs, stage):
    require(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 14, 7), 'Exact official CPython 3.14.7 required')
    sys.dont_write_bytecode = True
    before = source_records(inputs)
    panel_before = panel_records(PANEL, inputs[7])
    cfg, cert = [json.loads(inputs[index].read_text()) for index in [2, 3]]
    require(cfg['version'] == '4.3.2' and cfg['status'] == 'LOCKED' and cfg['enabled_edge'] == 'A_X01_M06' and
        cfg['exposure_role'] == 'LEGACY_EXPLORATORY' and cfg['overlap_class'] == 'O2' and cfg['primary_p_source'] == 'NA' and
        cfg['clump_p1'] == 5e-8 and cfg['clump_r2'] == .001 and cfg['clump_kb'] == 10000 and cfg['LD_samples'] == 489 and
        cert['A']['allowed'] is True and cert['A']['confirmatory_allowed'] is False, 'Frozen legacy configuration required')
    software = table(inputs[8])
    requirement = [row for row in software if row['component'] == 'genetic_summary_qc']
    require(len(requirement) == 1 and requirement[0]['version_or_commit'] == 'CPython3.14.7;PLINK1.90b7.2', 'Frozen QC software lock differs')
    require(not any(path.exists() or path.is_symlink() for path in ORIGINAL_SOURCE_LOCATIONS),
        'Original Downloads fallback locations must not be exposed to this container')
    root = stage / 'project'
    data = root / '04_DATA/G0_MINIMUM_A'
    output = root / '03_AUDIT/G0_v4.3.2_2026-10-11'
    tool = root / '04_SOFTWARE/bin/plink'
    for directory in [data, output, tool.parent]:
        directory.mkdir(parents=True)
    for index in [0, 1]:
        (data / INPUT_PINS[index][0]).symlink_to(inputs[index])
    shutil.copyfile(inputs[6], tool)
    tool.chmod(0o700)
    require(digest(tool) == INPUT_PINS[6][2], 'Owned official PLINK tool copy differs')
    version = subprocess.run([str(tool), '--version'], capture_output=True, text=True, timeout=30)
    require(version.returncode == 0 and version.stdout.strip() == PLINK_VERSION, 'Exact official PLINK version required')
    proxy = RestrictedPLINK(tool, PANEL, output)
    original = load_source('prepare_minimum_g0', inputs[4])
    original.ROOT, original.OUT, original.DATA, original.PANEL = root, output, data, PANEL
    original.subprocess = proxy
    original.qualify_a()
    verifier = load_source('verify_minimum_ld', inputs[5])
    verifier.subprocess = proxy
    require(not (output / 'A_RETAINED_PAIRWISE_LD.tsv').exists(), 'No historical genotype diagnostic may be injected')
    verifier.verify()
    observed = []
    for filename in sorted((output / 'clumping').glob('haplotype_paircheck_chr*.ld')):
        with filename.open() as handle:
            header = next(handle).split()
            for line in handle:
                values = line.split()
                require(len(values) == len(header), 'Complete official LD row required')
                observed.append(dict(zip(header, values, strict=True)))
    envelope = complete_pair_envelope(table(output / 'A_LD_CLUMPED_INSTRUMENTS.tsv'), observed,
        table(output / 'A_RETAINED_HAPLOTYPE_LD.tsv'))
    require(envelope['retained_variants'] == 39 and envelope['expected_pairs'] == 11 and
        sum(item['phase'] == 'clump' for item in proxy.executions) == 13 and
        sum(item['phase'] == 'haplotype_paircheck' for item in proxy.executions) == 13 and
        all(type(item['actual_exit']) is int and item['actual_exit'] == 0 for item in proxy.executions),
        'Complete original 13 clump and 13 paircheck executions required')
    for name, expected in EXPECTED_OUTPUT_SHA.items():
        require(digest(regular(output / name)) == expected, 'Original frozen qualification product differs: ' + name)
    qc = json.loads((output / 'A_QC_AND_LD.json').read_text())
    acceptance = json.loads((output / 'A_LD_PAIRWISE_ACCEPTANCE.json').read_text())
    require(qc['GWS_unique_SNPs'] == 3139 and qc['LD_eligible'] == 3017 and qc['LD_excluded'] == 122 and
        qc['clumped_N'] == 39 and qc['outcome_matches_rows'] == 3139 and qc['scientific_results_computed'] is False and
        acceptance['status'] == 'PASS' and acceptance['violations'] == [] and
        acceptance['genotype_r2_diagnostic_exceedances'] == [], 'Original QC or LD qualification facts differ')
    require(before == source_records(inputs) and panel_before == panel_records(PANEL, inputs[7]), 'Frozen source or panel changed during execution')
    require(digest(tool) == INPUT_PINS[6][2] and all((data / INPUT_PINS[index][0]).is_symlink() and
        (data / INPUT_PINS[index][0]).resolve(strict=True) == inputs[index] for index in [0, 1]),
        'Owned tool or zero-copy raw bindings changed during execution')
    for index, name in enumerate(OUTPUTS[:9]):
        shutil.copyfile(regular(output / name), stage / name)
    archive_members = []
    official_files = sorted((output / 'clumping').iterdir())
    require(len(official_files) <= 128 and sum(regular(path).stat().st_size for path in official_files) <= 16 * 1024**2,
        'Bounded complete official artifact inventory required')
    with tarfile.open(stage / OUTPUTS[11], 'x') as archive:
        for filename in official_files:
            regular(filename)
            require(filename.stat().st_size <= 16 * 1024**2, 'Bounded official clumping artifacts required')
            archive.add(filename, arcname='clumping/' + filename.name, recursive=False)
            archive_members.append(dict(path='clumping/' + filename.name, bytes=filename.stat().st_size, sha256=digest(filename)))
    provenance = dict(scope='FROZEN_X01_M06_RAW_QC_AND_PLINK_QUALIFICATION_ONLY_NOT_MR_OR_G0',
        Python=sys.version.split()[0], PLINK_version=version.stdout.strip(), input_sources=before,
        panel_sources=panel_before, panel_digest=PANEL_DIGEST, original_qualify_a_executed=True,
        original_verify_minimum_ld_executed=True, source_functions_modified=False, original_source_fallback_forbidden=True,
        raw_inputs_copied=False, panel_copied=False, tool_copy_sha256=digest(tool), tool_source_permissions_unchanged=True,
        subprocess_executions=proxy.executions, complete_pair_envelope=envelope, official_archive_members=archive_members,
        original_small_output_sha256={name: digest(stage / name) for name in OUTPUTS[:9]},
        adapter_sha256=digest(Path(__file__).resolve()), sources_unchanged=True, panel_unchanged=True,
        harmonisation_executed=False, MR_estimates_computed=False, original_full_project_verifier_executed=False,
        scientific_authorization_granted=False, formal_scientific_pass_granted=False, G0=False)
    (stage / OUTPUTS[9]).write_text(json.dumps(provenance, indent=2, allow_nan=False) + '\n')


def publish_outputs(input_values, output_values, compute):
    require(len(input_values) == 9 and len(output_values) == 12 and all(input_values) and all(output_values),
        'All nine input and twelve output paths required')
    inputs = [regular(Path(value).resolve(strict=True)) for value in input_values]
    require(len(set(inputs)) == 9, 'Distinct frozen input files required')
    parents = [Path(value).parent.resolve(strict=True) for value in output_values]
    require(all(parent.is_dir() for parent in parents) and len({parent.stat().st_dev for parent in parents}) == 1,
        'Existing same-filesystem output parents required')
    paths = [parent / Path(value).name for parent, value in zip(parents, output_values, strict=True)]
    require(len(set(paths)) == 12 and not set(paths) & set(inputs) and
        all(not path.exists() and not path.is_symlink() for path in paths), 'Refusing existing, aliased or duplicate outputs')
    input_identity = [(path.stat().st_dev, path.stat().st_ino, path.stat().st_size) for path in inputs]
    stage = Path(tempfile.mkdtemp(prefix='.frozen-a-input-stage-', dir=parents[0]))
    stage.chmod(0o700)
    stage_identity = stage.stat().st_dev, stage.stat().st_ino
    staged_log = stage / OUTPUTS[10]
    staged_log.touch(exist_ok=False)
    log_identity = identity(staged_log)
    published = []
    successful = False

    def check(record):
        destination, expected = record
        first = identity(destination)
        require(first == expected and identity(destination) == expected, 'Published artifact ownership or content changed')

    try:
        os.link(staged_log, paths[10])
        check((paths[10], log_identity))
        try:
            with staged_log.open('a') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                compute(inputs, stage)
            require(input_identity == [(path.stat().st_dev, path.stat().st_ino, path.stat().st_size) for path in inputs],
                'Input file identity changed during execution')
            final_log = paths[10], identity(staged_log)
            check(final_log)
            for index, name in enumerate(OUTPUTS):
                if index == 10:
                    continue
                source = regular(stage / name)
                require(source.stat().st_size > 0, 'Every normal output must be nonempty')
                record = paths[index], identity(source)
                os.link(source, paths[index])
                published.append(record)
                check(record)
            for record in [final_log, *published]:
                check(record)
            successful = True
        except BaseException as error:
            if ((stage.stat().st_dev, stage.stat().st_ino) == stage_identity and staged_log.exists() and
                    (staged_log.stat().st_dev, staged_log.stat().st_ino) == log_identity[:2]):
                with staged_log.open('a') as handle:
                    handle.write('BLOCKED: ' + str(error) + '\n')
            raise
    finally:
        if not successful:
            for destination, expected in reversed(published):
                try:
                    if identity(destination) == expected and identity(destination) == expected:
                        destination.unlink()
                    else:
                        print('BLOCKED: foreign or changed result preserved during rollback', file=sys.stderr)
                except (FileNotFoundError, ValueError):
                    pass
        try:
            if not stage.is_symlink() and (stage.stat().st_dev, stage.stat().st_ino) == stage_identity:
                shutil.rmtree(stage)
            else:
                print('BLOCKED: replaced staging directory preserved', file=sys.stderr)
        except FileNotFoundError:
            pass


def main():
    publish_outputs([os.environ.get('AUTONOMICS_INPUT' + str(index), '') for index in range(9)],
        [os.environ.get('AUTONOMICS_OUTPUT' + str(index), '') for index in range(12)], run_qualification)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('BLOCKED:', error, file=sys.stderr)
        raise SystemExit(2)
