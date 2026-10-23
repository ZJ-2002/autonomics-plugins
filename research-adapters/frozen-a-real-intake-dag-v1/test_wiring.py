"""Only new File wiring; reuse prior sealed numerical proof without running R."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('prepare_candidate', HERE / 'prepare.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)
bridge = prepare.bridge
BASELINE = Path('/home/zj-normal/.local/state/autonomics/validation-archives/3fddecd8263d4166888d41f582b35dca/artifacts/permanent/a-real-input-v1-toy')
STUDY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0')


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='a-dag-wire-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = self.root / 'originals'
        self.original.mkdir()
        source = self.original / 'results.tsv'
        source.write_bytes((BASELINE / 'toy-results.tsv').read_bytes())
        rds = self.original / 'original.RDS'
        rds.write_bytes((BASELINE / 'toy-original.RDS').read_bytes())
        history = self.original / 'history.tsv'
        ids = ['A_X01_M06', 'A_X01_M01', 'A_X01_M02']
        history.write_text('analysis_id\tfirst_result_viewed_at\tstatus\tallowed_identity\n' + ''.join(
            identifier + '\tON_OR_BEFORE_2026-01-01_EXACT_FIRST_VIEW_UNKNOWN\tLEGACY_PIPELINE_ANALYZED\tLEGACY_EXPLORATORY_TECHNICAL_REANALYSIS\n'
            for identifier in ids))
        request = json.loads((BASELINE / 'toy-request.json').read_bytes())
        request['sources'][0]['path'] = str(source)
        for edge in request['edges']:
            if edge['rds']:
                edge['rds']['path'] = str(rds)
        request['seen_history'] = [dict(source_id='synthetic-toy', sha256=bridge.sha(source.read_bytes()),
            declaration='ALREADY_SEEN_NOT_INDEPENDENT', precision='ON_OR_BEFORE_DATE',
            upper_bound_date='2026-01-01', exact_first_view_known=False,
            history_file=dict(path=str(history), sha256=bridge.sha(history.read_bytes())), analysis_ids=ids)]
        request_path = self.original / 'request.json'
        request_path.write_bytes(bridge.encode(request))
        self.lock = json.loads((HERE / 'source-lock.json').read_bytes())
        self.contract, self.candidate = prepare.prepare(request_path, STUDY, HERE.parent, self.root / 'candidate')
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        self.inputs = []
        for i, source in enumerate([self.root / 'candidate/file-closure.json'] +
                [Path(row['original_path']) for row in self.contract['entries']]):
            target = self.stage / (str(i) + '.input')
            shutil.copyfile(source, target)
            target.chmod(0o444)
            self.inputs.append(target)
        self.outputs = [self.root / n for n in ['real-family.tsv', 'real-vectors.tsv', 'real-assembly.json', 'file-transport.json']]

    def test_01_materialized_closure_preserves_complete_payloads_without_host_paths(self):
        # Original request/source/history/RDS locations cease to exist. No host
        # fallback can satisfy this case; every byte must come from a File port.
        self.original.rename(self.root / 'host-paths-unavailable')
        transport = bridge.run_assembly(self.inputs, self.outputs, self.root / 'materialized', self.lock)
        for index, name in enumerate(['real-family.tsv', 'real-vectors.tsv']):
            self.assertEqual(self.outputs[index].read_bytes(), (BASELINE / 'chain' / name).read_bytes())
        receipt = json.loads(self.outputs[2].read_bytes())
        self.assertEqual([receipt['assembly_rows'], receipt['vector_rows'], receipt['vector_count']], [564, 840, 6])
        self.assertEqual(receipt['decision_state_counts'], dict(PENDING=275, O2=1))
        self.assertEqual(len(receipt['decision_evidence']), 2)
        self.assertEqual(transport['original_request_sha256'], self.contract['original_request_sha256'])
        self.assertNotEqual(transport['original_request_sha256'], transport['materialized_request_sha256'])
        self.assertEqual(receipt['request_sha256'], transport['materialized_request_sha256'])
        for entry in transport['dependencies']:
            target = Path(entry['materialized_path'])
            self.assertEqual(bridge.sha(target.read_bytes()), entry['sha256'])
            self.assertEqual(target.stat().st_mode & 0o222, 0)
        history = receipt['sources'][0]['history']
        self.assertFalse(history['exact_first_view_known'])
        self.assertEqual(len(history['original_history_rows']), 3)
        self.assertFalse(receipt['primary_results_published'])
        self.assertFalse(receipt['scientific_authorization_granted'])
        self.assertFalse(receipt['g0_granted'])
        if os.environ.get('A_DAG_CASE_EVIDENCE_ROOT'):
            evidence = Path(os.environ['A_DAG_CASE_EVIDENCE_ROOT']) / 'materialization-success'
            evidence.mkdir()
            for output in self.outputs:
                shutil.copyfile(output, evidence / output.name)
            shutil.copytree(self.root / 'candidate', evidence / 'candidate')

    def test_02_missing_declared_dependency_refuses_before_receipt(self):
        with self.assertRaisesRegex(ValueError, 'Missing or extra'):
            bridge.run_assembly(self.inputs[:-1], self.outputs, self.root / 'materialized', self.lock)
        self.assertFalse(any(p.exists() for p in self.outputs))

    def test_03_staged_sha_mismatch_refuses_before_receipt(self):
        self.inputs[-1].chmod(0o600)
        self.inputs[-1].write_bytes(self.inputs[-1].read_bytes() + b'TAMPER')
        with self.assertRaisesRegex(ValueError, 'SHA/bytes differ'):
            bridge.run_assembly(self.inputs, self.outputs, self.root / 'materialized', self.lock)
        self.assertFalse(any(p.exists() for p in self.outputs))

    def test_04_undeclared_request_dependency_refuses_before_receipt(self):
        contract = copy.deepcopy(self.contract)
        # Removing a closure record while leaving request bytes unchanged must
        # fail even when the caller supplies the shortened matching port list.
        contract['entries'].pop()
        self.inputs[0].chmod(0o600)
        self.inputs[0].write_bytes(bridge.encode(contract))
        with self.assertRaisesRegex(ValueError, 'closure declaration differs'):
            bridge.run_assembly(self.inputs[:-1], self.outputs, self.root / 'materialized', self.lock)
        self.assertFalse(any(p.exists() for p in self.outputs))

    def test_05_generated_file_ports_and_official_edges_are_exact(self):
        manifest = tomllib.loads((self.root / 'candidate/assembly/manifest.toml').read_text())
        definition = manifest['nodes'][0]
        self.assertEqual(len(definition['ports']['inputs']), len(self.inputs))
        self.assertEqual(definition['stage_in_mode'], 'copy')
        self.assertEqual(json.loads(definition['command']['files']['source-lock.json']), self.lock)
        edges = self.candidate['edges']
        assembly = [e for e in edges if e['to'] == 'assemble']
        self.assertEqual([e['to_port'] for e in assembly], list(range(len(self.inputs))))
        self.assertEqual(len({e['from'] for e in assembly}), len(self.inputs))
        official = [e for e in edges if e['to'] == 'official']
        self.assertEqual([(e['from'], e['from_port'], e['to_port']) for e in official],
            [('assemble', 1, 0), ('assemble', 2, 1), ('input9', 0, 2), ('input16', 0, 3)])
        self.assertEqual(self.contract['entries'][15]['role'], 'implementation:' + bridge.IMPLEMENTATIONS[3])
        self.assertEqual(self.contract['entries'][8]['role'], 'frozen:8')
        self.assertEqual(self.contract['entries'][8]['sha256'], 'f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd')
        native = json.loads((self.root / 'candidate/native-dag-manifest.json').read_bytes())
        self.assertEqual(set(native), {'schema_version', 'nodes', 'edges'})
        self.assertEqual(native['schema_version'], 1)
        self.assertEqual(native['nodes'], self.candidate['nodes'])
        self.assertEqual(native['edges'], self.candidate['edges'])
        self.assertTrue(all(0 <= e['from_port'] <= 255 and 0 <= e['to_port'] <= 255 for e in native['edges']))

    def test_06_upstream_r_process_failure_has_no_success_outputs(self):
        # An inert worker returning 23 exercises new shell failure propagation.
        # It never interprets R, estimates a model or repeats p.adjust.
        executable_dir = self.root / 'bin'
        executable_dir.mkdir()
        worker = executable_dir / 'Rscript'
        worker.write_text('#!/bin/sh\nexit 23\n')
        worker.chmod(0o700)
        environment = dict(os.environ, PATH=str(executable_dir) + ':' + os.environ['PATH'],
            AUTONOMICS_INPUT_COUNT='4', AUTONOMICS_OUTPUT_COUNT='3', AUTONOMICS_WORKDIR=str(self.root))
        for i, source in enumerate([self.inputs[10], self.inputs[10], self.inputs[9], self.inputs[16]]):
            environment['AUTONOMICS_INPUT' + str(i)] = str(source)
        for i, output in enumerate(self.outputs[:3]):
            environment['AUTONOMICS_OUTPUT' + str(i)] = str(output)
        result = subprocess.run(['sh', str(HERE / 'scripts/adjust.sh')], env=environment, capture_output=True)
        self.assertEqual(result.returncode, 23, result.stderr.decode())
        self.assertFalse(any(p.exists() for p in self.outputs))

    def test_07_sdk_port_overflow_is_blocked_before_candidate_generation(self):
        request = json.loads(self.inputs[10].read_bytes())
        request['sources'] = [dict(source_id='s' + str(i), path='/unmounted/source' + str(i), sha256='0' * 64)
            for i in range(240)]
        request['seen_history'] = []
        request['edges'] = []
        with self.assertRaisesRegex(ValueError, 'SDK u8 port limit'):
            bridge.records(request, str(STUDY), str(HERE.parent), '/unmounted/request', '0' * 64, self.lock)

    def test_08_aggregate_byte_budget_is_blocked_before_materialization(self):
        contract = copy.deepcopy(self.contract)
        for entry in contract['entries']:
            entry['bytes'] = 32 * 1024**2
        self.inputs[0].chmod(0o600)
        self.inputs[0].write_bytes(bridge.encode(contract))
        with self.assertRaisesRegex(ValueError, 'Aggregate File byte budget'):
            bridge.run_assembly(self.inputs, self.outputs, self.root / 'materialized', self.lock)
        self.assertFalse((self.root / 'materialized').exists())
        self.assertFalse(any(p.exists() for p in self.outputs))


if __name__ == '__main__':
    unittest.main()
