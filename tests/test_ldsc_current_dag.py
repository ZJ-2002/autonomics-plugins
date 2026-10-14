import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import prove_current_ldsc as proof


class CurrentLdscDagContractTests(unittest.TestCase):
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
