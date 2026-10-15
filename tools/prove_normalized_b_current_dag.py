"""Replay three immutable normalized-array SYN oracles through current DESIGN/LIMMA DAGs."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import check_ports, digest, write
from tools.prove_bulk_current_chain import plugin_spec

ROOT = Path(__file__).resolve().parents[1]
ORACLE = '186a1ed980cd48f6908f0e7201420f7f'
ORACLE_SEAL = 'efded200ef0755472fda92543d4ce48095799e78828560fa66d54b57968f73cc'
BUILD = 'f7e02ba49c024ceca6b934b4a123f751'
BUILD_SEAL = '431dd1cdf0ea5c2ea66ce98621354b65ebdac356d03d081ee71045b0c81d4caf'
ENGINE = '4ceefbd821baab8deebb070645a2fb8b1fa8e1ba'
EXE = 'bbc1a387b508ba05c50e79eb95b3dc15f87cf274a6e2c3983bcd320246339481'
IMAGE = 'localhost/autonomics/frozen-b-normalized@sha256:723904dd46c9148d75716555e2f641604d98c22909bc333d5fac832f33ebffed'
MODELS = ('primary', 'unadjusted', 'therapy_sensitivity')
NUMERICAL_PREFIXES = {
    'run-design.R': (16694, '5f8300f0078ee45531efb16fd8ecad726ba52a6a24c2824b0f8418979d504d2e'),
    'run-limma.R': (16693, '7723131e15c4aeb64a8b58ee97756028cf191ad3bdcbb85e22ab88da50d3b1cc'),
}
NUMERIC = {'matrix_row', 'family_p', 'raw_p', 'log2_expression_difference', 'standard_error',
           'ci_lower', 'ci_upper', 'moderated_t', 'moderated_df', 'average_expression',
           'n_case', 'n_control', 'q_BH', 'q_BY'}
FROZEN_COLUMNS = {'beta': 'log2_expression_difference', 'moderated_se': 'standard_error',
                  'df': 'moderated_df', 'lo': 'ci_lower', 'hi': 'ci_upper', 'p_raw': 'raw_p',
                  'q_BH': 'q_BH', 'q_BY': 'q_BY'}


def sealed(archives, identity, expected, check_all=True):
    root = archives / identity / 'artifacts'
    if digest(root / 'MANIFEST.json') != expected:
        raise RuntimeError('Immutable reference seal differs')
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*')
              if path.is_file() and path.name != 'MANIFEST.json'}
    if actual != set(manifest['files']):
        raise RuntimeError('Immutable reference membership differs')
    if check_all:
        for name, record in manifest['files'].items():
            path = root / name
            if path.is_symlink() or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
                raise RuntimeError('Immutable reference bytes differ')
    return root, manifest


def job_for(work, source):
    names = ['config.json', 'expression.tsv', 'genes.tsv', 'samples.tsv', 'decisions.tsv']
    nodes = [dict(id='input'+str(index), kind='file_reference',
                  spec=dict(path='vfs:///'+name, format='json' if index == 0 else 'tsv'))
             for index, name in enumerate(names)]
    nodes.extend(dict(id=stage, kind='bulk_normalized_'+stage, spec={}) for stage in ['design', 'limma'])
    edges = [dict(**{'from': 'input'+str(index), 'to': stage}, from_port=0, to_port=index)
             for stage in ['design', 'limma'] for index in range(5)]
    edges.append(dict(**{'from': 'design', 'to': 'limma'}, from_port=0, to_port=5))
    return dict(scope='TECHNICAL_PLUGIN_DAG_NOT_G0', run_root=str(work), **plugin_spec(source),
                bundles=[], panel_manifest_sha256={}, nodes=nodes, edges=edges)


def rows(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t', strict=True)
        header = reader.fieldnames
        result = list(reader)
    if not header or len(header) != len(set(header)) or any(set(row) != set(header) or None in row.values() for row in result):
        raise RuntimeError('Complete unique table header and rectangular rows required')
    return header, result


def number(actual, expected):
    if actual == 'NA' or expected == 'NA':
        if actual != expected:
            raise RuntimeError('Exact missing-value mask differs')
        return 0.0
    observed, target = float(actual), float(expected)
    if not math.isfinite(observed) or not math.isfinite(target) or not math.isclose(observed, target, rel_tol=1e-11, abs_tol=1e-12):
        raise RuntimeError('Unrounded frozen numeric value differs')
    return abs(observed-target)


def compare_tables(actual, baseline, frozen):
    header, observed = rows(actual)
    target_header, expected = rows(baseline)
    _, original = rows(frozen)
    if header != target_header or len(observed) != len(expected) or len(observed) != len(original):
        raise RuntimeError('Complete frozen table shape differs')
    maximum = 0.0
    for current, prior, reference in zip(observed, expected, original, strict=True):
        if current['gene_id'] != reference['gene_id']:
            raise RuntimeError('Frozen gene order differs')
        for key in header:
            if key in NUMERIC:
                maximum = max(maximum, number(current[key], prior[key]))
            elif current[key] != prior[key]:
                raise RuntimeError('Exact table identity/status differs')
        for old, new in FROZEN_COLUMNS.items():
            maximum = max(maximum, number(current[new], reference[old]))
    return dict(rows=len(observed), columns=len(header), frozen_numeric_columns=list(FROZEN_COLUMNS),
                rtol=1e-11, atol=1e-12, max_absolute_error=maximum)


def failed_chain(report, work):
    nodes = {node['id']: node for node in report['first_run']['nodes']}
    published = [path for path in (work / 'artifacts').rglob('*')
                 if path.name in {'audit.json', 'results.tsv', 'official.rds'}]
    if (not report['first_run']['errors'] or nodes['design']['status'] != 'failed'
            or nodes['limma']['status'] != 'skipped' or nodes['limma']['port_assignments']
            or nodes['design']['port_assignments'] or nodes['limma'].get('execution')
            or published):
        raise RuntimeError('Rejected upstream must skip downstream without published outputs')


def check_bindings(node, originals, scratch, sources):
    bindings = node['inputs']
    if len(bindings) != len(originals):
        raise RuntimeError('Actual complete input binding inventory differs')
    workspace = Path(node['port_assignments']['0']['path']).parent
    for index, original in enumerate(originals):
        binding = next(record for record in bindings if record['to_port'] == index)
        staged = list((workspace / '.autonomics/inputs').glob('input-'+str(index)+'.*'))
        if (binding['from'] != sources[index] or binding['from_port'] != 0 or len(staged) != 1
                or staged[0].is_symlink() or not staged[0].resolve().is_relative_to(scratch)
                or binding['fingerprint']['size'] != original.stat().st_size or digest(staged[0]) != digest(original)):
            raise RuntimeError('Actual staged input or port edge differs')
        content = binding['fingerprint'].get('content_hash')
        if content is not None and content.removeprefix('sha256:') != digest(original):
            raise RuntimeError('Actual bound content fingerprint differs')
    return len(bindings)


def private_backend(owner_path, output):
    shim = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    if "'--tmpdir'" not in shim.read_text():
        raise RuntimeError('HOLD: active managed shim lacks qualified private --tmpdir backend')
    owner = json.loads(owner_path.read_text())
    storage = owner_path.parent
    backend = ['--root', str(storage/'storage'), '--runroot', str(storage/'run'),
               '--tmpdir', str(storage/'run/libpod-tmp'), '--storage-driver', 'overlay']
    if owner['runtime_backend'] != backend or not owner['all_three_software_images_exactly_installed']:
        raise RuntimeError('Reviewed existing software-only backend required')
    for key in ['storage', 'runroot']:
        record = owner[key]
        stat = Path(record['path']).stat()
        if (stat.st_dev, stat.st_ino, stat.st_uid, stat.st_gid) != (record['device'], record['inode'], record['uid'], record['gid']):
            raise RuntimeError('Existing private backend identity differs')
    inspected = subprocess.run([str(shim), *backend, 'image', 'inspect', IMAGE], capture_output=True, text=True, check=True, timeout=60)
    (output/'image-inspect.json').write_text(inspected.stdout)
    actual = json.loads(inspected.stdout)[0]
    expected = next(row for row in owner['installed'] if row['label'] == 'B')
    if (expected['reference'] != IMAGE or actual['Digest'] != expected['installed_manifest_sha256']
            or 'sha256:'+actual['Id'].removeprefix('sha256:') != expected['image_config_digest']
            or actual['RootFS']['Layers'] != expected['ordered_diff_ids']):
        raise RuntimeError('Actual cached image/config/layer identity differs')
    proxy = Path(os.environ['TMPDIR'])/'normalized-podman-proxy'
    proxy.mkdir()
    launcher = proxy/'podman'
    launcher.write_text('#!/usr/bin/python3\nimport os,sys\nos.execv('+repr(str(shim))+','+
                        repr([str(shim), *backend])+'+sys.argv[1:])\n')
    launcher.chmod(0o700)
    os.environ['PATH'] = str(proxy)+os.pathsep+os.environ['PATH']
    write(output/'runtime-identity.json', dict(backend=backend, owner_sha256=digest(owner_path),
          managed_shim_sha256=digest(shim), per_session_proxy_sha256=digest(launcher),
          no_image_pull_or_build=True, cpus=1, memory='1Gi', real_study_mounted=False))


def readback(output, records):
    program = output/'readback.R'
    program.write_text('library(jsonlite)\n'
        'stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("limma"))=="3.68.5")\n'
        'jobs<-fromJSON("/work/readback-input.json",simplifyVector=FALSE)\n'
        'fields<-c("coefficients","stdev.unscaled","sigma","df.residual","s2.prior","df.prior","s2.post","df.total","t","p.value","Amean","cov.coefficients")\n'
        'for(job in jobs){actual<-readRDS(job$actual);old<-readRDS(job$reference);'
        'stopifnot(identical(actual$full_gene_ids,old$full_gene_ids),identical(actual$variable_gene_ids,old$variable_gene_ids),'
        'length(actual$full_gene_ids)==25L,length(actual$variable_gene_ids)==24L);'
        'for(field in fields)stopifnot(isTRUE(all.equal(actual$fit[[field]],old$fit[[field]],tolerance=1e-11)));'
        'cat(job$model,"RDS_SELECTED_FIELDS_OK\\n")}\n')
    write(output/'readback-input.json', records)
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
               '--security-opt=no-new-privileges', '--cpus=1', '--memory=1g', '--pids-limit=64',
               '--userns=keep-id', '--user='+str(os.getuid())+':'+str(os.getgid()),
               '--tmpfs=/tmp:rw,size=64m', '-v', str(output)+':/work:ro',
               '--entrypoint=/opt/b-bulk/bin/Rscript-vanilla', IMAGE, '/work/readback.R']
    write(output/'readback-command.json', command)
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (output/'readback.stdout').write_text(result.stdout)
    (output/'readback.stderr').write_text(result.stderr)
    if result.returncode or result.stdout.splitlines() != [model+' RDS_SELECTED_FIELDS_OK' for model in MODELS]:
        raise RuntimeError('Actual container RDS readback failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--runtime-owner', type=Path, required=True)
    arguments = parser.parse_args()
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'normalized-b-current-dag'
    output.mkdir()
    shutil.copyfile(Path(__file__), output/'driver.py')
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
    write(output/'resource-preflight.json', dict(available_bytes=available, required_bytes=3*1024**3,
          free_bytes=shutil.disk_usage(output).free, one_container_only=True, no_production_restart=True))
    if available < 3*1024**3 or shutil.disk_usage(output).free < 2*1024**3:
        raise RuntimeError('HOLD: bounded SYN resource admission unavailable')
    oracle_root, oracle_manifest = sealed(arguments.archives, ORACLE, ORACLE_SEAL)
    oracle = oracle_root/'permanent/normalized-limma-toy'
    build_root, build_manifest = sealed(arguments.archives, BUILD, BUILD_SEAL, check_all=False)
    compiled = build_root/'permanent/current-ldsc-build'
    build = json.loads((compiled/'build-record.json').read_text())
    for filename in ['build-record.json', 'official_plugin_dag']:
        path = compiled/filename
        record = build_manifest['files'][path.relative_to(build_root).as_posix()]
        if path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise RuntimeError('Sealed compiler artifact differs')
    if build['actual_build_exit'] != 0 or build['engine_commit'] != ENGINE or build['executable_sha256'] != EXE:
        raise RuntimeError('Exact sealed successful current runner required')
    runner = Path(os.environ['TMPDIR'])/'official_plugin_dag'
    shutil.copyfile(compiled/'official_plugin_dag', runner)
    runner.chmod(0o700)
    if digest(runner) != EXE:
        raise RuntimeError('Owned executable identity differs')
    shutil.copyfile(compiled/'build-record.json', output/'build-record.json')
    source = output/'source'
    source.mkdir()
    manifest = tomllib.loads((ROOT/'plugins/bulk-limma-normalized/manifest.toml').read_text())
    for name in ['manifest.toml', *{node['command']['script_file'] for node in manifest['nodes']}]:
        destination = source/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'plugins/bulk-limma-normalized'/name, destination)
    for node in manifest['nodes']:
        if manifest['image']['reference'] != IMAGE or node['resources']['cpus'] != 1.0 or node['resources']['memory'] != '1Gi':
            raise RuntimeError('Exact small-SYN manifest resource and image identity required')
    for filename in ['run-design.R', 'run-limma.R']:
        prefix = (source/'scripts'/filename).read_bytes().split(b'entry_main <- function()', 1)[0]
        expected_bytes, expected_hash = NUMERICAL_PREFIXES[filename]
        if len(prefix) != expected_bytes or hashlib.sha256(prefix).hexdigest() != expected_hash:
            raise RuntimeError('Current embedded numerical method differs from immutable independent toy source')
    private_backend(arguments.runtime_owner.resolve(strict=True), output)
    cases = []
    readbacks = []
    for model in [*MODELS, 'upstream-scale-rejected']:
        work = output/model
        work.mkdir()
        base = model if model in MODELS else 'primary'
        originals = [oracle/(base+'-config.json'), *[oracle/name for name in ['expression.tsv','genes.tsv','samples.tsv','decisions.tsv']]]
        inputs = [work/'config.json', *[work/path.name for path in originals[1:]]]
        for original, target in zip(originals, inputs, strict=True):
            shutil.copyfile(original, target)
        if model not in MODELS:
            config = json.loads(inputs[0].read_text())
            config['expression_scale'] = 'raw_integer_counts'
            inputs[0].write_text(json.dumps(config, sort_keys=True, separators=(',', ':')))
        before = [digest(path) for path in inputs]
        job = job_for(work, source)
        write(work/'job.json', job)
        completed = subprocess.run([str(runner), str(work/'job.json')], capture_output=True, text=True, timeout=500)
        (work/'runner.stdout').write_text(completed.stdout)
        (work/'runner.stderr').write_text(completed.stderr)
        report = json.loads((work/'dag-report.json').read_text())
        if (completed.returncode or report['engine_source_revision'] != ENGINE or report['original_manifest_sha256'] != job['plugin_manifest_sha256']
                or report['native_statistical_factories_registered'] is not False or report['g0_granted'] is not False
                or report['input_hashing'] != 'ContentRequired' or report['max_concurrency'] != 1 or report['incremental'] is not False
                or len(report['first_run']['nodes']) != 7 or before != [digest(path) for path in inputs]):
            raise RuntimeError('Actual bounded DAG identity or unchanged inputs differ')
        if model not in MODELS:
            failed_chain(report, work)
            failed_nodes = {node['id']: node for node in report['first_run']['nodes']}
            if (any(failed_nodes['input'+str(index)]['status'] != 'success' for index in range(5))
                    or failed_nodes['design']['execution']['image'] != IMAGE
                    or failed_nodes['design']['execution']['exit_code'] != 2
                    or 'frozen normalized-bulk original source contract required' not in failed_nodes['design']['error']['message']):
                raise RuntimeError('Negative case failed for a reason other than the injected input-scale contract')
            cases.append(dict(case=model, upstream_failed=True, downstream_skipped=True, method_outputs=0))
            continue
        nodes = {node['id']: node for node in report['first_run']['nodes']}
        if report['first_run']['errors'] or any(node['status'] != 'success' for node in nodes.values()):
            raise RuntimeError('Actual normalized DESIGN/LIMMA chain failed')
        scratch = Path(os.environ['TMPDIR'])/'official-plugin-container-workspaces'/model
        ports = {}
        for stage in ['design','limma']:
            definition = next(node for node in manifest['nodes'] if node['kind'] == 'bulk_normalized_'+stage)
            if nodes[stage]['execution']['image'] != IMAGE:
                raise RuntimeError('Actual dispatched image differs')
            ports[stage] = check_ports(work, definition, nodes[stage], scratch)
        bindings = check_bindings(nodes['design'], inputs, scratch, ['input'+str(index) for index in range(5)])
        bindings += check_bindings(nodes['limma'], [*inputs, ports['design'][0]], scratch, [*['input'+str(index) for index in range(5)], 'design'])
        comparison = compare_tables(ports['limma'][0], oracle/(base+'-fit/results.tsv'), oracle/('frozen-numeric-block/FULL_TRANSCRIPTOME_'+base+'.tsv'))
        expected_design = json.loads((oracle/(base+'-design/audit.json')).read_text())
        if json.loads(ports['design'][0].read_text()) != expected_design:
            raise RuntimeError('Complete actual DESIGN receipt differs')
        audit = json.loads(ports['limma'][1].read_text())
        expected_audit = json.loads((oracle/(base+'-fit/audit.json')).read_text())
        hashes = audit.pop('plugin_transport_output_sha256')
        expected_audit.pop('plugin_transport_output_sha256')
        if audit != expected_audit or hashes != dict(results=digest(ports['limma'][0]), rds=digest(ports['limma'][2])):
            raise RuntimeError('Complete method audit or actual output digest differs')
        reference_rds = work/'oracle-official.rds'
        shutil.copyfile(oracle/(base+'-fit/official.rds'), reference_rds)
        readbacks.append(dict(model=model, actual='/work/'+str(ports['limma'][2].relative_to(output)), reference='/work/'+str(reference_rds.relative_to(output))))
        cases.append(dict(case=model, nodes=7, edges=11, actual_input_bindings=bindings,
              actual_output_ports=4, output_hashes={stage:[digest(path) for path in paths] for stage,paths in ports.items()}, comparison=comparison))
        print(model, 'ACTUAL_CURRENT_DAG_PASS', flush=True)
    readback(output, readbacks)
    write(output/'VERIFICATION.json', dict(status='ACCEPTED_SCOPED_SYN_NORMALIZED_DESIGN_LIMMA_DAGS',
          cases=cases, immutable_oracle=dict(session=ORACLE, seal=ORACLE_SEAL, files_rehashed=len(oracle_manifest['files'])),
          engine_commit=ENGINE, executable_sha256=EXE, plugin_identity=plugin_spec(source),
          embedded_numerical_prefixes=NUMERICAL_PREFIXES,
          original_frozen_numerical_block_recomputed=False, official_rds_selected_fields_readback=True,
          RDS_scope='Full gene identities and 12 fitted numerical components, not every object slot or environment',
          family_node_or_real_study_or_resident_daemon_qualified=False,
          container_stoppage_verification_pending_session_reconcile=True, g0_granted=False))


if __name__ == '__main__':
    main()
