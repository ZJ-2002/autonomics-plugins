"""Generate a TUI dag_shell request for the current frozen B LEGACY primary model.

Only constructs source references and edges; never reads project payloads or runs a DAG.
"""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'plugins/frozen-b-project/project-lock.json').read_text())
INPUTS = ['config', 'manifest', 'samples', 'features', 'scope', 'design_certificate',
          'software_lock', 'r_dependencies', 'r_session', 'scientific_code',
          'scientific_rules', 'scope_decision', 'matrix', 'source_metadata',
          'g0_certificate', 'family_lock', 'restore_acceptance', 'runtime_manifest', 'byte_verifier']


def build(project_uri, prefix='frozen_b'):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,60}', prefix):
        raise ValueError('safe distinct DAG node prefix required')
    if (not project_uri.startswith('vfs://') or '\\' in project_uri or
            any(p in ['', '.', '..'] for p in project_uri[6:].rstrip('/').split('/')) or
            any(ord(c) < 32 for c in project_uri)):
        raise ValueError('an existing mounted project vfs:// URI is required')
    base = project_uri.rstrip('/')
    lines = []
    for name in INPUTS:
        spec = '#{path: ' + json.dumps(base + '/' + LOCK['files'][name]['relative_path']) + ', hash_content: true}'
        lines.append('node(' + json.dumps(prefix + '_' + name) + ', "core/file_reference", ' + spec + ');')
    kinds = {'intake': 'frozen-b-project/frozen_b_legacy_intake',
             'design': 'bulk-limma-normalized/bulk_normalized_design',
             'limma': 'bulk-limma-normalized/bulk_normalized_limma',
             'family': 'frozen-b-project/frozen_b_legacy_family'}
    for name, kind in kinds.items():
        lines.append('node(' + json.dumps(prefix + '_' + name) + ', ' + json.dumps(kind) + ', #{});')
    def edge(source, output, target, port):
        lines.append('edge(' + json.dumps(prefix + '_' + source) + ', ' + str(output) + ', ' +
                     json.dumps(prefix + '_' + target) + ', ' + str(port) + ');')
    for i, name in enumerate(INPUTS):
        edge(name, 0, 'intake', i)
    for name in ['design', 'limma']:
        for i in range(5):
            edge('intake', i, name, i)
    edge('design', 0, 'limma', 5)
    for source, output, port in [('limma', 0, 0), ('intake', 2, 1), ('intake', 5, 2), ('limma', 1, 3)]:
        edge(source, output, 'family', port)
    lines.append('commit();')
    return {'script': '\n'.join(lines) + '\n', 'dry_run': True, 'timeout_ms': 5000}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-uri', required=True)
    parser.add_argument('--prefix', default='frozen_b')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(build(args.project_uri, args.prefix), stream, indent=2)
        stream.write('\n')
