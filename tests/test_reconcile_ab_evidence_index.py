import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import reconcile_ab_evidence_index as index


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ReconcileEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / 'repository'
        self.repository.mkdir()
        self.method = self.repository / 'method.R'
        self.method.write_text('identity <- function(value) value\n')
        self.git('init', '--quiet')
        blob = self.git('hash-object', '-w', 'method.R')
        tree = self.git('mktree', raw=f'100644 blob {blob}\tmethod.R\n'.encode())
        self.revision = self.git('commit-tree', tree, raw=b'SYNTHETIC fixture\n')
        self.archives = self.root / 'archives'
        self.session = 'a' * 32
        self.directory = self.archives / self.session
        self.artifacts = self.directory / 'artifacts'
        self.artifacts.mkdir(parents=True)
        self.report_path = self.artifacts / 'report.json'
        self.report_path.write_bytes(encoded({'cases': [{'name': 'positive'}, {'name': 'refusal'}]}))
        manifest = {'schema': 'TECHNICAL_VALIDATION_SESSION_V1', 'session': self.session,
                    'files': {'report.json': {'bytes': self.report_path.stat().st_size,
                                             'sha256': sha(self.report_path.read_bytes())}}}
        self.manifest_path = self.artifacts / 'MANIFEST.json'
        self.manifest_path.write_bytes(encoded(manifest))
        self.seal = sha(self.manifest_path.read_bytes())
        self.session_path = self.directory / 'SESSION.json'
        self.state = {'schema': 'TECHNICAL_VALIDATION_SESSION_V1', 'session': self.session,
                      'state': 'CLEANED', 'manifest_sha256': self.seal, 'worker_exit_status': 0}
        self.session_path.write_bytes(encoded(self.state))
        self.handoff_path = self.root / 'handoff.json'
        self.handoff = {'session': self.session, 'seal': self.seal, 'cases': 2, 'revision': self.revision}
        self.handoff_path.write_bytes(encoded(self.handoff))
        self.base = self.root / 'base.tsv'
        self.rows = [{'function_id': 'FUNC_' + str(number), 'original_kind': 'kind_' + str(number),
                      'original_current_official': 'PENDING'} for number in range(120)]
        self.write_base()
        links = [{'archive': 'proof', 'member': 'report.json'}]
        self.entry = {'function_id': 'FUNC_0', 'original_kind': 'kind_0', 'mapping_id': 'SYN_one',
                      'route': 'ORIGINAL', 'adapter_kind': 'kind_0',
                      'handoff': {'path': str(self.handoff_path), 'sha256': sha(self.handoff_path.read_bytes())},
                      'archives': [{'id': 'proof', 'session_pointer': '/session', 'seal_pointer': '/seal'}],
                      'counts': [{'archive': 'proof', 'report': 'report.json', 'report_pointer': '/cases',
                                  'operation': 'count', 'case_id_key': 'name', 'label': 'cases',
                                  'handoff_pointer': '/cases', 'scope': 'SYNTHETIC_REPORT_CASES'}],
                      'sources': [{'repository': str(self.repository), 'relative_path': 'method.R',
                                   'revision_pointer': '/revision', 'revision': self.revision,
                                   'sha256': sha(self.method.read_bytes())}],
                      'layers': {name: {'links': links, 'scope': 'SYNTHETIC_LINK_ONLY', 'manual_review': True}
                                 for name in index.LAYERS}}
        self.mapping = {'schema': 'AB_EVIDENCE_RECONCILIATION_MAPPING_V1',
                        'base_sha256': sha(self.base.read_bytes()), 'expected_rows': 120,
                        'mappings': [self.entry],
                        'minimum_AB_adapters': [{'kind': 'SYN_ADAPTER_' + str(number)} for number in range(5)]}
        self.mapping_path = self.root / 'mapping.json'

    def git(self, *arguments, raw=None):
        environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                           GIT_AUTHOR_NAME='Synthetic', GIT_AUTHOR_EMAIL='synthetic@example.invalid',
                           GIT_COMMITTER_NAME='Synthetic', GIT_COMMITTER_EMAIL='synthetic@example.invalid')
        return subprocess.check_output(['git', '-C', str(self.repository), *arguments], input=raw,
                                       env=environment, stderr=subprocess.DEVNULL).decode().strip()

    def write_base(self):
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, ['function_id', 'original_kind', 'original_current_official'], delimiter='\t')
        writer.writeheader()
        writer.writerows(self.rows)
        self.base.write_text(stream.getvalue())

    def run_index(self):
        self.mapping_path.write_bytes(encoded(self.mapping))
        return index.reconcile(self.base, self.mapping_path, self.archives)

    def review(self):
        return self.run_index()['slots'][0]['current_review']

    def test_complete_facts_do_not_upgrade_historical_scientific_state(self):
        result = self.run_index()
        self.assertEqual(result['summary']['fixed_original_slots'], 120)
        self.assertEqual(result['summary']['mapped_verified_fact_packets'], 1)
        self.assertEqual(result['slots'][0]['historical_row'], self.rows[0])
        self.assertEqual(result['slots'][0]['historical_status_unchanged'], 'PENDING')
        self.assertFalse(result['slots'][0]['current_review']['qualification_upgraded'])
        self.assertFalse(result['g0_granted'])
        self.assertEqual(result['slots'][1]['current_review']['disposition'], 'INHERITED_HISTORICAL_NOT_REVERIFIED_THIS_ROUND')

    def test_seal_replacement_is_not_accepted(self):
        self.manifest_path.write_bytes(self.manifest_path.read_bytes() + b'\n')
        self.assertIn('seal differs', ' '.join(self.review()['unresolved']))

    def test_missing_member_is_not_accepted(self):
        self.report_path.unlink()
        self.assertIn('membership differs', ' '.join(self.review()['unresolved']))

    def test_unlisted_member_is_not_accepted(self):
        (self.artifacts / 'extra').write_text('SYNTHETIC')
        self.assertIn('membership differs', ' '.join(self.review()['unresolved']))

    def test_failed_worker_keeps_failure_and_does_not_become_success(self):
        self.state['worker_exit_status'] = 1
        self.session_path.write_bytes(encoded(self.state))
        review = self.review()
        self.assertEqual(review['archives'][0]['worker_exit_status'], 1)
        self.assertFalse(review['archives'][0]['positive_worker_exit_verified'])
        self.assertEqual(review['evidence_fact_status'], 'NEEDS_MANUAL_REVIEW')

    def test_missing_worker_exit_is_not_inferred(self):
        self.state['worker_exit_status'] = None
        self.session_path.write_bytes(encoded(self.state))
        self.assertIn('EXIT_NOT_ZERO', ' '.join(self.review()['unresolved']))

    def test_boolean_exit_is_not_integer_zero(self):
        self.state['worker_exit_status'] = False
        self.session_path.write_bytes(encoded(self.state))
        self.assertEqual(self.review()['evidence_fact_status'], 'NEEDS_MANUAL_REVIEW')

    def test_pending_session_is_not_cleaned(self):
        self.state['state'] = 'RUNNING'
        self.session_path.write_bytes(encoded(self.state))
        self.assertIn('not terminal CLEANED', ' '.join(self.review()['unresolved']))

    def test_nonobject_session_is_manual_not_a_tool_crash(self):
        self.session_path.write_bytes(encoded(['malformed', 'session']))
        self.assertIn('SESSION identity/schema', ' '.join(self.review()['unresolved']))

    def test_nonobject_handoff_is_manual_not_a_tool_crash(self):
        self.handoff_path.write_bytes(encoded(['malformed', 'handoff']))
        self.entry['handoff']['sha256'] = sha(self.handoff_path.read_bytes())
        self.assertIn('JSON object required', ' '.join(self.review()['unresolved']))

    def test_working_source_drift_is_not_hidden_by_matching_publication(self):
        self.method.write_text('changed <- TRUE\n')
        self.assertIn('source drift', ' '.join(self.review()['unresolved']))

    def test_duplicate_fixed_id_rejects_denominator(self):
        self.rows[1]['function_id'] = self.rows[0]['function_id']
        self.write_base()
        self.mapping['base_sha256'] = sha(self.base.read_bytes())
        with self.assertRaisesRegex(ValueError, 'duplicate or absent fixed'):
            self.run_index()

    def test_wrong_base_source_hash_rejects(self):
        self.mapping['base_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'historical base SHA'):
            self.run_index()

    def test_duplicate_mapping_id_rejects(self):
        self.mapping['mappings'].append(dict(self.entry))
        with self.assertRaisesRegex(ValueError, 'mapping ID/denominator duplicate'):
            self.run_index()

    def test_alternative_never_certifies_original(self):
        self.entry.update(route='ALTERNATIVE', adapter_kind='r_stats_lm')
        review = self.review()
        self.assertEqual(review['evidence_fact_status'], 'VERIFIED_EVIDENCE_FACTS_ONLY')
        self.assertFalse(review['original_implementation_certified'])
        self.assertFalse(review['qualification_upgraded'])
        self.entry['route'] = 'ORIGINAL'
        with self.assertRaisesRegex(ValueError, 'alternative cannot certify original'):
            self.run_index()

    def test_report_count_mismatch_requires_review(self):
        self.entry['counts'][0]['expected'] = 4
        del self.entry['counts'][0]['handoff_pointer']
        self.assertIn('report count differs', ' '.join(self.review()['unresolved']))

    def test_report_without_count_context_requires_review(self):
        self.entry['counts'][0]['report_pointer'] = '/missing'
        self.assertEqual(self.review()['evidence_fact_status'], 'NEEDS_MANUAL_REVIEW')

    def test_forged_method_to_sealed_execution_binding_is_refused(self):
        self.entry['sources'][0]['sealed_source_binding'] = {
            'archive': 'proof', 'report': 'report.json', 'report_pointer': '/cases'}
        self.assertIn('not bound to measured report', ' '.join(self.review()['unresolved']))

    def test_accepted_handoff_string_cannot_replace_count_context(self):
        self.handoff['status'] = 'ACCEPTED'
        self.handoff_path.write_bytes(encoded(self.handoff))
        self.entry['handoff']['sha256'] = sha(self.handoff_path.read_bytes())
        self.entry['counts'] = []
        self.assertEqual(self.review()['evidence_fact_status'], 'NEEDS_MANUAL_REVIEW')

    def test_sealed_identity_mismatch_is_not_deployment_proof(self):
        self.entry['identities'] = [{'archive': 'proof', 'report': 'report.json',
                                    'report_pointer': '/cases', 'expected': 'fictional engine',
                                    'label': 'engine revision'}]
        self.assertIn('identity declaration differs', ' '.join(self.review()['unresolved']))

    def test_symlink_member_is_refused(self):
        self.report_path.unlink()
        self.report_path.symlink_to(self.method)
        self.assertIn('symlink', ' '.join(self.review()['unresolved']))

    def test_hardlinked_manifest_is_refused(self):
        os.link(self.manifest_path, self.root / 'manifest-link')
        self.assertIn('non-hardlinked', ' '.join(self.review()['unresolved']))

    def test_hardlinked_member_is_refused(self):
        os.link(self.report_path, self.root / 'report-link')
        self.assertIn('hardlinked', ' '.join(self.review()['unresolved']))

    def test_archive_byte_cap_refuses_before_hashing_members(self):
        with patch.object(index, 'MAX_ARCHIVE_BYTES', 1):
            self.assertIn('total byte limit', ' '.join(self.review()['unresolved']))

    def test_escape_member_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'member path escape'):
            index.relative_member('../outside')

    def test_duplicate_report_ids_do_not_inflate_case_count(self):
        self.assertRaisesRegex(ValueError, 'duplicate or missing report', index.report_count,
                               {'cases': [{'name': 'same'}, {'name': 'same'}]}, self.entry['counts'][0])


if __name__ == '__main__':
    unittest.main()
