"""Bounded public Open Targets source capture, not API/bulk equivalence certification."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


LIMIT = 2 * 1024**2
API_COMMIT = '018afc7b8f439b456045ea1dc3544c70af0d86bd'
DISCOVERY = {
    'api-tree': f'https://api.github.com/repos/opentargets/platform-api/git/trees/{API_COMMIT}?recursive=1',
    'pos-tags': 'https://api.github.com/repos/opentargets/pos/tags?per_page=100',
}
POS_COMMIT = '504fd02f4c4325dfe665d1cef3ffc249acd29238'
OTTER_COMMIT = 'dcb9433cd1d796ca2fc59915f31b7730aa01a3af'
SOURCES = {
    'pos-aotf-schema': f'https://raw.githubusercontent.com/opentargets/pos/{POS_COMMIT}/config/clickhouse/schema/aotf.sql',
    'pos-aotf-load': f'https://raw.githubusercontent.com/opentargets/pos/{POS_COMMIT}/config/clickhouse/scripts/aotf.sql',
    'pos-config': f'https://raw.githubusercontent.com/opentargets/pos/{POS_COMMIT}/config/config.yaml',
    'otter-tree': f'https://api.github.com/repos/opentargets/otter/git/trees/{OTTER_COMMIT}?recursive=1',
}
DISCOVERY_NEXT = {
    'pos-tree': f'https://api.github.com/repos/opentargets/pos/git/trees/{POS_COMMIT}?recursive=1',
    'otter-tags': 'https://api.github.com/repos/opentargets/otter/tags?per_page=100',
    'api-qaotf': f'https://raw.githubusercontent.com/opentargets/platform-api/{API_COMMIT}/app/models/db/QAOTF.scala',
    'api-config': f'https://raw.githubusercontent.com/opentargets/platform-api/{API_COMMIT}/conf/application.conf',
    'api-associations': f'https://raw.githubusercontent.com/opentargets/platform-api/{API_COMMIT}/app/models/entities/Associations.scala',
}
MAPPING = {
    'pos-load-task': f'https://raw.githubusercontent.com/opentargets/pos/{POS_COMMIT}/src/pos/tasks/clickhouse_load.py',
    'api-harmonic': f'https://raw.githubusercontent.com/opentargets/platform-api/{API_COMMIT}/app/models/entities/Harmonic.scala',
    'org-repos': 'https://api.github.com/orgs/opentargets/repos?per_page=100&sort=updated',
}
PIPELINE_DISCOVERY = {
    'pipeline-tags': 'https://api.github.com/repos/opentargets/pipeline/tags?per_page=100',
    'pos-datasets': f'https://raw.githubusercontent.com/opentargets/pos/{POS_COMMIT}/config/datasets.yaml',
    'api-backend': f'https://raw.githubusercontent.com/opentargets/platform-api/{API_COMMIT}/app/models/Backend.scala',
}
PIPELINE_COMMIT = 'ee0eb2f797ec90a25edca2eb5e2deb95614c6b4b'
PIPELINE_TREE = {
    'pipeline-tree': f'https://api.github.com/repos/opentargets/pipeline/git/trees/{PIPELINE_COMMIT}?recursive=1',
}
PIPELINE_FIELDS = {
    'pipeline-association': f'https://raw.githubusercontent.com/opentargets/pipeline/{PIPELINE_COMMIT}/pts/src/pts/pyspark/association.py',
    'pipeline-association-utils': f'https://raw.githubusercontent.com/opentargets/pipeline/{PIPELINE_COMMIT}/pts/src/pts/pyspark/associations_utils/association.py',
    'pipeline-association-otf': f'https://raw.githubusercontent.com/opentargets/pipeline/{PIPELINE_COMMIT}/pts/src/pts/pyspark/association_otf.py',
    'pipeline-config': f'https://raw.githubusercontent.com/opentargets/pipeline/{PIPELINE_COMMIT}/pts/config.yaml',
}
PIPELINE_MATH = {
    'pipeline-dataset': f'https://raw.githubusercontent.com/opentargets/pipeline/{PIPELINE_COMMIT}/pts/src/pts/pyspark/associations_utils/dataset.py',
    'pipeline-evidence': f'https://raw.githubusercontent.com/opentargets/pipeline/{PIPELINE_COMMIT}/pts/src/pts/pyspark/associations_utils/evidence.py',
    'pos-release-ref': 'https://api.github.com/repos/opentargets/pos/git/ref/tags/v26.9.0',
    'pipeline-release-ref': 'https://api.github.com/repos/opentargets/pipeline/git/ref/tags/pts@v26.9.0',
}
RELEASE_REF = {
    'api-release-ref': 'https://api.github.com/repos/opentargets/platform-api/git/ref/tags/v26.9.0',
}
ARCHIVED_PHASES = {
    'initial-discovery-failed': ('4fb1608f7336450caf90f6c751bebe80', '6459fa61cf8019aac60cbb583270106e6438d1c8130b171e9973eff974b9fdac', 1),
    'discovery-next': ('c40691def1e14fa78699fce0018ecddf', 'aaa3131c0f32eedc6066fd7d96ecc2dbdc2d12112520651a4f540227b58ebc4a', 0),
    'sources': ('0c36b4e8a6264abe925b507ed3be7a82', 'b1975118154debaa94302986affdddaae61bc090cbd895eae0846a078cc09b98', 0),
    'mapping': ('c32c2acb4bd54b29972c48aa1e6daa6e', '116e710a8374a6572493d20ab6ad233ed1099800285a1dc9db038383572c9a70', 0),
    'pipeline-discovery': ('a654fead0c844f888ab63773297d1f62', '63478cef9de4ed07e5639c6a03d1f801577f5beb4ad577dbb9300f1482576872', 0),
    'pipeline-tree': ('ec464973d8ed4527a1afb9081e05d3d3', '325980f48f82f7b47645ea7710eb201b6e7a3117b5f9d621128a8e040def7694', 0),
    'pipeline-fields': ('c2a35ddee0fc4d819226087fda7fc445', '3968d81382557e57bfee8ad916095fa713d596fddefc591c5e06d77a0635fd46', 0),
    'pipeline-math': ('b9733f0fd69e4668bfe56a8b7d849cee', '5e467fe3d2c39b8b3a392a6a62563c67932b0590e8838cac151417a0e8637ca8', 0),
    'release-ref': ('c0e5eec7a6214cfeb2b4291f88216e89', '175b8aca784cae94e2af9ff54ce2851b633de626a263fb8cefe1e4a8a619c05e', 0),
}


def default_weights(pipeline, api):
    lines = pipeline.splitlines()
    start = lines.index('        datasource_weights:') + 1
    end = next(index for index in range(start, len(lines)) if lines[index].strip()
        and len(lines[index])-len(lines[index].lstrip()) <= 8)
    pairs = re.findall(r'datasourceId: ([a-z0-9_]+)\n\s+weight: ([0-9.]+)', '\n'.join(lines[start:end]))
    pipeline_weights = {key: float(value) for key, value in pairs}
    overrides = {key: float(value) for key, value in
        re.findall(r'\{id: "([a-z0-9_]+)", weight: ([0-9.]+)', api)}
    if (len(pairs) != len(pipeline_weights) or len(pipeline_weights) != 23 or len(overrides) != 7
            or {key: value for key, value in pipeline_weights.items() if value != 1.0} != overrides):
        raise RuntimeError('Examined default datasource weight table differs')
    return dict(pipeline_weights=pipeline_weights, api_overrides=overrides,
        api_unlisted_fallback=1.0, default_configuration_values_agree=True,
        deployed_configuration_not_verified=True)


def reconcile(archives, output):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import continue_opentargets_direct_reference as archive_guard
    shutil.copyfile(Path(archive_guard.__file__), output / 'archive-verifier.py')
    shutil.copyfile(Path(archive_guard.original.__file__), output / 'archive-verifier-dependency.py')
    sources = {}
    phases = {}
    for phase, (session_id, seal, expected_exit) in ARCHIVED_PHASES.items():
        artifacts, manifest, session = archive_guard.verify_archive(archives, session_id, seal, expected_exit == 0)
        if type(session['worker_exit_status']) is not int or session['worker_exit_status'] != expected_exit:
            raise RuntimeError('Recorded source phase exit differs')
        folder = artifacts / 'permanent/opentargets-field-sources'
        declared = json.loads((folder / 'predeclared.json').read_bytes())['resources']
        phase_sources = []
        for path in sorted(folder.glob('*.source')):
            name = path.name.removesuffix('.source')
            relative = path.relative_to(artifacts).as_posix()
            if name in sources or name not in declared:
                raise RuntimeError('Unexpected or duplicate source identity')
            sources[name] = dict(url=declared[name], session=session_id, manifest_sha256=seal,
                relative_path=relative, **manifest['files'][relative])
            sources[name]['receipt_persisted'] = (folder / (name+'.receipt.json')).exists()
            phase_sources.append(name)
        phases[phase] = dict(session=session_id, manifest_sha256=seal, worker_exit_status=expected_exit,
            state=session['state'], archive_members_rehashed=len(manifest['files']), sources=phase_sources)
    def body(name):
        record = sources[name]
        return (archives / record['session'] / 'artifacts' / record['relative_path']).read_text()
    weights = default_weights(body('pipeline-config'), body('api-config'))
    result = dict(status='OFFICIAL_SOURCE_MAPPING_ESTABLISHED_SCORE_EQUIVALENCE_CONTRADICTED',
        phases=phases, sources=sources, default_weights=weights,
        source_commits=dict(api=API_COMMIT, pos=POS_COMMIT, pipeline=PIPELINE_COMMIT),
        source_text_review=dict(direct_novelty_mapping='currentNovelty -> noveltyDirect -> novelty',
            bulk_harmonic_normalization_terms=1000, bulk_score_vector_cap=50,
            api_otf_harmonic_normalization_terms=100000, api_query_explicit_top50_cap=False,
            semantic_source_review_not_an_automated_proof=True,
            source_snapshots_not_live_deployment_identity=True),
        no_network_requests_during_reconciliation=True, no_scientific_estimator_executed=True,
        numerical_correction_or_tolerance_changed=False, source_or_scientific_release_granted=False,
        g0_granted=False)
    (output / 'reconciliation.json').write_text(json.dumps(result, indent=2)+'\n')
    print('SOURCE_CHAIN_REHASHED DEFAULT_WEIGHTS_AGREE SCORE_ALGORITHMS_DIFFER NO_SCIENTIFIC_RELEASE')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise RuntimeError('Public source redirect forbidden')


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in {'api.github.com', 'raw.githubusercontent.com'}
            or parsed.username or parsed.password or parsed.fragment
            or not parsed.path.startswith(('/repos/opentargets/', '/opentargets/', '/orgs/opentargets/'))):
        raise RuntimeError('Exact public Open Targets source origin required')


def capture(name, url, output):
    validate_url(url)
    time.sleep(2)
    request = Request(url, headers={'Accept-Encoding': 'identity',
        'User-Agent': 'autonomics-source-semantics-technical-audit/1.0'})
    with build_opener(NoRedirect()).open(request, timeout=45) as response:
        if (response.status != 200 or response.url != url
                or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise RuntimeError('Exact public source response required')
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT:
            raise RuntimeError('Public source byte budget exceeded')
        record = dict(url=url, status=response.status, bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(), etag=response.headers.get('ETag'),
            observed_source_only_not_deployed_identity=True)
    with (output / (name + '.source')).open('xb') as handle:
        handle.write(body)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['discovery', 'discovery-next', 'sources', 'mapping', 'pipeline-discovery', 'pipeline-tree', 'pipeline-fields', 'pipeline-math', 'release-ref', 'reconcile'], required=True)
    parser.add_argument('--archives', type=Path)
    arguments = parser.parse_args()
    if not os.environ.get('AUTONOMICS_VALIDATION_PERMANENT'):
        raise RuntimeError('Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'opentargets-field-sources'
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / 'driver.py')
    if arguments.phase == 'reconcile':
        if arguments.archives is None:
            parser.error('--archives required for sealed source reconciliation')
        reconcile(arguments.archives, output)
        return
    selected = {'discovery': DISCOVERY, 'discovery-next': DISCOVERY_NEXT,
        'sources': SOURCES, 'mapping': MAPPING, 'pipeline-discovery': PIPELINE_DISCOVERY,
        'pipeline-tree': PIPELINE_TREE, 'pipeline-fields': PIPELINE_FIELDS,
        'pipeline-math': PIPELINE_MATH, 'release-ref': RELEASE_REF}[arguments.phase]
    if not selected:
        raise RuntimeError('No public source inventory predeclared')
    (output / 'predeclared.json').write_text(json.dumps(dict(phase=arguments.phase,
        resources=selected, per_file_limit=LIMIT, no_scientific_data=True,
        deployed_service_commit_asserted=False, bulk_api_semantic_equivalence_granted=False,
        g0_granted=False), indent=2) + '\n')
    records = {}
    for name, url in selected.items():
        try:
            records[name] = capture(name, url, output)
        except Exception as error:
            (output / 'failed-resource.json').write_text(json.dumps(dict(name=name, url=url,
                exception_type=type(error).__name__, successful_phase=False, retries=0), indent=2)+'\n')
            raise
        (output / (name + '.receipt.json')).write_text(json.dumps(records[name], indent=2)+'\n')
    (output / 'verification.json').write_text(json.dumps(dict(resources=records,
        status='PUBLIC_SOURCE_BYTES_CAPTURED_NOT_SEMANTIC_EQUIVALENCE', g0_granted=False), indent=2) + '\n')
    print('PUBLIC_SOURCE_FILES_CAPTURED', len(records), 'SEMANTIC_EQUIVALENCE_NOT_GRANTED')


if __name__ == '__main__':
    main()
