import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_opentargets_direct_files as proof
from tools import opentargets_direct_reader as reader


def seal(root, session, files, exit_status=0):
    archive = root / session
    artifacts = archive / 'artifacts'
    artifacts.mkdir(parents=True)
    entries = {}
    for name, body in files.items():
        path = artifacts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        entries[name] = dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    body = json.dumps(dict(session=session, files=entries)).encode()
    (artifacts / 'MANIFEST.json').write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    (archive / 'SESSION.json').write_text(json.dumps(dict(session=session, state='CLEANED',
        worker_exit_status=exit_status, manifest_sha256=digest)))
    return archive, digest


def rows():
    records = []
    for dataset, count in proof.SELECTED.items():
        for position in range(count):
            name = f'part-{position:05d}.parquet'
            records.append(dict(dataset=dataset, url=proof.BASE + dataset + '/' + name,
                bytes=12, sha256=hashlib.sha256(b'PAR1dataPAR1').hexdigest(),
                relative_path='permanent/reference/files/' + dataset + '/' + name,
                source_session='a' * 32, source_manifest_sha256='1' * 64,
                etag='"fixed"', last_modified='Mon, 07 Sep 2026 15:56:27 GMT'))
    return records


def index(records):
    return dict(schema=proof.INDEX_SCHEMA, status=proof.INDEX_STATUS,
        release='26.09', total_bytes=sum(row['bytes'] for row in records),
        files=records, g0_granted=False)


class DirectFileAuditTests(unittest.TestCase):
    def test_complete_inventory_requires_all_unique_classified_official_partitions(self):
        records = rows()
        with patch.object(proof, 'TOTAL', 216):
            self.assertEqual(proof.inventory(index(records)), records)
            for field, value in [('relative_path', 'retained/reference/files/target/part.parquet'),
                    ('relative_path', 'permanent/reference/files/target/../part.parquet'),
                    ('source_session', '../foreign'), ('source_manifest_sha256', 'main'),
                    ('url', 'https://example.invalid/data.parquet'), ('bytes', True)]:
                bad = copy.deepcopy(records)
                bad[0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                    proof.inventory(index(bad))
            duplicate = copy.deepcopy(records)
            duplicate[1] = duplicate[0]
            with self.assertRaises(RuntimeError):
                proof.inventory(index(duplicate))
            with self.assertRaises(RuntimeError):
                proof.inventory(index(records[:-1]))

    def test_unknown_worker_exit_preserves_sealed_file_facts_without_inventing_success(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, digest = seal(Path(directory), 'a' * 32, {'permanent/file': b'toy'}, None)
            evidence = proof.sealed_archive(archive, digest)
            self.assertIsNone(evidence['session']['worker_exit_status'])
            with self.assertRaises(RuntimeError):
                proof.sealed_archive(archive, digest, successful=True)
            for status in [False, None, 1]:
                path = archive / 'SESSION.json'
                session = json.loads(path.read_text())
                session['worker_exit_status'] = status
                path.write_text(json.dumps(session))
                with self.assertRaises(RuntimeError):
                    proof.sealed_archive(archive, digest, successful=True)

    def test_all_archive_members_are_hashed_and_extra_partial_files_are_rejected(self):
        for corruption in ['changed_member', 'extra_partial', 'missing_member', 'symlink_member']:
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                archive, digest = seal(Path(directory), 'a' * 32, {'permanent/file': b'toy'})
                path = archive / 'artifacts/permanent/file'
                if corruption == 'changed_member':
                    path.write_bytes(b'bad')
                elif corruption == 'extra_partial':
                    (path.parent / 'unlisted.partial').write_bytes(b'partial')
                elif corruption == 'missing_member':
                    path.unlink()
                else:
                    path.unlink()
                    path.symlink_to('/dev/null')
                with self.assertRaises(RuntimeError):
                    proof.sealed_archive(archive, digest)

    def test_absolute_traversal_unclassified_and_aliased_archive_paths_are_refused(self):
        for name in ['/absolute', 'permanent/../file', 'permanent//file', 'scratch/file', 'permanent']:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                proof.member_path(name)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, digest = seal(root, 'a' * 32, {'permanent/file': b'toy'})
            (root / 'alias').symlink_to(archive, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                proof.sealed_archive(root / 'alias', digest)

    def fixture(self, root, mutate=None, index_exit=0):
        records = rows()
        files = [{'permanent/reference/files/' + row['dataset'] + '/' + Path(row['relative_path']).name:
            b'PAR1dataPAR1' for row in records[:10]},
            {'permanent/reference/files/' + row['dataset'] + '/' + Path(row['relative_path']).name:
            b'PAR1dataPAR1' for row in records[10:]}]
        for part, session in enumerate(['a' * 32, 'b' * 32]):
            subset = records[:10] if part == 0 else records[10:]
            receipts = [dict(row, relative_path=row['relative_path'].removeprefix('permanent/reference/'),
                sha256_is_measured_not_author_published=True) for row in subset]
            files[part]['permanent/reference/completed-files.json'] = json.dumps(receipts).encode()
            archive, digest = seal(root, session, files[part], None if part == 0 else 0)
            for row in subset:
                row.update(source_session=session, source_manifest_sha256=digest)
        metadata = {}
        for dataset in proof.SELECTED:
            metadata['permanent/opentargets-bulk-metadata/' + dataset + '.resource.json'] = json.dumps(
                dict(dataset=dataset, files=[{key: row[key] for key in ['url', 'bytes', 'etag', 'last_modified']}
                    for row in records if row['dataset'] == dataset])).encode()
        metadata_archive, metadata_seal = seal(root, 'c' * 32, metadata)
        if mutate:
            mutate(records)
        name = 'permanent/opentargets-direct-index/verification.json'
        archive, digest = seal(root, 'd' * 32, {name: json.dumps(index(records)).encode()}, index_exit)
        return archive, digest, name, metadata_archive, metadata_seal

    def test_complete_multi_archive_index_binds_every_file_without_copy_or_worker_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, digest, member, metadata, metadata_seal = self.fixture(root)
            with patch.multiple(proof, TOTAL=216, SOURCE_SESSION=metadata.name, SOURCE_SEAL=metadata_seal):
                records, sources = proof.source_index(root, archive, digest, member)
            self.assertEqual(len(records), 18)
            self.assertEqual(len(sources), 3)
            self.assertIsNone(sources['a' * 32]['session']['worker_exit_status'])
            self.assertEqual(sum(1 for path in root.rglob('*.parquet')), 18)

    def test_index_cannot_change_metadata_or_source_archive_receipts(self):
        mutations = [lambda records: records[0].update(etag='"changed"'),
            lambda records: records[0].update(last_modified='changed'),
            lambda records: records[0].update(source_manifest_sha256='2' * 64),
            lambda records: records[0].update(sha256='3' * 64)]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive, digest, member, metadata, metadata_seal = self.fixture(root, mutation)
                with patch.multiple(proof, TOTAL=216, SOURCE_SESSION=metadata.name, SOURCE_SEAL=metadata_seal):
                    with self.assertRaises(RuntimeError):
                        proof.source_index(root, archive, digest, member)

    def test_index_itself_requires_a_successful_terminal_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, digest, member, metadata, metadata_seal = self.fixture(root, index_exit=None)
            with patch.multiple(proof, TOTAL=216, SOURCE_SESSION=metadata.name, SOURCE_SEAL=metadata_seal):
                with self.assertRaises(RuntimeError):
                    proof.source_index(root, archive, digest, member)

    def test_complete_file_facts_require_the_original_sealed_response_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, digest, member, metadata, metadata_seal = self.fixture(root)
            records = json.loads((archive / 'artifacts' / member).read_text())['files']
            source = root / ('a' * 32)
            manifest = json.loads((source / 'artifacts/MANIFEST.json').read_text())
            payloads = {name: (source / 'artifacts' / name).read_bytes() for name in manifest['files']}
            receipts_name = 'permanent/reference/completed-files.json'
            receipts = json.loads(payloads[receipts_name])
            receipts[0]['sha256_is_measured_not_author_published'] = False
            payloads[receipts_name] = json.dumps(receipts).encode()
            alternate, alternate_seal = seal(root, 'e' * 32, payloads, None)
            for row in records[:10]:
                row.update(source_session=alternate.name, source_manifest_sha256=alternate_seal)
            changed, changed_seal = seal(root, 'f' * 32, {member: json.dumps(index(records)).encode()})
            with patch.multiple(proof, TOTAL=216, SOURCE_SESSION=metadata.name, SOURCE_SEAL=metadata_seal):
                with self.assertRaises(RuntimeError):
                    proof.source_index(root, changed, changed_seal, member)

    def test_control_retains_null_novelty_and_refuses_duplicates_or_missing_annotations(self):
        control = dict(diseaseId=reader.CONTROL, targetId='ENSG1', associationScore=0.5, currentNovelty=None)
        targets = {'ENSG1': dict(id='ENSG1', approvedSymbol='SYMBOL', approvedName='gene', biotype='protein_coding')}
        diseases = [dict(id=reader.CONTROL, name='control disease')]
        self.assertEqual(reader.check_control([control], targets, diseases), 1)
        self.assertIsNone(control['currentNovelty'])
        for rows_value, targets_value, diseases_value in [([control, control], targets, diseases),
                ([control], {}, diseases), ([control], targets, diseases * 2), ([], {}, diseases)]:
            with self.assertRaises(RuntimeError):
                reader.check_control(rows_value, targets_value, diseases_value)
        for field, value in [('associationScore', True), ('associationScore', float('nan')),
                ('associationScore', -0.1), ('currentNovelty', float('inf')), ('currentNovelty', 1.1)]:
            bad = dict(control, **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                reader.check_control([bad], targets, diseases)

    def test_reader_is_offline_pinned_and_uses_explicit_nonroot_uid_and_readonly_sources(self):
        sources = {'a' * 32: dict(archive=Path('/sealed') / ('a' * 32))}
        with patch.object(proof.os, 'getuid', return_value=123), patch.object(proof.os, 'getgid', return_value=456):
            command = proof.reader_command(Path('/work-output'), sources)
        for value in ['--network=none', '--pull=never', '--read-only', '--userns=keep-id', '--user=123:456', proof.READER_IMAGE]:
            self.assertIn(value, command)
        self.assertIn('/sealed/' + 'a' * 32 + '/artifacts:/sources/' + 'a' * 32 + ':ro', command)
        self.assertEqual(proof.READER_IMAGE.split('@sha256:')[1], 'e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20')

    def test_api_string_contract_preserves_and_reports_blank_annotations_without_filling(self):
        control = dict(diseaseId=reader.CONTROL, targetId='ENSG1', associationScore=0.5, currentNovelty=None)
        targets = {'ENSG1': dict(id='ENSG1', approvedSymbol='SYMBOL', approvedName='  ', biotype='')}
        diseases = [dict(id=reader.CONTROL, name='')]
        before = copy.deepcopy((targets, diseases))
        self.assertEqual(reader.check_control([control], targets, diseases), 1)
        quality = reader.annotation_quality(targets, diseases)
        self.assertEqual(len(quality), 3)
        self.assertEqual({row['state'] for row in quality}, {'EMPTY_STRING', 'WHITESPACE_ONLY'})
        self.assertEqual((targets, diseases), before)
        for field, value in [('approvedSymbol', None), ('approvedName', 123), ('biotype', False)]:
            bad = copy.deepcopy(targets)
            bad['ENSG1'][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                reader.check_control([control], bad, diseases)
        for value in [None, [], 123]:
            with self.subTest(disease_name=value), self.assertRaises(RuntimeError):
                reader.check_control([control], targets, [dict(id=reader.CONTROL, name=value)])

    def test_api_comparison_keeps_repeated_rows_and_reports_missing_members_and_null_patterns(self):
        bulk = [dict(targetId=identity, associationScore=0.5, currentNovelty=None) for identity in ['A', 'B']]
        targets = {identity: dict(id=identity, approvedSymbol=identity, approvedName='', biotype='') for identity in ['A', 'B']}
        api = [dict(target=targets['A'], score=0.5, novelty=None), dict(target=targets['A'], score=0.4, novelty=0.2)]
        before = copy.deepcopy((bulk, targets, api))
        summary, comparisons = reader.compare_api_rows(bulk, targets, api)
        self.assertEqual(summary['api_rows'], 2)
        self.assertEqual(summary['api_unique_targets'], 1)
        self.assertEqual(summary['api_duplicate_occurrences'], 1)
        self.assertEqual(summary['bulk_target_ids_missing_from_api'], ['B'])
        self.assertEqual(summary['novelty_null_patterns'], {'BOTH_NULL': 1, 'BULK_NULL_API_FINITE': 1})
        self.assertEqual(summary['score_exact_rows'], 1)
        self.assertEqual([row['api_row'] for row in comparisons], [0, 1])
        self.assertEqual((bulk, targets, api), before)
        with self.assertRaises(RuntimeError):
            reader.compare_api_rows(bulk + [bulk[0]], targets, api)

    def test_api_comparison_does_not_turn_nonfinite_scores_or_null_annotations_into_matches(self):
        bulk = [dict(targetId='A', associationScore=0.5, currentNovelty=0.2)]
        targets = {'A': dict(id='A', approvedSymbol='A', approvedName='', biotype='')}
        for score, novelty, name in [(float('nan'), .2, ''), (True, .2, ''), (.5, float('inf'), ''), (.5, .2, None)]:
            api = [dict(target=dict(targets['A'], approvedName=name), score=score, novelty=novelty)]
            with self.subTest(score=score, novelty=novelty, name=name), self.assertRaises(RuntimeError):
                reader.compare_api_rows(bulk, targets, api)

    def test_duplicate_keys_nonfinite_json_and_symlinked_json_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'evidence.json'
            for body in ['{"status":1,"status":2}', '{"score":NaN}']:
                path.write_text(body)
                with self.assertRaises(RuntimeError):
                    proof.read_json(path)
            (root / 'link').symlink_to(path)
            with self.assertRaises(RuntimeError):
                proof.read_json(root / 'link')


if __name__ == '__main__':
    unittest.main()
