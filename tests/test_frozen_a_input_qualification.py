import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/frozen-a-input-qualification'
SPEC = importlib.util.spec_from_file_location('frozen_a_input_qualification', FAMILY / 'scripts/qualify.py')
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


def pair_fixture():
    instruments = [dict(snp='first', chr37='1', pos37='100'), dict(snp='second', chr37='1', pos37='200'),
        dict(snp='boundary', chr37='1', pos37='10000100'), dict(snp='other_chr', chr37='2', pos37='100')]
    observed = []
    for first, second in [('first', 'second'), ('first', 'boundary'), ('second', 'boundary')]:
        one = next(item for item in instruments if item['snp'] == first)
        two = next(item for item in instruments if item['snp'] == second)
        observed.append(dict(CHR_A=one['chr37'], BP_A=one['pos37'], SNP_A=first,
            CHR_B=two['chr37'], BP_B=two['pos37'], SNP_B=second, R2='0.0001'))
    summary = [dict(chr37=item['CHR_A'], SNP1=item['SNP_A'], SNP2=item['SNP_B'],
        distance_bp=str(abs(int(item['BP_A']) - int(item['BP_B']))), haplotype_r2=item['R2']) for item in observed]
    return instruments, observed, summary


def publication_fixture(root):
    inputs = [root / ('input' + str(index)) for index in range(9)]
    for index, path in enumerate(inputs):
        path.write_bytes(('source' + str(index)).encode())
    outputs = [root / name for name in qualification.OUTPUTS]

    def compute(inputs, stage):
        for index, name in enumerate(qualification.OUTPUTS):
            if index != 10:
                (stage / name).write_bytes(('toy product ' + str(index)).encode())
        print('toy execution complete')
    return inputs, outputs, compute


def panel_fixture(root):
    panel = root / 'panel'
    panel.mkdir()
    entries = []
    for chromosome in range(1, 23):
        for suffix in ['bed', 'bim', 'fam']:
            path = panel / f'1000G.EUR.QC.{chromosome}.{suffix}'
            path.write_bytes((b'fixture\n' * 489) if suffix == 'fam' else b'fixture')
            entries.append(dict(path=path.name, size=path.stat().st_size, sha256='sha256:' + qualification.digest(path)))
    manifest = root / 'input7.json'
    manifest.write_text(json.dumps(dict(digest=qualification.PANEL_DIGEST, metadata=dict(population='EUR', genome_build='GRCh37'), files=entries)))
    pins = list(qualification.INPUT_PINS)
    pins[7] = ('manifest.json', manifest.stat().st_size, qualification.digest(manifest))
    return panel, manifest, pins


class FrozenAInputQualificationTests(unittest.TestCase):
    def test_manifest_pins_nine_inputs_twelve_outputs_and_zero_copy_staging(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest['image']['reference'],
            'docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d')
        self.assertEqual(manifest['panels'], [dict(binding='ld_ref', mount='/panels/ld_ref',
            bundle='wjixiang/catalog-plink-ref-1000g-eur-binary')])
        self.assertEqual(len(manifest['nodes']), 1)
        node = manifest['nodes'][0]
        self.assertEqual(node['kind'], 'frozen_a_v432_input_qualification')
        self.assertEqual(node['stage_in_mode'], 'symlink')
        self.assertNotIn('params', node)
        self.assertEqual(len(node['ports']['inputs']), 9)
        self.assertEqual([item['path'] for item in node['ports']['outputs']], qualification.OUTPUTS)
        self.assertEqual(node['resources']['pull_policy'], 'never')
        self.assertEqual(node['resources']['memory'], '2Gi')
        self.assertTrue(node['resources']['read_only_rootfs'])

    def test_contract_is_exact_and_does_not_claim_scientific_authority(self):
        contract = json.loads((FAMILY / 'contracts/source-lock.json').read_text())
        self.assertEqual(contract['schema'], 'FROZEN_V432_A_INPUT_QUALIFICATION_SOURCE_CONTRACT_V1')
        self.assertEqual([(item['name'], item['bytes'], item['sha256']) for item in contract['inputs']], qualification.INPUT_PINS)
        self.assertEqual([item['port'] for item in contract['inputs']], list(range(9)))
        self.assertEqual(contract['existing_expected_outputs'], qualification.EXPECTED_OUTPUT_SHA)
        self.assertEqual(contract['Python'], '3.14.7')
        self.assertFalse(contract['scientific_authorization_granted'])
        self.assertFalse(contract['g0_granted'])

    def test_separate_panel_manifest_accepts_exact_payload_only_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            panel, manifest, pins = panel_fixture(Path(directory))
            with mock.patch.object(qualification, 'INPUT_PINS', pins):
                self.assertEqual(len(qualification.panel_records(panel, manifest)), 66)
                (panel / 'manifest.json').write_bytes(manifest.read_bytes())
                self.assertEqual(len(qualification.panel_records(panel, manifest)), 66)

    def test_panel_tampering_or_conflicting_embedded_manifest_is_rejected(self):
        for failure in ['missing', 'changed', 'conflicting_manifest']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                panel, manifest, pins = panel_fixture(Path(directory))
                if failure == 'missing':
                    (panel / '1000G.EUR.QC.22.bed').unlink()
                elif failure == 'changed':
                    (panel / '1000G.EUR.QC.22.bed').write_bytes(b'changed')
                else:
                    (panel / 'manifest.json').write_text('{}')
                with mock.patch.object(qualification, 'INPUT_PINS', pins):
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        qualification.panel_records(panel, manifest)

    def test_source_hash_verification_rejects_same_size_changed_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, _, _ = publication_fixture(root)
            pins = [(path.name, path.stat().st_size, qualification.digest(path)) for path in paths]
            with mock.patch.object(qualification, 'INPUT_PINS', pins):
                self.assertEqual(len(qualification.source_records(paths)), 9)
                paths[0].write_bytes(b'changed')
                self.assertEqual(paths[0].stat().st_size, pins[0][1])
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    qualification.source_records(paths)

    def test_pairset_includes_exact_ten_megabase_boundary(self):
        instruments, observed, summary = pair_fixture()
        result = qualification.complete_pair_envelope(instruments, observed, summary)
        self.assertEqual((result['expected_pairs'], result['observed_pairs']), (3, 3))

    def test_pairset_missing_or_reverse_duplicate_is_rejected(self):
        instruments, observed, summary = pair_fixture()
        with self.assertRaisesRegex(ValueError, 'missing pairs'):
            qualification.complete_pair_envelope(instruments, observed[:-1], summary[:-1])
        reverse = {**observed[0], 'SNP_A': observed[0]['SNP_B'], 'SNP_B': observed[0]['SNP_A'],
            'BP_A': observed[0]['BP_B'], 'BP_B': observed[0]['BP_A']}
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            qualification.complete_pair_envelope(instruments, [*observed, reverse], summary)

    def test_pairset_threshold_nonfinite_and_negative_r2_are_rejected(self):
        instruments, observed, summary = pair_fixture()
        for value in ['0.001', '0.002', 'nan', 'inf', '-0.001']:
            changed = copy.deepcopy(observed)
            changed[0]['R2'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'strictly below'):
                qualification.complete_pair_envelope(instruments, changed, summary)

    def test_pairset_wrong_coordinates_and_outside_window_are_rejected(self):
        instruments, observed, summary = pair_fixture()
        changed = copy.deepcopy(observed)
        changed[0]['BP_A'] = '101'
        with self.assertRaisesRegex(ValueError, 'coordinates'):
            qualification.complete_pair_envelope(instruments, changed, summary)
        changed_instruments = copy.deepcopy(instruments)
        changed_instruments[2]['pos37'] = '10000101'
        changed = copy.deepcopy(observed)
        changed[1]['BP_B'] = '10000101'
        with self.assertRaisesRegex(ValueError, 'outside'):
            qualification.complete_pair_envelope(changed_instruments, changed, summary)

    def test_original_summary_cannot_omit_duplicate_or_modify_pairs(self):
        instruments, observed, summary = pair_fixture()
        for changed in [summary[:-1], [*summary, summary[0]], [{**summary[0], 'distance_bp': '101'}, *summary[1:]]]:
            with self.assertRaises(ValueError):
                qualification.complete_pair_envelope(instruments, observed, changed)

    def test_restricted_proxy_accepts_exact_thirteen_plus_thirteen_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proxy = qualification.RestrictedPLINK(root / 'plink', root / 'panel', root / 'output')
            with mock.patch.object(qualification.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                for chromosome in [1, 3, 5, 6, 8, 9, 12, 13, 14, 15, 17, 18, 19]:
                    reference = str(proxy.panel / f'1000G.EUR.QC.{chromosome}')
                    clump = [str(proxy.program), '--bfile', reference, '--clump', str(proxy.output / 'A_CLUMP_INPUT.tsv'),
                        '--clump-p1', '5e-8', '--clump-p2', '1', '--clump-r2', '0.001', '--clump-kb', '10000',
                        '--threads', '1', '--memory', '1024', '--out', str(proxy.output / 'clumping' / f'chr{chromosome}')]
                    paircheck = [str(proxy.program), '--bfile', reference, '--extract', str(proxy.output / 'clumping/retained_ids.txt'),
                        '--r2', 'dprime', '--ld-window', '99999', '--ld-window-kb', '10000', '--ld-window-r2', '0',
                        '--threads', '1', '--memory', '1024', '--out', str(proxy.output / 'clumping' / f'haplotype_paircheck_chr{chromosome}')]
                    for command in [clump, paircheck]:
                        proxy.run(command, capture_output=True, text=True)
                self.assertEqual(run.call_count, 26)
                self.assertEqual(sum(item['phase'] == 'clump' for item in proxy.executions), 13)
                self.assertEqual(sum(item['phase'] == 'haplotype_paircheck' for item in proxy.executions), 13)

    def test_fallback_copy_downloader_and_modified_resource_argv_are_rejected(self):
        proxy = qualification.RestrictedPLINK(Path('/owned/plink'), Path('/panel'), Path('/owned/output'))
        invalid = [['cp', '/raw/source', '/data/copy'], ['curl', 'https://example.invalid'],
            ['/owned/plink', '--bfile', '/panel/1000G.EUR.QC.1', '--threads', '2']]
        with mock.patch.object(qualification.subprocess, 'run') as run:
            for command in invalid:
                with self.assertRaises(ValueError):
                    proxy.run(command, capture_output=True, text=True)
            run.assert_not_called()

    def test_successful_publication_checks_all_ports_and_cleans_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, outputs, compute = publication_fixture(root)
            before = [qualification.identity(path) for path in inputs]
            qualification.publish_outputs(inputs, outputs, compute)
            self.assertTrue(all(path.is_file() and path.stat().st_size > 0 for path in outputs))
            self.assertEqual(before, [qualification.identity(path) for path in inputs])
            self.assertEqual(list(root.glob('.frozen-a-input-stage-*')), [])

    def test_existing_output_and_dangling_link_are_never_overwritten(self):
        for dangling in [False, True]:
            with self.subTest(dangling=dangling), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                inputs, outputs, compute = publication_fixture(root)
                if dangling:
                    outputs[10].symlink_to(root / 'absent')
                else:
                    outputs[10].write_bytes(b'old protected log')
                with self.assertRaisesRegex(ValueError, 'Refusing existing'):
                    qualification.publish_outputs(inputs, outputs, compute)
                if dangling:
                    self.assertTrue(outputs[10].is_symlink())
                else:
                    self.assertEqual(outputs[10].read_bytes(), b'old protected log')

    def test_nonthrowing_foreign_replacement_preserves_foreign_and_rolls_back_owned(self):
        for port in [0, 11]:
            with self.subTest(port=port), tempfile.TemporaryDirectory() as directory:
                inputs, outputs, compute = publication_fixture(Path(directory))
                original_link = qualification.os.link

                def replace_after_link(source, destination):
                    original_link(source, destination)
                    if destination == outputs[port]:
                        destination.unlink()
                        destination.write_bytes(b'foreign replacement')

                with mock.patch.object(qualification.os, 'link', side_effect=replace_after_link):
                    with self.assertRaisesRegex(ValueError, 'ownership or content'):
                        qualification.publish_outputs(inputs, outputs, compute)
                self.assertEqual(outputs[port].read_bytes(), b'foreign replacement')
                self.assertTrue(outputs[10].is_file())
                self.assertTrue(all(not path.exists() for index, path in enumerate(outputs) if index not in [port, 10]))

    def test_method_failure_keeps_only_diagnostic_log_without_normal_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs, outputs, _ = publication_fixture(Path(directory))

            def fail(inputs, stage):
                (stage / qualification.OUTPUTS[0]).write_bytes(b'partial unpublished product')
                raise ValueError('expected source rejection')

            with self.assertRaisesRegex(ValueError, 'expected source rejection'):
                qualification.publish_outputs(inputs, outputs, fail)
            self.assertIn('expected source rejection', outputs[10].read_text())
            self.assertTrue(all(not path.exists() for index, path in enumerate(outputs) if index != 10))


if __name__ == '__main__':
    unittest.main()
