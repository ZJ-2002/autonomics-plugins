import copy
import json
import unittest

from tools import prove_ldsc_panel_payloads as proof


class DeclaredPanelPayloadTests(unittest.TestCase):
    def manifests(self):
        return [json.loads(path.read_text()) for path in sorted((proof.ROOT/'provenance/ldsc-declared-panels').glob('*.json'))]

    def test_actual_public_manifests_match_their_canonical_catalog_digests(self):
        evidence=json.loads((proof.ROOT/'evidence/ldsc-declared-panel-resources-20261015.json').read_text())
        for name,expected in evidence['source_sha256'].items():
            self.assertEqual(proof.digest(proof.ROOT/name),expected)
        self.assertFalse(evidence['author_distribution_origin_independently_proven'])
        self.assertFalse(evidence['current_DAG_or_daemon_qualified'])
        self.assertFalse(evidence['g0_granted'])
        values=self.manifests()
        self.assertEqual(len(values),2)
        files=[proof.validate_manifest(value,value['repo'],value['digest']) for value in values]
        self.assertEqual(sum(len(items) for items in files),88)
        self.assertEqual(sum(item['size'] for items in files for item in items),26093666)

    def test_missing_duplicate_or_noncanonical_payloads_are_rejected(self):
        original=self.manifests()[0]
        for mutation in ['missing','duplicate','unsafe','content']:
            value=copy.deepcopy(original)
            if mutation=='missing': value['files'].pop()
            elif mutation=='duplicate': value['files'][-1]=value['files'][0]
            elif mutation=='unsafe': value['files'][0]['path']='../outside'
            else: value['files'][0]['sha256']='sha256:'+'0'*64
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                proof.validate_manifest(value,original['repo'],original['digest'])

    def test_wrong_identity_boolean_size_or_unknown_semantics_fail_closed(self):
        original=self.manifests()[0]
        for mutation in ['identity','size','metadata','payload','schema']:
            value=copy.deepcopy(original)
            if mutation=='identity': value['repo']='other/repository'
            elif mutation=='size': value['files'][0]['size']=True
            elif mutation=='metadata': value['metadata']['population']='OTHER'
            elif mutation=='payload': value['payload']['not_reviewed']=True
            else: value['schema_version']=True
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                proof.validate_manifest(value,original['repo'],original['digest'])


if __name__ == '__main__':
    unittest.main()
