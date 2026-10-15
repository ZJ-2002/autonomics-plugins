"""Bounded official-runtime regression for two publication-only repairs, not DAG admission."""

import base64
import ast
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import prove_h5ad_subset_official_runtime as subset
from tools.prove_frozen_a_family_runtime import stopped

BASELINE = 'd91be9dad535e79c97fb3566b07fe1f68d0954ba'
PB_IMAGE = 'ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5'
PINNED = {
    'plugins/pseudobulk/manifest.toml': '2c1a5d0105617aabed47b3950dfa751a94e3b47dfa7d98a805f9c5d1a66033c8',
    'plugins/pseudobulk/scripts/pseudobulk_counts.py': 'd1bb920dbd2c7a938638724432f38a8f56fd8ecd6b8aeb5d9b6e221ed04be109',
    'plugins/pseudobulk/tests/test_assurance.py': '885cea12225f2468b57216487fd37f14aacf780bbb64dfac5101b232aef8ad25',
    'plugins/single-cell/manifest.toml': '5288e9c7ac552f318b93c67f107fd45dcddf12d9396c38e00e6950e3bede9c42',
    'plugins/single-cell/scripts/score_genes.py': 'dc2815e79b289327ef4ef3c15bf744c1e1557063692b9989c77b2002bf47f774',
    'plugins/single-cell/tests/test_score_genes_container.py': '36fd415ea047213c022c0c4fe781e7b70295255277162afda903debbe6ccb78c',
    'tools/check_pseudobulk_publication_runtime.py': 'c46cc1956d6932f61dd61689cbb93a44753f1ab4d40c9e4e7b9f2b864c2d109c',
    'tools/check_score_genes_publication_runtime.py': '2544aa5f26c5bd00bd3891d33ee55ec131d5065bfb96b9cddb2cad4c10edb4d9',
    'tools/prove_h5ad_subset_official_runtime.py': '3176113e657a9d122c1435545b026eaac9eaeaab13883e70aa70912c73c7d0c7',
    'tools/prove_frozen_a_family_runtime.py': '9939f90020c5d3bf2c92d69ec69433581fe41f47074bbe757a252dd49f8ecd3f',
}
ORIGINAL = {
    'plugins/pseudobulk/scripts/pseudobulk_counts.py': '77884036871586b1be564a8c25f9ab72b2939a987db112aecd328cc86e44c83d',
    'plugins/single-cell/scripts/score_genes.py': '9cad19728810b8e9c9933fed33f556870419a985a12f1485ce61d4f4da8c58e8',
}
THREAD_VARIABLES = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
    'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS')
SCORE_EXPECTED = dict(schema='SCORING_PUBLICATION_OFFICIAL_RUNTIME_V1',
    status='SCOPED_OFFICIAL_SCORING_AND_PUBLICATION_DIRECT_RUNTIME_PROVEN',
    actual_scientific_suite_cases=14, actual_original_defect_reproductions=3,
    actual_fixed_path_refusals=3, actual_DAG_executed=False, official_scores_not_UCell_or_singscore=True,
    real_research_inputs_used=False, production_deployed=False,
    scientific_authorization_granted=False, g0_granted=False,
    container_stoppage='OUTER_MANAGED_RUNNER_MUST_RECONCILE')
require = subset.require
write = subset.write
strict_json = subset.strict_json
fact = subset.fact


def source_facts():
    require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) for value in PINNED.values()),
        'Final source identities are not frozen; no runtime execution permitted')
    facts = {name: fact(ROOT / name) for name in PINNED}
    require(all(facts[name]['sha256'] == expected for name, expected in PINNED.items()),
        'Reviewed publication source or inherited runtime helper differs')
    return facts


def inspect_pseudobulk(prefix, output, label):
    command = [*prefix, 'image', 'inspect', PB_IMAGE]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output / (label + '-inspect.stdout.json')).write_text(result.stdout)
    (output / (label + '-inspect.stderr')).write_text(result.stderr)
    require(type(result.returncode) is int and result.returncode == 0,
        'Installed immutable pseudobulk image unavailable; no pull or alternate runtime allowed')
    records = strict_json(result.stdout)
    require(isinstance(records, list) and len(records) == 1, 'One actual pseudobulk image required')
    observed = records[0]
    config_sha = observed['Id'].removeprefix('sha256:')
    requested_sha = PB_IMAGE.split('@sha256:', 1)[1]
    require(re.fullmatch('[0-9a-f]{64}', config_sha), 'Actual image configuration identity required')
    store = Path.home() / '.local/share/containers/storage/overlay-images' / config_sha
    encoded = lambda name: '=' + base64.b64encode(name.encode()).decode()
    manifest_path = store / encoded('manifest-sha256:' + requested_sha)
    config_path = store / encoded('sha256:' + config_sha)
    manifest_bytes = manifest_path.read_bytes()
    config_bytes = config_path.read_bytes()
    require(hashlib.sha256(manifest_bytes).hexdigest() == requested_sha and
        hashlib.sha256(config_bytes).hexdigest() == config_sha and
        fact(manifest_path)['sha256'] == requested_sha and fact(config_path)['sha256'] == config_sha,
        'Read actual immutable manifest/configuration bytes before parsing')
    manifest = strict_json(manifest_bytes)
    configuration = strict_json(config_bytes)
    require(manifest['config']['digest'] == 'sha256:' + config_sha and
        configuration['architecture'] == 'amd64' and configuration['os'] == 'linux' and
        observed['RootFS']['Layers'] == configuration['rootfs']['diff_ids'],
        'Actual requested manifest must bind the installed image/configuration/ordered layers')
    primary = observed['Digest'].removeprefix('sha256:')
    require(re.fullmatch('[0-9a-f]{64}', primary), 'Actual primary manifest digest required')
    if primary != requested_sha:
        alternate_path = store / encoded('manifest-sha256:' + primary)
        alternate_bytes = alternate_path.read_bytes()
        require(hashlib.sha256(alternate_bytes).hexdigest() == primary and
            fact(alternate_path)['sha256'] == primary and
            strict_json(alternate_bytes)['config']['digest'] == 'sha256:' + config_sha,
            'Alternate cached manifest must cryptographically bind the same installed configuration')
        (output / (label + '-alternate-manifest.json')).write_bytes(alternate_bytes)
    (output / (label + '-requested-manifest.json')).write_bytes(manifest_bytes)
    (output / (label + '-image-configuration.json')).write_bytes(config_bytes)
    return dict(requested_reference=PB_IMAGE, requested_manifest_sha256=requested_sha,
        config_sha256=config_sha, installed_primary_manifest_digest=observed['Digest'],
        ordered_diff_ids=configuration['rootfs']['diff_ids'], default_backend=True,
        private_AB_backend_used=False, image_name_alone_not_identity=True)


def snapshot_sources(output, before):
    source = output / 'source'
    source.mkdir(mode=0o700)
    for name in PINNED:
        destination = source / 'fixed' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        require(fact(destination)['sha256'] == before[name]['sha256'], 'Small reviewed source snapshot differs')
    originals = {}
    for name, expected in ORIGINAL.items():
        payload = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + name])
        require(hashlib.sha256(payload).hexdigest() == expected, 'Exact published original script required')
        destination = source / 'original' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as handle:
            handle.write(payload)
        originals[name] = fact(destination)
    return source, originals


def run_inner(prefix, source, output, label, image, arguments):
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
        '--pids-limit=128', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=128m', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'TMPDIR=/tmp']
    for name in THREAD_VARIABLES:
        command.extend(['-e', name + '=1'])
    command.extend(['-v', str(source) + ':/source:ro', '-v', str(output) + ':/proof:rw',
        '--entrypoint=python3', image, *arguments])
    write(output / (label + '-command.json'), command)
    result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
    (output / (label + '.stdout')).write_text(result.stdout)
    (output / (label + '.stderr')).write_text(result.stderr)
    write(output / (label + '-execution.json'), dict(actual_exit=result.returncode, image=image,
        container_cpus=1, container_memory_bytes=1024**3, parent_memory_max_bytes=2 * 1024**3,
        no_build=True, no_pull=True, no_network=True, actual_DAG_executed=False,
        scientific_authorization_granted=False, g0_granted=False))
    require(type(result.returncode) is int and result.returncode == 0,
        'Actual bounded official-runtime regression failed: ' + label)


def literal_constants(path, names):
    result = {}
    for node in ast.parse(path.read_bytes()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in names:
                require(name not in result, 'Unique frozen case constants required')
                result[name] = ast.literal_eval(node.value)
    require(set(result) == set(names), 'All frozen literal case inventories required')
    return result


def check_pseudobulk_summary(value, directory):
    require(value.get('status') == 'ALL_41_CASES_PER_SOURCE_COMPLETED_20_COMPLETE_OUTPUT_PAIRS_EQUAL' and
        type(value.get('actual_child_processes')) is int and value['actual_child_processes'] == 82 and
        value.get('positive_cases_per_source') == 20 and value.get('specific_negative_cases_per_source') == 21 and
        all(value.get(name) is True for name in ['all_original_synthetic_arithmetic_checks_passed',
            'full_positive_counts_and_quoted_metadata_byte_equal',
            'all_41_actual_exits_and_specific_refusals_agree']),
        'All original pseudobulk cases and complete output comparisons must really execute')
    constants = literal_constants(ROOT / 'tools/check_pseudobulk_publication_runtime.py',
        ['POSITIVE_CASES', 'NEGATIVE_CASES'])
    positives, negatives = constants['POSITIVE_CASES'], constants['NEGATIVE_CASES']
    require(len(positives) == len(set(positives)) == 20 and len(negatives) == 21 and
        len(set(positives) | set(negatives)) == 41, 'Exact full technical case inventory required')
    inventories = []
    for name in ['actual_cases_original', 'actual_cases_fixed']:
        rows = value.get(name)
        require(isinstance(rows, list) and [row.get('case') for row in rows] == [*positives, *negatives],
            'Every original/fixed actual case must appear once in frozen order')
        for row in rows:
            require(type(row.get('actual_exit')) is int, 'Actual case exit must be an integer')
            if row['case'] in negatives:
                expected = 1 if row['case'] == 'ordinary-second-publish-failure' else 2
                require(row['actual_exit'] == expected and type(row.get('expected_exit')) is int and
                    row['expected_exit'] == expected and row.get('actual_diagnostic_matched') is True and
                    row.get('expected_diagnostic') == negatives[row['case']],
                    'Infrastructure failure cannot replace a specific expected original refusal')
            else:
                require(row['actual_exit'] == 0 and row.get('independent_reference_checked') is True,
                    'Every complete original arithmetic assertion must actually pass')
        inventories.append(rows)
    require(inventories[0] == inventories[1], 'All original/fixed exits and refusal diagnostics must agree')
    comparisons = value.get('complete_positive_output_comparisons')
    require(isinstance(comparisons, list) and [row.get('case') for row in comparisons] == list(positives),
        'Every original positive case needs complete paired output proof')
    for row in comparisons:
        products = row.get('products')
        require(isinstance(products, list) and [product.get('name') for product in products] == ['counts.tsv', 'samples.tsv'] and
            row.get('complete_logs_equal_except_exact_input_path') is True,
            'Both complete quoted tables and normalized complete log must be compared')
        for product in products:
            old = directory / 'original/cases' / row['case'] / product['name']
            current = directory / 'fixed/cases' / row['case'] / product['name']
            old_fact, current_fact = fact(old), fact(current)
            require(old_fact['sha256'] == current_fact['sha256'] == product.get('sha256') and
                type(product.get('bytes')) is int and old_fact['bytes'] == current_fact['bytes'] == product['bytes'] and
                product.get('complete_quoted_lexical_bytes_equal') is True and
                all(type(product.get(name)) is int and product[name] > 0 for name in ['rows', 'columns']),
                'Actual full positive tables must match their paired whole-byte evidence')
    require(all(value.get(name) is False for name in ['real_scientific_data_read', 'full_scale_resources_certified',
        'donor_eligibility_granted', 'isolated_DAG_executed', 'resident_method_execution_proven',
        'scientific_authorization_granted', 'g0_granted']), 'Runtime regression cannot grant research authority')
    return value


def check_score_summary(value, directory):
    require(isinstance(SCORE_EXPECTED, dict) and SCORE_EXPECTED,
        'Final score_genes official-runtime summary contract is not frozen')
    require(all(type(value.get(name)) is type(expected) and value[name] == expected
        for name, expected in SCORE_EXPECTED.items()), 'Full original scoring suite/runtime contract differs')
    require(value.get('source_sha256') == dict(
        original_script=ORIGINAL['plugins/single-cell/scripts/score_genes.py'],
        fixed_script=PINNED['plugins/single-cell/scripts/score_genes.py'],
        suite_source=PINNED['plugins/single-cell/tests/test_score_genes_container.py']),
        'Scoring execution must use the exact old/fixed/original-suite sources')
    require(value.get('packages') == dict(scanpy='1.11.3', anndata='0.11.4', numpy='2.1.3',
        scipy='1.14.1', pandas='2.2.3', h5py='3.16.0'), 'Exact frozen scoring package versions required')
    constants = literal_constants(ROOT / 'tools/check_score_genes_publication_runtime.py',
        ['SCIENTIFIC_CASES', 'PUBLICATION_CASES'])
    required_cases = constants['SCIENTIFIC_CASES']
    suites = value.get('scientific_suites')
    require(isinstance(suites, dict) and set(suites) == {'original', 'fixed'} and len(required_cases) == 7,
        'Both complete unchanged seven-case official scoring suites required')
    for label in ['original', 'fixed']:
        suite = suites[label]
        rows = suite.get('actual_cases')
        require(type(suite.get('tests_run')) is int and suite['tests_run'] == 7 and
            isinstance(rows, list) and len(rows) == 7 and
            {row.get('test_id', '').rsplit('.', 1)[-1] for row in rows} == required_cases and
            all(row.get('status') == 'SUCCESS' for row in rows) and
            all(suite.get(name) == [] for name in ['failures', 'errors', 'skipped']) and
            suite.get('original_suite_unchanged') is True and
            suite.get('fixture_scope') == 'SYNTHETIC_METHOD_TEST_NOT_RESEARCH',
            'No missing, skipped or failed original scientific case may pass runtime regression')
        require(strict_json((directory / ('official-suite-' + label) / 'verification.json').read_text()) == suite,
            'Actual original-suite evidence differs from the final summary')
    cases = value.get('publication_cases')
    expected = [(label, case) for label in ['original', 'fixed'] for case in constants['PUBLICATION_CASES']]
    require(isinstance(cases, list) and [(row.get('implementation'), row.get('case')) for row in cases] == expected and
        len(expected) == 6, 'All three original defects and three repaired refusals must execute')
    for row in cases:
        original = row['implementation'] == 'original'
        expected_exit = 2 if not original or row['case'] == 'missing-report-parent' else 0
        require(type(row.get('actual_exit')) is int and row['actual_exit'] == expected_exit and
            row.get('baseline_defect_reproduced') is original and row.get('fixed_refusal_proven') is (not original) and
            row.get('scientific_authorization_granted') is False and
            all(isinstance(row.get(name), str) and re.fullmatch('[0-9a-f]{64}', row[name])
                for name in ['input_before_sha256', 'input_after_sha256']) and
            (row['input_before_sha256'] != row['input_after_sha256'] if original and row['case'] == 'input-alias'
                else row['input_before_sha256'] == row['input_after_sha256']),
            'Actual scoring publication refusal cannot be substituted with OOM or an unrelated error')
        case_directory = directory / (row['implementation'] + '-' + row['case'])
        require(strict_json((case_directory / 'verification.json').read_text()) == row,
            'Actual scoring publication case evidence differs from its summary')
    compatibility = value.get('descriptor_h5ad_compatibility')
    require(isinstance(compatibility, dict) and
        all(compatibility.get(name) is True for name in ['actual_official_AnnData_write_h5ad_and_readback',
            'owned_inode_preserved', 'full_X_and_axes_equal']) and
        type(compatibility.get('rows')) is int and compatibility['rows'] == 12 and
        type(compatibility.get('columns')) is int and compatibility['columns'] == 100,
        'Real AnnData descriptor compatibility must include full matrix and axis readback')
    files = list((directory / 'descriptor-h5ad-readback').glob('owned-*.h5ad'))
    require(len(files) == 1 and fact(files[0])['bytes'] == compatibility.get('h5ad_bytes') and
        fact(files[0])['sha256'] == compatibility.get('h5ad_sha256'),
        'Complete descriptor-written H5AD must remain available and hashed')
    return value


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'),
        'Managed light session required')
    before = source_facts()
    require(SCORE_EXPECTED is not None, 'Final inner scoring evidence contract required before execution')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'b-publication-runtime'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    initial_cgroup = subset.cgroup_observation()
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:'))) * 1024
    require(available >= 4 * 1024**3 and shutil.disk_usage(output).free >= 1024**3,
        'Two serial tiny official-runtime fixtures plus system reserve are unavailable')
    write(output / 'resource-admission.json', dict(parent=initial_cgroup, available_memory_bytes=available,
        container_cpus=1, container_memory_max_bytes=1024**3, parent_memory_max_bytes=2 * 1024**3,
        competing_builds_not_stopped=True, no_build=True))
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    shim_before = fact(shim)
    prefix = [str(shim), '--cgroup-manager=cgroupfs']
    for name in ['backend-before', 'backend-after', 'images']:
        (output / name).mkdir()
    backend_before = subset.default_backend(prefix, output / 'backend-before')
    pseudobulk_before = inspect_pseudobulk(prefix, output / 'images', 'pseudobulk-before')
    score_before = subset.inspect(prefix, output / 'images', 'score-before')
    source, originals = snapshot_sources(output, before)
    manifests = {name: tomllib.loads((source / 'fixed' / name).read_text())
        for name in ['plugins/pseudobulk/manifest.toml', 'plugins/single-cell/manifest.toml']}
    require(manifests['plugins/pseudobulk/manifest.toml']['image']['reference'] == PB_IMAGE and
        manifests['plugins/single-cell/manifest.toml']['image']['reference'] == subset.IMAGE,
        'Actual immutable runtime must equal each unchanged family manifest')
    run_inner(prefix, source, output, 'pseudobulk', PB_IMAGE,
        ['/source/fixed/tools/check_pseudobulk_publication_runtime.py',
         '--original-script', '/source/original/plugins/pseudobulk/scripts/pseudobulk_counts.py',
         '--fixed-script', '/source/fixed/plugins/pseudobulk/scripts/pseudobulk_counts.py',
         '--assurance-source', '/source/fixed/plugins/pseudobulk/tests/test_assurance.py',
         '--output', '/proof/pseudobulk'])
    pseudobulk = check_pseudobulk_summary(strict_json((output / 'pseudobulk/verification.json').read_text()),
        output / 'pseudobulk')
    run_inner(prefix, source, output, 'score', subset.IMAGE,
        ['/source/fixed/tools/check_score_genes_publication_runtime.py',
         '--original-script', '/source/original/plugins/single-cell/scripts/score_genes.py',
         '--fixed-script', '/source/fixed/plugins/single-cell/scripts/score_genes.py',
         '--suite-source', '/source/fixed/plugins/single-cell/tests/test_score_genes_container.py',
         '--output', '/proof/score'])
    scoring = check_score_summary(strict_json((output / 'score/SUMMARY.json').read_text()), output / 'score')
    require(backend_before == subset.default_backend(prefix, output / 'backend-after') and
        pseudobulk_before == inspect_pseudobulk(prefix, output / 'images', 'pseudobulk-after') and
        score_before == subset.inspect(prefix, output / 'images', 'score-after'),
        'Default backend or installed immutable runtime identity changed')
    stops = stopped(prefix, permanent, output, 2)
    require(fact(shim) == shim_before and source_facts() == before and
        all(fact(source / 'fixed' / name)['sha256'] == expected for name, expected in PINNED.items()) and
        all(fact(source / 'original' / name) == identity for name, identity in originals.items()),
        'Original managed shim, canonical source, source snapshot or frozen original changed')
    final_cgroup = subset.cgroup_observation()
    write(output / 'verification.json', dict(
        scope='BOUNDED_DIRECT_TWO_PUBLICATION_REPAIRS_OFFICIAL_RUNTIME_NOT_DAG_OR_DEPLOYMENT',
        sources=before, original_published_revision=BASELINE, original_script_sha256=ORIGINAL,
        runtime_backend=backend_before, pseudobulk_image=pseudobulk_before, score_image=score_before,
        original_managed_shim=shim_before, initial_parent_cgroup=initial_cgroup,
        final_parent_cgroup=final_cgroup, pseudobulk=pseudobulk, score_genes=scoring,
        actual_method_containers=2, owned_container_intents_verified=len(stops), containers_remaining=0,
        container_memory_bytes=1024**3, parent_memory_max_bytes=2 * 1024**3,
        official_runtime_reused_no_new_installation=True, source_only_small_technical_snapshots=True,
        research_raw_data_read=False, original_manifest_resources_certified=False,
        full_size_or_all_inputs_certified=False, actual_DAG_executed=False, current_daemon_verified=False,
        production_restarted=False, scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
