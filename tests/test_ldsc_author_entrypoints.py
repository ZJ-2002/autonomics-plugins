import unittest
import hashlib
import json

from tools import prove_ldsc_entrypoints as proof


class AuthorEntrypointParityTests(unittest.TestCase):
    def test_current_migration_evidence_binds_the_actual_dispatched_sources(self):
        document=json.loads((proof.ROOT/'evidence/ldsc-author-runtime-migration-20261015.json').read_text())
        self.assertEqual(document['image'],proof.IMAGE)
        for name,expected in document['source_sha256'].items():
            self.assertEqual(hashlib.sha256((proof.ROOT/name).read_bytes()).hexdigest(),expected,name)
        self.assertFalse(document['g0_granted'])
        self.assertEqual(document['layer_status']['isolated_current_DAG'],'PENDING')
        cases=document['canonical_entrypoint_proof']['cases']
        self.assertEqual(len(cases),7)
        self.assertTrue(all(row['complete_log_bytes']>0 for row in cases))
        self.assertEqual(document['withdrawn_claims'][0]['session'],'e1b438845e764933965c82a231f95eba')

    def test_only_paths_and_three_runtime_timing_lines_are_normalized(self):
        value="Beginning analysis at NOW\nP: 0.00012345\nReading /work/input\nTotal time elapsed: 2s\n"
        result=proof.normalize_log(value,[("/work/input","<INPUT>")])
        self.assertEqual(result,"P: 0.00012345\nReading <INPUT>")
        self.assertNotEqual(result,proof.normalize_log(value.replace("0.00012345","0.0001"),[("/work/input","<INPUT>")]))

    def test_merged_failure_contract_requires_all_author_lines_and_actual_nonzero_exit(self):
        error="/opt/cachexia-official-ldsc/ldscore/sumstats.py\nKeyError: 'AGAC'\ntraceback.format_exc\nTypeError\n"
        merged="method stdout\n"+error+"author log\n"
        proof.check_author_failure(merged,"author log\n",error,1,1)
        for actual,observed,reference in [(merged,0,1),(merged,1,0),(merged.replace("TypeError\n",""),1,1),
                                          (merged.replace("KeyError: 'AGAC'","KeyError: OTHER"),1,1)]:
            with self.assertRaises(RuntimeError):
                proof.check_author_failure(actual,"author log\n",error,observed,reference)

    def test_empty_equal_logs_cannot_prove_an_inference_result(self):
        for method in ["h2", "rg"]:
            with self.subTest(method=method), self.assertRaises(RuntimeError):
                proof.check_positive_log("", "", [], method, "observed")
        log="Summary of Genetic Correlation Results\nGenetic Covariance\nGenetic Correlation: 0.4772\n"
        proof.check_positive_log(log,log,[],"rg","observed")
        with self.assertRaises(RuntimeError):
            proof.check_positive_log(log.replace("0.4772","0.5"),log,[],"rg","observed")


if __name__ == "__main__":
    unittest.main()
