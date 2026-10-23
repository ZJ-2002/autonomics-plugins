"""Render request-specific fixed File ports; never registers or runs a plugin."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('real_dag_bridge', HERE / 'scripts/bridge.py')
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def prepare(request, study, adapters, output):
    lock_payload = bridge.read(HERE / 'source-lock.json')
    lock = bridge.decode(lock_payload)
    contract = bridge.plan(request, study, adapters, lock)
    bridge.require(output.is_absolute() and output.parent.resolve(strict=True) == output.parent and
        not output.exists() and not output.is_symlink(), 'New canonical candidate directory required')
    output.mkdir(mode=0o700)
    assembly, official = output / 'assembly', output / 'official'
    assembly.mkdir()
    official.mkdir()
    (output / 'file-closure.json').write_bytes(bridge.encode(contract))
    # Fixed ports are generated per closure because SDK v1 exposes only File.
    entries = [dict(role='closure', original_path=str(output / 'file-closure.json'))] + contract['entries']
    ports = ', '.join('{type="file",label=' + json.dumps(e['role']) + '}' for e in entries)
    manifest = (HERE / 'manifest.template.toml').read_text().replace(
        'inputs = [] # GENERATED_EXACT_FILE_INPUTS', 'inputs = [' + ports + ']')
    manifest += '\n[nodes.command.files]\n"source-lock.json" = ' + json.dumps(lock_payload.decode()) + '\n'
    (assembly / 'manifest.toml').write_text(manifest)
    (assembly / 'bridge.py').write_bytes(bridge.read(HERE / 'scripts/bridge.py'))
    (official / 'manifest.toml').write_bytes(bridge.read(HERE / 'official-manifest.toml'))
    (official / 'adjust.sh').write_bytes(bridge.read(HERE / 'scripts/adjust.sh'))
    nodes = [dict(id='input' + str(i), kind='file_reference', spec=dict(path=e['original_path'],
        format='file', hash_content=True)) for i, e in enumerate(entries)]
    nodes.extend([dict(id='assemble', kind='frozen_a_real_intake_assemble_v1', spec={}),
        dict(id='official', kind='frozen_a_real_intake_adjust_v1', spec={})])
    edges = [dict(from_node='input' + str(i), from_port=0, to='assemble', to_port=i)
        for i in range(len(entries))]
    edges.extend([dict(from_node='assemble', from_port=1, to='official', to_port=0),
        dict(from_node='assemble', from_port=2, to='official', to_port=1),
        dict(from_node='input9', from_port=0, to='official', to_port=2),
        dict(from_node='input16', from_port=0, to='official', to_port=3)])
    edges = [{'from': e.pop('from_node'), **e} for e in edges]
    candidate = dict(schema='A_REAL_INTAKE_DAG_CANDIDATE_V1', scope='TECHNICAL_TRANSPORT_NOT_SCIENTIFIC',
        nodes=nodes, edges=edges, closure_sha256=bridge.sha((output / 'file-closure.json').read_bytes()),
        plugins=[dict(path=str(p / 'manifest.toml'), sha256=bridge.sha((p / 'manifest.toml').read_bytes()))
            for p in [assembly, official]],
        official_stage_executed=False, resident_deployment_granted=False,
        scientific_authorization_granted=False, g0_granted=False)
    (output / 'dag-candidate.json').write_bytes(bridge.encode(candidate))
    # Native dag_core::dag::history::DagManifest shape. Default logical and
    # physical metadata are supplied by serde; runtime admission is separate.
    (output / 'native-dag-manifest.json').write_bytes(bridge.encode(dict(schema_version=1, nodes=nodes, edges=edges)))
    return contract, candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--study-root', type=Path, required=True)
    parser.add_argument('--adapters-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.request, args.study_root, args.adapters_root, args.output)


if __name__ == '__main__':
    main()
