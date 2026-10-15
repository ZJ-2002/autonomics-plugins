"""Bounded fixed-image full-entry regression for two R publication repairs."""

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_b_publication_runtime as inherited
from tools import prove_h5ad_subset_official_runtime as runtime
from tools.prove_frozen_a_family_runtime import stopped

BASELINE = 'd3065953a513f5b5f07e436b8ff2da62177341cd'
FAMILIES = {
    'deseq2': {
        'manifest': 'plugins/deseq2/manifest.toml',
        'script': 'plugins/deseq2/deseq2_runner.R',
        'original': 'cb019c599face7715089df4c16157851b0403bef5f61a3166123ba913ba170f1',
        'fixed': 'ea10753445ba649cd87e74a8956c5974f9f7f1b8f4684d9ee6f7d982a5b80b34',
        'manifest_sha': '5720eeff4b44cd1285129b2f05d1a2fab780b150efa2c9d1a05421eae0f01782',
        'image': 'ghcr.io/zj-2002/deseq2@sha256:5931c509f7f30d44177033877a96b062bf8532d16e5762daebfa20564278a59f',
        'outputs': ['results.tsv', 'normalized_counts.tsv', 'size_factors.tsv', 'deseq2_dataset.rds', 'run_report.json'],
        'packages': {'DESeq2': '1.50.2', 'apeglm': '1.32.0'},
    },
    'limma': {
        'manifest': 'plugins/bulk-rnaseq/manifest.toml',
        'script': 'plugins/bulk-rnaseq/limma_voom_runner.R',
        'original': '4dd81e31f558b311da0fdbcc54415967d7cd237356b54d56cfed7ed284808dcf',
        'fixed': '1533681a19e415a1e4efabd7828b626613143fb451291dc1e175a1d017ea8e2f',
        'manifest_sha': 'd8c8344145cd8b75a79ed7e00ff3c399634ffc99cb7edf7d7bb58cedcd009f0e',
        'image': 'ghcr.io/zj-2002/bulk-rnaseq-official@sha256:8b280a45781160f3dc1f5bfac90862b8a85d7d2bf1b89146e418658cca4ca85a',
        'outputs': ['results.tsv', 'voom_weights.tsv', 'normalized_expression.tsv', 'contrast_summary.tsv', 'run_report.json'],
        'packages': {'limma': '3.66.0', 'edgeR': '4.8.2', 'statmod': '1.5.2'},
    },
}
INNER = 'tools/check_r_publication_runtime.R'
INNER_SHA = 'e70b1421fa40c5bc3fd177166d9dcabb8dee53b3e07c80676f0551fd19473dce'
HELPERS = {
    'tools/prove_b_publication_runtime.py': '35dd333d3d3ac46b491ce2d2deb90c76bd2815ca29cf34f9ab64f64dbf41e964',
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
}
FAULTS = ('same-inode-success', 'same-inode-later-link-failure', 'foreign-stage-child',
    'last-link-rewrites-first', 'staged-before-link')
CASES = ('original-normal', 'fixed-normal', *('fixed-' + mode for mode in FAULTS))
require, fact, write, strict_json = runtime.require, runtime.fact, runtime.write, runtime.strict_json


def sources():
    pins = {INNER: INNER_SHA, **HELPERS}
    for item in FAMILIES.values():
        pins[item['manifest']] = item['manifest_sha']
        pins[item['script']] = item['fixed']
    observed = {name: fact(ROOT / name) for name in pins}
    require(all(observed[name]['sha256'] == expected for name, expected in pins.items()),
        'Exact reviewed R scripts, manifests, inner or inherited runtime helper changed')
    return observed


def inspect_image(prefix, directory, label, image):
    observed = subprocess.run([*prefix, 'image', 'inspect', image], capture_output=True, text=True, timeout=60)
    (directory / (label + '.stdout.json')).write_text(observed.stdout)
    (directory / (label + '.stderr')).write_text(observed.stderr)
    require(type(observed.returncode) is int and observed.returncode == 0,
        'Fixed R image not available on the admitted default backend; no pull or fallback')
    records = strict_json(observed.stdout)
    require(isinstance(records, list) and len(records) == 1, 'Exactly one actual fixed image required')
    image_record = records[0]
    config_sha = image_record['Id'].removeprefix('sha256:')
    requested_sha = image.split('@sha256:', 1)[1]
    require(re.fullmatch('[0-9a-f]{64}', config_sha), 'Actual configuration digest required')
    image_store = Path.home() / '.local/share/containers/storage/overlay-images' / config_sha
    encoded = lambda value: '=' + base64.b64encode(value.encode()).decode()
    manifest_path = image_store / encoded('manifest-sha256:' + requested_sha)
    config_path = image_store / encoded('sha256:' + config_sha)
    manifest_bytes, config_bytes = manifest_path.read_bytes(), config_path.read_bytes()
    require(hashlib.sha256(manifest_bytes).hexdigest() == requested_sha and
        hashlib.sha256(config_bytes).hexdigest() == config_sha and
        fact(manifest_path)['sha256'] == requested_sha and fact(config_path)['sha256'] == config_sha,
        'Actual parsed manifest/configuration buffers must match requested immutable identities')
    manifest, configuration = strict_json(manifest_bytes), strict_json(config_bytes)
    require(manifest['config']['digest'] == 'sha256:' + config_sha and
        configuration['architecture'] == 'amd64' and configuration['os'] == 'linux' and
        image_record['RootFS']['Layers'] == configuration['rootfs']['diff_ids'],
        'Actual manifest/configuration/ordered rootfs layers differ')
    primary = image_record['Digest'].removeprefix('sha256:')
    require(re.fullmatch('[0-9a-f]{64}', primary), 'Installed primary manifest digest required')
    if primary != requested_sha:
        alternate_path = image_store / encoded('manifest-sha256:' + primary)
        alternate = alternate_path.read_bytes()
        require(hashlib.sha256(alternate).hexdigest() == primary and fact(alternate_path)['sha256'] == primary and
            strict_json(alternate)['config']['digest'] == 'sha256:' + config_sha,
            'Installed alternate manifest is not bound to the same exact configuration')
        (directory / (label + '-alternate-manifest.json')).write_bytes(alternate)
    (directory / (label + '-manifest.json')).write_bytes(manifest_bytes)
    (directory / (label + '-config.json')).write_bytes(config_bytes)
    return dict(reference=image, requested_manifest_sha256=requested_sha, config_sha256=config_sha,
        installed_primary_digest=image_record['Digest'], ordered_diff_ids=configuration['rootfs']['diff_ids'])


def snapshot(output, before):
    source = output / 'source'
    source.mkdir(mode=0o700)
    for relative, observed in before.items():
        target = source / 'fixed' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        require(fact(target)['sha256'] == observed['sha256'], 'Small exact technical source snapshot changed')
    originals = {}
    for label, item in FAMILIES.items():
        payload = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + item['script']])
        require(hashlib.sha256(payload).hexdigest() == item['original'], 'Published original R source differs')
        target = source / 'original' / item['script']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        originals[label] = fact(target)
    return source, originals


def container_command(prefix, source, output, label):
    item = FAMILIES[label]
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
        '--pids-limit=128', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=128m', '-e', 'TMPDIR=/tmp']
    for name in inherited.THREAD_VARIABLES:
        command.extend(['-e', name + '=1'])
    command.extend(['-v', str(source) + ':/source:ro', '-v', str(output) + ':/proof:rw',
        '--entrypoint=/opt/autonomics/Rscript-vanilla', item['image'],
        '/source/fixed/' + INNER, label, '/source/original/' + item['script'],
        '/source/fixed/' + item['script'], '/proof/' + label])
    return command


def run_inner(prefix, source, output, label):
    command = container_command(prefix, source, output, label)
    write(output / (label + '-command.json'), command)
    execution = subprocess.run(command, capture_output=True, text=True, timeout=1200)
    (output / (label + '.stdout')).write_text(execution.stdout)
    (output / (label + '.stderr')).write_text(execution.stderr)
    write(output / (label + '-execution.json'), dict(actual_exit=execution.returncode,
        image=FAMILIES[label]['image'], container_memory_bytes=1024**3, container_cpus=1,
        actual_DAG_executed=False, no_network=True, no_pull=True, no_build=True))
    require(type(execution.returncode) is int and execution.returncode == 0,
        'Actual fixed-image full-entry regression failed; no OOM/launch failure may count as expected refusal: ' + label)


def exact_integer(value, expected):
    return type(value) is int and value == expected


def validate_deseq_reports(original, fixed, original_md5, fixed_md5):
    comparisons = [copy.deepcopy(original), copy.deepcopy(fixed)]
    for report, expected in zip(comparisons, (original_md5, fixed_md5), strict=True):
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{32}', expected) and
            isinstance(report, dict) and isinstance(report.get('outputs'), dict) and
            isinstance(report['outputs'].get('dataset'), dict) and
            report['outputs']['dataset'].get('md5') == expected,
            'Each exact dataset.md5 must independently bind its own complete RDS bytes')
        report['outputs']['dataset']['md5'] = 'EACH_BOUND_OWN_COMPLETE_RDS_MD5'
    canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    require(canonical(comparisons[0]) == canonical(comparisons[1]),
        'Only the exact outputs.dataset.md5 field may differ between complete DESeq2 reports')
    return True


def md5_file(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'md5').hexdigest()


def validate_summary(value, label, directory=None):
    item = FAMILIES[label]
    require(value.get('schema') == 'TWO_R_PUBLICATION_FULL_ENTRY_RUNTIME_V1' and value.get('family') == label and
        exact_integer(value.get('actual_cases'), 7) and exact_integer(value.get('genes'), 200) and
        exact_integer(value.get('samples'), 12) and exact_integer(value.get('per_entry_seed'), 432202610),
        'Exact bounded seven-entry synthetic scope required')
    require(value.get('source_sha256') == dict(original=item['original'], fixed=item['fixed']) and
        value.get('scientific_body_AST_identical') is True and value.get('official_package_entries_executed') is True,
        'Complete unchanged official scientific body and exact source identities required')
    require(value.get('R_version') == '4.5.3' and isinstance(value.get('packages'), dict) and
        all(value['packages'].get(name) == version for name, version in item['packages'].items()) and
        isinstance(value['packages'].get('jsonlite'), str) and value['packages']['jsonlite'],
        'Actual frozen official runtime/package versions differ')
    for name in ('actual_DAG_executed', 'full_manifest_resource_certified', 'production_changed',
            'scientific_authorization_granted', 'g0_granted'):
        require(value.get(name) is False, 'Bounded runtime evidence cannot grant additional authority')
    records = value.get('records')
    require(isinstance(records, list) and [record.get('case') for record in records] == list(CASES),
        'All original/fixed normal and five exact full-entry publication controls must execute once')
    for record in records:
        mode = record.get('mode')
        require(record.get('complete_entry_sys_source_executed') is True and
            record.get('full_fit_before_publication') is True and record.get('no_scientific_authorization') is True and
            type(record.get('actual_link_calls')) is int and record['actual_link_calls'] > 0,
            'AST-only substitution, pre-fit failure or infrastructure failure cannot prove full entry')
        expected_mode = 'normal' if record['case'] in CASES[:2] else record['case'].removeprefix('fixed-')
        require(mode == expected_mode, 'Full-entry case/mode identity differs')
        success = mode in ('normal', 'foreign-stage-child')
        require(record.get('returned_success') is success, 'Unexpected normal/refusal outcome')
        if success:
            require(record.get('diagnostic') is None and exact_integer(record['actual_link_calls'], 5) and
                exact_integer(record.get('actual_present_ports'), 5), 'All five normal outputs must actually publish')
        else:
            diagnostic = ('output changed before publication completed' if mode == 'last-link-rewrites-first'
                else 'staged output changed before publication' if mode == 'staged-before-link'
                else 'published output identity or contents changed')
            require(record.get('diagnostic') == diagnostic and record.get('same_inode') is True and
                exact_integer(record['actual_link_calls'], 5 if mode == 'last-link-rewrites-first' else 1),
                'A targeted actual identity/content refusal is required, not arbitrary nonzero/OOM')
        if mode != 'normal':
            require(record.get('injected') is True and record.get('all_foreign_paths_preserved') is True and
                isinstance(record.get('foreign_paths'), list) and record['foreign_paths'],
                'All actual injected foreign files must remain intact')
            if directory is not None:
                for foreign in record['foreign_paths']:
                    require(isinstance(foreign, str) and foreign.startswith('/proof/' + label + '/') and
                        '..' not in Path(foreign).parts, 'Foreign technical evidence path escaped its own fixture')
                    actual_foreign = directory / Path(foreign).relative_to('/proof/' + label)
                    fact(actual_foreign)
                    require(actual_foreign.read_bytes() == b'EXPLICIT FOREIGN NONSCIENTIFIC BYTES\n',
                        'Actual foreign technical bytes were deleted or changed')
        else:
            require(record.get('injected') is False, 'Normal control cannot contain fault injection')
        products = record.get('products')
        require(isinstance(products, list) and len(products) == record['actual_present_ports'] and
            len({product.get('port') for product in products}) == len(products), 'Actual output census differs')
        for product in products:
            port = product.get('port')
            require(type(port) is int and 0 <= port < 5 and product.get('name') == item['outputs'][port],
                'Declared output port identity differs')
            if directory is not None:
                actual = fact(directory / record['case'] / product['name'])
                require(exact_integer(product.get('bytes'), actual['bytes']) and product.get('sha256') == actual['sha256'],
                    'Actual complete output differs from its observed bytes/hash')
    comparisons = value.get('complete_normal_port_comparisons')
    require(isinstance(comparisons, list) and [product.get('name') for product in comparisons] == item['outputs'],
        'All five old/new complete normal ports must be compared')
    for port, comparison in enumerate(comparisons):
        require(exact_integer(comparison.get('port'), port), 'Normal comparison port identity differs')
        if label == 'deseq2' and port == 3:
            require(comparison.get('complete_object_equal') is True and comparison.get('check_environment') is False and
                type(comparison.get('compressed_bytes_equal')) is bool and
                type(comparison.get('tolerance')) in (int, float) and comparison['tolerance'] == 0,
                'Complete DESeqDataSet comparison must disclose excluded environment identity')
        elif label == 'deseq2' and port == 4:
            require(type(comparison.get('complete_bytes_equal')) is bool and
                comparison.get('single_exact_dataset_md5_field_exception') is True and comparison.get('all_other_fields_exact') is True and
                isinstance(comparison.get('dataset_rds_md5'), dict),
                'DESeq2 report comparison must retain the single exact independently bound RDS hash exception')
            if directory is not None:
                original_md5 = md5_file(directory / 'original-normal' / item['outputs'][3])
                fixed_md5 = md5_file(directory / 'fixed-normal' / item['outputs'][3])
                require(comparison['dataset_rds_md5'] == dict(original=original_md5, fixed=fixed_md5),
                    'Recorded DESeq2 report RDS checksums differ from complete actual files')
                original_report = strict_json((directory / 'original-normal' / comparison['name']).read_text())
                fixed_report = strict_json((directory / 'fixed-normal' / comparison['name']).read_text())
                validate_deseq_reports(original_report, fixed_report, original_md5, fixed_md5)
        else:
            require(comparison.get('complete_bytes_equal') is True, 'Complete normal table/report bytes must agree')
        for version, case in (('original', 'original-normal'), ('fixed', 'fixed-normal')):
            recorded = comparison.get(version)
            require(isinstance(recorded, dict) and type(recorded.get('bytes')) is int and recorded['bytes'] > 0 and
                isinstance(recorded.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', recorded['sha256']),
                'Complete normal output identity required')
            if directory is not None:
                actual = fact(directory / case / comparison['name'])
                require(recorded == {key: actual[key] for key in ('bytes', 'sha256')}, 'Normal output was changed after reference comparison')
        observed_equal = comparison['original']['sha256'] == comparison['fixed']['sha256']
        equality_field = 'compressed_bytes_equal' if label == 'deseq2' and port == 3 else 'complete_bytes_equal'
        require(comparison[equality_field] is observed_equal, 'Observed complete byte equality must remain truthful')
    if label == 'deseq2':
        require(value.get('DESeq2_scope') == 'MEAN_DISPERSION_NONE_SHRINKAGE_ONLY_NOT_APEGLM_OR_ALL_FIT_BRANCHES' and
            value.get('parameters', {}).get('AUTONOMICS_DESEQ2_LFC_SHRINK') == 'none' and
            value['parameters'].get('AUTONOMICS_DESEQ2_FIT_TYPE') == 'mean', 'Only the explicit deterministic MLE branch was exercised')
    return value


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed light session required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'r-publication-runtime'
    output.mkdir(mode=0o700)
    own_before = fact(Path(__file__))
    shutil.copyfile(Path(__file__), output / 'driver.py')
    before = sources()
    initial_cgroup = runtime.cgroup_observation()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3 and shutil.disk_usage(output).free >= 1024**3, 'Two serial bounded fixtures plus host reserve unavailable')
    write(output / 'resource-admission.json', dict(parent=initial_cgroup, available_memory_bytes=available,
        parent_memory_max_bytes=2 * 1024**3, container_memory_bytes=1024**3, container_cpus=1, no_build=True))
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    shim_before = fact(shim)
    prefix = [str(shim), '--cgroup-manager=cgroupfs']
    for name in ('backend-before', 'backend-after', 'images'):
        (output / name).mkdir(mode=0o700)
    backend = runtime.default_backend(prefix, output / 'backend-before')
    images = {label: inspect_image(prefix, output / 'images', label + '-before', item['image']) for label, item in FAMILIES.items()}
    source, originals = snapshot(output, before)
    for item in FAMILIES.values():
        manifest = tomllib.loads((source / 'fixed' / item['manifest']).read_text())
        require(manifest['image']['reference'] == item['image'], 'Unchanged manifest image binding differs')
    reports = {}
    attempted = 0
    try:
        for label in FAMILIES:
            attempted += 1
            run_inner(prefix, source, output, label)
            reports[label] = validate_summary(strict_json((output / label / 'verification.json').read_text()), label, output / label)
    finally:
        stops = stopped(prefix, permanent, output, attempted)
    require(backend == runtime.default_backend(prefix, output / 'backend-after') and
        all(images[label] == inspect_image(prefix, output / 'images', label + '-after', item['image']) for label, item in FAMILIES.items()),
        'Actual admitted backend or exact fixed image changed')
    require(sources() == before and fact(shim) == shim_before and fact(Path(__file__)) == own_before and
        all(fact(source / 'fixed' / name)['sha256'] == identity['sha256'] for name, identity in before.items()) and
        all(fact(source / 'original' / FAMILIES[label]['script']) == identity for label, identity in originals.items()),
        'Canonical source, immutable baseline snapshot, helper or shim changed')
    require(reports['deseq2']['inputs'] == reports['limma']['inputs'], 'Both official families must receive the same complete synthetic input bytes')
    write(output / 'verification.json', dict(scope='BOUNDED_FIXED_IMAGES_FULL_R_ENTRIES_PUBLICATION_ONLY_NOT_DAG_OR_DEPLOYMENT',
        sources=before, original_published_revision=BASELINE, images=images, backend=backend,
        reports=reports, actual_full_entries=14, actual_method_containers=2, stopped_intents=len(stops),
        parent_cgroup_before=initial_cgroup, parent_cgroup_after=runtime.cgroup_observation(),
        original_manifest_resources_certified=False, actual_DAG_executed=False, real_research_inputs_read=False,
        production_changed=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
