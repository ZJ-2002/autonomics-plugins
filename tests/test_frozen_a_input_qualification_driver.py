import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import tomllib
import unittest

from tools import prove_frozen_a_input_qualification as proof


class FrozenAInputQualificationDriverTests(unittest.TestCase):
    def command_fixture(self):
        records = []
        project = Path('/work/.frozen-a-input-stage-toy/project')
        output = project / '03_AUDIT/G0_v4.3.2_2026-10-11'
        for phase in ['clump', 'haplotype_paircheck']:
            for chromosome in range(1, 14):
                prefix = [str(project / '04_SOFTWARE/bin/plink'), '--bfile', f'/panels/ld_ref/1000G.EUR.QC.{chromosome}']
                if phase == 'clump':
                    command = prefix + ['--clump', str(output / 'A_CLUMP_INPUT.tsv'), '--clump-p1', '5e-8', '--clump-p2', '1',
                        '--clump-r2', '0.001', '--clump-kb', '10000', '--threads', '1', '--memory', '1024', '--out',
                        str(output / 'clumping' / f'chr{chromosome}')]
                else:
                    command = prefix + ['--extract', str(output / 'clumping/retained_ids.txt'), '--r2', 'dprime',
                        '--ld-window', '99999', '--ld-window-kb', '10000', '--ld-window-r2', '0', '--threads', '1',
                        '--memory', '1024', '--out', str(output / 'clumping' / f'haplotype_paircheck_chr{chromosome}')]
                records.append(dict(phase=phase, chromosome=chromosome, argv=command, actual_exit=0))
        qc = dict(commands=[dict(argv=item['argv'], exit=0) for item in records[:13]])
        ld = dict(commands=[dict(argv=item['argv'], exit=0) for item in records[13:]])
        return records, qc, ld

    def archive_fixture(self, directory, *, mutation=None):
        instruments = []
        observed = []
        summary = []
        for index in range(11):
            first, second = 'first' + str(index), 'second' + str(index)
            start = 1 + index * 20000000
            instruments.extend([dict(snp=first, chr37='1', pos37=str(start)),
                                dict(snp=second, chr37='1', pos37=str(start + 1))])
            observed.append(dict(CHR_A='1', BP_A=str(start), SNP_A=first, CHR_B='1', BP_B=str(start + 1), SNP_B=second, R2='0.0001'))
            summary.append(dict(SNP1=first, SNP2=second, chr37='1', distance_bp='1', haplotype_r2='0.0001'))
        for index in range(17):
            instruments.append(dict(snp='single' + str(index), chr37='2', pos37=str(1 + index * 20000000)))
        if mutation == 'missing_pair':
            observed.pop()
        if mutation == 'duplicate_pair':
            observed.append(copy.deepcopy(observed[0]))
        if mutation == 'coordinate':
            observed[0]['BP_A'] = '2'
        columns = ['CHR_A', 'BP_A', 'SNP_A', 'CHR_B', 'BP_B', 'SNP_B', 'R2']
        payload = (' '.join(columns) + '\n' + '\n'.join(' '.join(row[key] for key in columns) for row in observed) + '\n').encode()
        path = directory / 'official-artifacts.tar'
        declared = []
        with tarfile.open(path, 'w') as archive:
            info = tarfile.TarInfo('clumping/haplotype_paircheck_chr1.ld')
            info.size = len(payload)
            if mutation == 'symlink':
                info.type = tarfile.SYMTYPE
                info.linkname = '/outside'
                info.size = 0
                archive.addfile(info)
            else:
                archive.addfile(info, io.BytesIO(payload))
            declared.append(dict(path=info.name, bytes=info.size, sha256=hashlib.sha256(payload).hexdigest()))
            if mutation == 'undeclared':
                extra = tarfile.TarInfo('clumping/extra.log')
                extra.size = 1
                archive.addfile(extra, io.BytesIO(b'x'))
        return path, dict(official_archive_members=declared), instruments, summary

    def test_final_manifest_pins_nine_inputs_twelve_outputs_and_two_gib(self):
        for name, expected in proof.SOURCE_PINS.items():
            self.assertEqual(proof.digest(proof.FAMILY / name), expected)
        manifest = tomllib.loads((proof.FAMILY / 'manifest.toml').read_text())
        node = manifest['nodes'][0]
        self.assertEqual((len(node['ports']['inputs']), len(node['ports']['outputs'])), (9, 12))
        self.assertEqual(node['resources']['memory'], '2Gi')
        self.assertEqual(manifest['image']['reference'], proof.IMAGE)
        self.assertNotIn('params', node)

    def test_stopped_known_build_is_observed_not_inferred_from_missing_pid(self):
        text = 'LoadState=not-found\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\n'
        self.assertEqual(proof.check_known_build(text, 1)['MainPID'], '0')

    def test_active_known_build_refuses_another_heavy_task(self):
        text = 'LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=123\nControlPID=0\n'
        with self.assertRaisesRegex(RuntimeError, 'Known large build'):
            proof.check_known_build(text, 0)

    def test_incomplete_or_failed_process_observation_is_not_admission(self):
        for text, exit_code in [('', 1), ('MainPID=0\n', 0),
                ('LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\n', 2)]:
            with self.assertRaises(RuntimeError):
                proof.check_known_build(text, exit_code)

    def test_nine_toy_source_identities_are_streamed_and_rechecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, contract = [], dict(inputs=[])
            for index in range(9):
                path = root / ('toy' + str(index))
                path.write_bytes(('payload' + str(index)).encode())
                paths.append(path)
                contract['inputs'].append(dict(port=index, name=path.name, bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            before = proof.source_facts(paths, contract)
            self.assertEqual(len(before), 9)
            self.assertEqual(proof.source_facts(paths, contract), before)
            paths[2].write_bytes(b'changed2')
            with self.assertRaises(RuntimeError):
                proof.source_facts(paths, contract)

    def test_canonical_source_symlink_is_not_an_ordinary_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target, link = root / 'target', root / 'alias'
            target.write_bytes(b'toy')
            link.symlink_to(target)
            with self.assertRaises(RuntimeError):
                proof.ordinary(link)

    def test_exact_twenty_six_original_commands_are_accepted(self):
        proof.validate_commands(*self.command_fixture())

    def test_missing_or_failed_plink_command_is_rejected(self):
        records, qc, ld = self.command_fixture()
        with self.assertRaises(RuntimeError):
            proof.validate_commands(records[:-1], qc, ld)
        records[-1]['actual_exit'] = 1
        with self.assertRaises(RuntimeError):
            proof.validate_commands(records, qc, ld)

    def test_changed_ld_statistic_or_threshold_is_rejected(self):
        for position, old, new in [(0, '0.001', '0.01'), (13, 'dprime', 'square')]:
            records, qc, ld = self.command_fixture()
            argv = records[position]['argv']
            argv[argv.index(old)] = new
            with self.assertRaises(RuntimeError):
                proof.validate_commands(records, qc, ld)

    def test_duplicate_chromosome_does_not_fill_twenty_six_count(self):
        records, qc, ld = self.command_fixture()
        records[1] = copy.deepcopy(records[0])
        qc['commands'][1] = copy.deepcopy(qc['commands'][0])
        with self.assertRaises(RuntimeError):
            proof.validate_commands(records, qc, ld)

    def test_official_archive_requires_all_eleven_complete_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            fact = proof.validate_official_archive(*self.archive_fixture(Path(temporary)))
            self.assertEqual(fact['complete_haplotype_pairs'], 11)

    def test_missing_duplicate_or_wrongly_located_ld_pair_is_rejected(self):
        for mutation in ['missing_pair', 'duplicate_pair', 'coordinate']:
            with tempfile.TemporaryDirectory() as temporary:
                fixture = self.archive_fixture(Path(temporary), mutation=mutation)
                with self.assertRaises(RuntimeError):
                    proof.validate_official_archive(*fixture)

    def test_official_tar_alias_or_undeclared_member_is_rejected(self):
        for mutation in ['symlink', 'undeclared']:
            with tempfile.TemporaryDirectory() as temporary:
                fixture = self.archive_fixture(Path(temporary), mutation=mutation)
                with self.assertRaises(RuntimeError):
                    proof.validate_official_archive(*fixture)

    def test_specific_config_refusal_has_no_normal_publications(self):
        definition = dict(ports=dict(outputs=[dict(path='port' + str(index)) for index in range(12)]))
        result = subprocess.CompletedProcess([], 2, '', 'BLOCKED: Frozen input bytes differ: A_ANALYSIS_CONFIG.json')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            proof.validate_negative(result, directory, definition)
            (directory / 'port0').write_bytes(b'bad leaked result')
            with self.assertRaises(RuntimeError):
                proof.validate_negative(result, directory, definition)

    def test_oom_or_startup_failure_cannot_be_counted_as_guard_success(self):
        definition = dict(ports=dict(outputs=[dict(path='port' + str(index)) for index in range(12)]))
        with tempfile.TemporaryDirectory() as temporary:
            for exit_code, stderr in [(137, 'Frozen input bytes differ: A_ANALYSIS_CONFIG.json'), (2, 'OCI runtime error'), (0, '')]:
                with self.assertRaises(RuntimeError):
                    proof.validate_negative(subprocess.CompletedProcess([], exit_code, '', stderr), Path(temporary), definition)


if __name__ == '__main__':
    unittest.main()
