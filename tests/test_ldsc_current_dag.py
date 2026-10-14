import hashlib
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from tools import prove_current_ldsc as proof


class CurrentLdscDagContractTests(unittest.TestCase):
    def test_staged_raw_input_requires_exact_source_bytes_and_port_binding(self):
        evidence=json.loads((proof.ROOT/'evidence/current-ldsc-dag-20261015.json').read_text())
        for name,expected in evidence['source_sha256'].items():
            self.assertEqual(proof.digest(proof.ROOT/name),expected,name)
        self.assertEqual(evidence['positive_DAGs'],8)
        self.assertEqual(evidence['exact_author_failure_DAGs'],1)
        self.assertEqual(evidence['actual_input_bindings_independently_byte_checked'],13)
        self.assertFalse(evidence['daemon_or_production_changed'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original=root/'input-0.tsv'
            original.write_bytes(b'SNP\tZ\nrs001\t1.0\n')
            work=root/'work'
            work.mkdir()
            (work/original.name).write_bytes(original.read_bytes())
            scratch=root/'scratch'
            staged=scratch/'.autonomics/inputs/input-0.tsv'
            staged.parent.mkdir(parents=True)
            staged.write_bytes(original.read_bytes())
            analysis=dict(inputs=[dict(to_port=0,**{'from':'input0'},path='vfs:///input-0.tsv',fingerprint=dict(size=original.stat().st_size))])
            result=proof.check_staged_inputs(work,[original],analysis,scratch)
            self.assertEqual(result[0]['source_sha256'],result[0]['actual_staged_sha256'])
            staged.write_bytes(b'WRONG')
            with self.assertRaises(RuntimeError):
                proof.check_staged_inputs(work,[original],analysis,scratch)

    def test_gzip_input_requires_complete_materialized_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original=root/'input-0.sumstats.gz'
            original.write_bytes(gzip.compress(b'COMPLETE PLAINTEXT',mtime=0))
            work=root/'work'
            work.mkdir()
            (work/original.name).write_bytes(original.read_bytes())
            scratch=root/'scratch'
            staged=scratch/'.autonomics/inputs/input-0.sumstats.gz'
            staged.parent.mkdir(parents=True)
            staged.write_bytes(original.read_bytes())
            plaintext=scratch/'.autonomics/input-0.tsv'
            plaintext.write_bytes(b'COMPLETE PLAINTEXT')
            analysis=dict(inputs=[dict(to_port=0,**{'from':'input0'},path='vfs:///'+original.name,fingerprint=dict(size=original.stat().st_size))])
            proof.check_staged_inputs(work,[original],analysis,scratch)
            plaintext.write_bytes(b'PARTIAL')
            with self.assertRaises(RuntimeError):
                proof.check_staged_inputs(work,[original],analysis,scratch)

    def test_summary_path_padding_does_not_change_any_scientific_field(self):
        header=" ".join(proof.TABLE_COLUMNS)
        body="0.4772 0.054 8.8444 0.0000 0.2848 0.0237 -0.7813 1.0149 -0.1067 0.8577"
        first="Summary of Genetic Correlation Results\n"+header+"\n/source/first /source/second "+body
        second="Summary of Genetic Correlation Results\n"+header.replace(" ","    ")+"\n/longer/first    /longer/second   "+body
        substitutions=[("/source/first","<INPUT0>"),("/source/second","<INPUT1>"),
                       ("/longer/first","<INPUT0>"),("/longer/second","<INPUT1>")]
        self.assertEqual(proof.normalize_engine_log(first,substitutions),proof.normalize_engine_log(second,substitutions))
        self.assertNotEqual(proof.normalize_engine_log(first,substitutions),proof.normalize_engine_log(second.replace("0.4772","0.4773"),substitutions))

    def test_truncated_summary_row_cannot_be_normalized_into_a_result(self):
        with self.assertRaises(RuntimeError):
            proof.normalize_engine_log("Summary of Genetic Correlation Results\n<INPUT0> <INPUT1> 0.1",[])

    def test_synthetic_panel_names_and_exact_manifest_bytes_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original=root/'original'
            for binding in proof.PANEL_IDS:
                (original/binding).mkdir(parents=True)
                (original/binding/'fixture.gz').write_bytes(b'SYNTHETIC ONLY')
            work=root/'work'
            bundles,hashes=proof.panels(work,original)
            self.assertEqual(len(bundles),2)
            for bundle in bundles:
                self.assertTrue(bundle['ident'].startswith('autonomics-technical/'))
                self.assertNotIn('wjixiang',bundle['ident'])
                path=work/bundle['source'].removeprefix('/')/'manifest.json'
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),hashes[bundle['source']])
                manifest=json.loads(path.read_text())
                self.assertEqual(manifest['id'],bundle['ident'])
                self.assertEqual(manifest['digest'],bundle['digest'])
                self.assertEqual(len(manifest['files']),1)

    def test_published_port_must_match_nonempty_owned_live_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            scratch=root/'scratch'
            scratch.mkdir()
            live=scratch/'result.log'
            live.write_bytes(b'ACTUAL AUTHOR RESULT')
            work=root/'work'
            published=work/'artifacts/ldsc/run/result.log'
            published.parent.mkdir(parents=True)
            published.write_bytes(live.read_bytes())
            definition=dict(artifact_prefix='/artifacts/ldsc',ports=dict(outputs=[dict(path='result.log',format='ldsc_log')]))
            analysis=dict(port_assignments={'0':dict(path=str(live),format='ldsc_log',fingerprint=dict(size=live.stat().st_size))})
            self.assertEqual(proof.check_ports(work,definition,analysis,scratch),[published])
            published.write_bytes(b'WRONG')
            with self.assertRaises(RuntimeError):
                proof.check_ports(work,definition,analysis,scratch)
            live.write_bytes(b'')
            published.write_bytes(b'')
            analysis['port_assignments']['0']['fingerprint']['size']=0
            with self.assertRaises(RuntimeError):
                proof.check_ports(work,definition,analysis,scratch)


if __name__ == '__main__':
    unittest.main()
