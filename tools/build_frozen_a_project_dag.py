"""Generate the fixed v4.3.2 A legacy exploratory TUI dag_shell request.

Only constructs hash-enabled file references and graph edges. It does not read
study payloads, install mounts, commit a graph, or execute the 39-SNP analysis.
"""
import argparse
import json
from pathlib import Path
import re

PROJECT_URI = 'vfs://research/versions/v4.3.2/bm_cachexia_v432_g0'
AUDIT_URI = PROJECT_URI + '/03_AUDIT/G0_v4.3.2_2026-10-11'
PROOF_URI = 'vfs://plugins/active/twosamplemr-v432-a/contracts/frozen-method-proof.json'
METHOD_KIND = 'twosamplemr-v432-a/twosamplemr_v432_a_exploratory'
INPUTS = [
    ('qualified', AUDIT_URI + '/A_FROZEN_EXPLORATORY_INPUT.tsv'),
    ('config', AUDIT_URI + '/A_ANALYSIS_CONFIG.json'),
    ('certificate', AUDIT_URI + '/G0_V432_CERTIFICATE.json'),
    ('r_dependencies', AUDIT_URI + '/R_DEPENDENCY_LOCK.tsv'),
    ('method_proof', PROOF_URI),
]


def build(prefix='frozen_a'):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,60}', prefix):
        raise ValueError('safe distinct DAG node prefix required')
    lines = []
    for name, uri in INPUTS:
        spec = '#{path: ' + json.dumps(uri) + ', hash_content: true}'
        lines.append('node(' + json.dumps(prefix + '_' + name) + ', "core/file_reference", ' + spec + ');')
    lines.append('node(' + json.dumps(prefix + '_mr') + ', ' + json.dumps(METHOD_KIND) + ', #{});')
    for port, (name, _) in enumerate(INPUTS):
        lines.append('edge(' + json.dumps(prefix + '_' + name) + ', 0, ' +
                     json.dumps(prefix + '_mr') + ', ' + str(port) + ');')
    lines.append('commit();')
    return {'script': '\n'.join(lines) + '\n', 'dry_run': True, 'timeout_ms': 5000}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default='frozen_a')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    request = build(args.prefix)
    with args.output.open('x') as stream:
        json.dump(request, stream, indent=2)
        stream.write('\n')
