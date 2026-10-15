"""Read-only, bounded reconciliation of immutable historical slots and evidence facts."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


MAX_ARCHIVE_BYTES = 2 * 1024 ** 3
MAX_ARCHIVE_MEMBERS = 10000
MAX_METADATA_BYTES = 16 * 1024 ** 2
LAYERS = ('official', 'interface', 'isolated_dag', 'plan_contract')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('nonfinite JSON value')

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def signature(record):
    return (record.st_dev, record.st_ino, record.st_mode, record.st_nlink,
            record.st_size, record.st_mtime_ns, record.st_ctime_ns)


def checked_path(path):
    path = Path(path).absolute()
    require(not any(part in ('.', '..') for part in path.parts), 'path traversal')
    for parent in reversed([path, *path.parents]):
        require(not parent.is_symlink(), 'symlink path or ancestor')
    return path


def file_fact(path, limit=MAX_METADATA_BYTES, *, collect=False):
    path = checked_path(path)
    named_before = path.lstat()
    require(stat.S_ISREG(named_before.st_mode) and named_before.st_nlink == 1,
            'regular non-hardlinked file required')
    require(0 <= named_before.st_size <= limit, 'file byte limit exceeded')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    checksum = hashlib.sha256()
    size = 0
    chunks = []
    with os.fdopen(descriptor, 'rb') as source:
        before = os.fstat(source.fileno())
        require(signature(before) == signature(named_before), 'source changed before open')
        while chunk := source.read(1024 ** 2):
            size += len(chunk)
            require(size <= limit, 'file grew beyond byte limit')
            checksum.update(chunk)
            if collect:
                chunks.append(chunk)
        after = os.fstat(source.fileno())
    require(signature(before) == signature(after) == signature(path.lstat()) and size == before.st_size,
            'source changed during observation')
    return {'bytes': size, 'sha256': checksum.hexdigest()}, b''.join(chunks) if collect else None


def relative_member(name):
    require(isinstance(name, str) and name and '\\' not in name and
            not any(ord(character) < 32 for character in name), 'invalid member path')
    member = PurePosixPath(name)
    require(not member.is_absolute() and all(part not in ('', '.', '..') for part in name.split('/')),
            'member path escape')
    return member


def archive_members(root):
    pending = [checked_path(root)]
    result = set()
    visited = 0
    while pending:
        directory = pending.pop()
        require(stat.S_ISDIR(directory.lstat().st_mode), 'regular archive directory required')
        with os.scandir(directory) as entries:
            for entry in entries:
                visited += 1
                require(visited <= MAX_ARCHIVE_MEMBERS, 'archive traversal member limit exceeded')
                record = entry.stat(follow_symlinks=False)
                require(not stat.S_ISLNK(record.st_mode), 'archive symlink member')
                path = Path(entry.path)
                if stat.S_ISDIR(record.st_mode):
                    pending.append(path)
                else:
                    require(stat.S_ISREG(record.st_mode) and record.st_nlink == 1,
                            'archive special or hardlinked member')
                    result.add(path.relative_to(root).as_posix())
    return result


def verify_archive(archives, session, expected_seal):
    require(re.fullmatch(r'[0-9a-f]{32}', session) is not None, 'invalid session ID')
    require(re.fullmatch(r'[0-9a-f]{64}', expected_seal) is not None, 'invalid manifest SHA256')
    directory = checked_path(Path(archives) / session)
    session_fact, session_raw = file_fact(directory / 'SESSION.json', collect=True)
    state = strict_json(session_raw)
    require(isinstance(state, dict) and state.get('session') == session and
            state.get('schema') == 'TECHNICAL_VALIDATION_SESSION_V1',
            'SESSION identity/schema differs')
    require(state.get('state') == 'CLEANED', 'session not terminal CLEANED')
    require(state.get('manifest_sha256') == expected_seal, 'SESSION seal differs')
    artifact_root = directory / 'artifacts'
    manifest_fact, manifest_raw = file_fact(artifact_root / 'MANIFEST.json', collect=True)
    require(manifest_fact['sha256'] == expected_seal, 'archive manifest seal differs')
    manifest = strict_json(manifest_raw)
    require(isinstance(manifest, dict) and manifest.get('session') == session and
            manifest.get('schema') == 'TECHNICAL_VALIDATION_SESSION_V1',
            'archive manifest identity/schema differs')
    members = manifest.get('files')
    require(isinstance(members, dict) and 0 < len(members) <= MAX_ARCHIVE_MEMBERS,
            'archive declared member limit/schema')
    declared_bytes = 0
    for name, identity in members.items():
        relative_member(name)
        require(name != 'MANIFEST.json' and isinstance(identity, dict) and
                set(identity) == {'bytes', 'sha256'} and type(identity['bytes']) is int and
                identity['bytes'] >= 0 and isinstance(identity['sha256'], str) and
                re.fullmatch(r'[0-9a-f]{64}', identity['sha256']) is not None,
                'invalid declared member identity')
        declared_bytes += identity['bytes']
    require(declared_bytes <= MAX_ARCHIVE_BYTES, 'archive total byte limit exceeded')
    require(archive_members(artifact_root) == set(members) | {'MANIFEST.json'}, 'archive membership differs')
    for name, identity in members.items():
        actual, _ = file_fact(artifact_root / name, limit=identity['bytes'])
        require(actual == identity, 'archive member content differs: ' + name)
    require(file_fact(directory / 'SESSION.json')[0] == session_fact and
            file_fact(artifact_root / 'MANIFEST.json')[0] == manifest_fact,
            'archive metadata changed during observation')
    worker = state.get('worker_exit_status')
    return {'session': session, 'manifest_sha256': expected_seal,
            'session_json_sha256': session_fact['sha256'], 'state': state['state'],
            'worker_exit_status': worker, 'positive_worker_exit_verified': type(worker) is int and worker == 0,
            'files': len(members), 'bytes': declared_bytes, 'all_members_rehashed': True,
            'status': 'ARCHIVE_CONTENT_FACTS_VERIFIED_NOT_WORKER_SUCCESS' if type(worker) is not int or worker != 0
                      else 'ARCHIVE_CONTENT_AND_ZERO_EXIT_FACTS_VERIFIED',
            'artifact_root': str(artifact_root), 'member_identities': members}


def pointer(value, path):
    require(isinstance(path, str) and (not path or path.startswith('/')), 'invalid JSON pointer')
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def report_count(report, check):
    value = pointer(report, check['report_pointer'])
    if check['operation'] == 'value':
        require(type(value) is int and value >= 0, 'reported count must be a nonnegative integer')
        return value
    require(isinstance(value, list), 'count context must be an actual report list')
    selected = []
    for row in value:
        require(isinstance(row, dict), 'case count requires object rows')
        if all(type(row.get(key)) is type(expected) and row.get(key) == expected
               for key, expected in check.get('where', {}).items()):
            selected.append(row)
    identities = [row[check['case_id_key']] for row in selected]
    require(all(isinstance(name, str) and name for name in identities) and len(set(identities)) == len(identities),
            'duplicate or missing report case IDs')
    if check['operation'] == 'count':
        return len(selected)
    values = [row[check['field']] for row in selected]
    if check['operation'] == 'sum_lengths':
        require(all(isinstance(item, list) for item in values), 'list sum context differs')
        return sum(map(len, values))
    require(check['operation'] == 'sum' and all(type(item) is int and item >= 0 for item in values),
            'integer sum context differs')
    return sum(values)


def git_file_fact(repository, revision, name):
    require(re.fullmatch(r'[0-9a-f]{40}', revision) is not None, 'full Git revision required')
    relative_member(name)
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    command = ['git', '-C', str(repository), 'show', revision + ':' + name]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment) as process:
        checksum = hashlib.sha256()
        size = 0
        while chunk := process.stdout.read(1024 ** 2):
            size += len(chunk)
            if size > MAX_METADATA_BYTES:
                process.kill()
                raise ValueError('Git source object byte limit exceeded')
            checksum.update(chunk)
        require(process.wait() == 0, 'declared Git source object unavailable')
    mode = subprocess.check_output(['git', '-C', str(repository), 'ls-tree', revision, '--', name],
                                   env=environment, stderr=subprocess.DEVNULL).decode().split()[0]
    require(mode in ('100644', '100755'), 'Git source must be an ordinary blob')
    return {'bytes': size, 'sha256': checksum.hexdigest()}


def observe_mapping(entry, archives, cache):
    unresolved = []
    observed = {'mapping_id': entry['mapping_id'], 'route': entry['route'], 'adapter_kind': entry['adapter_kind'],
                'qualification_upgraded': False, 'original_implementation_certified': False,
                'deployment': 'NOT_GRANTED', 'research': 'NOT_GRANTED', 'layers': {},
                'archives': [], 'counts': [], 'identity_checks': [], 'sources': [], 'unresolved': unresolved}
    try:
        require(entry['route'] in ('ORIGINAL', 'ALTERNATIVE'), 'explicit ORIGINAL/ALTERNATIVE route required')
        handoff_fact, raw = file_fact(entry['handoff']['path'], collect=True)
        require(handoff_fact['sha256'] == entry['handoff']['sha256'], 'handoff source SHA differs')
        handoff = strict_json(raw)
        require(isinstance(handoff, dict), 'handoff JSON object required')
        observed['handoff'] = {'path': entry['handoff']['path'], **handoff_fact}
        require(entry['archives'] and entry.get('counts') and entry.get('sources'),
                'archive, count context and source observations required')
        archive_by_id = {}
        for reference in entry['archives']:
            session = pointer(handoff, reference['session_pointer'])
            seal = pointer(handoff, reference['seal_pointer'])
            key = (session, seal)
            if key not in cache:
                try:
                    cache[key] = verify_archive(archives, session, seal)
                except (ValueError, OSError, KeyError, TypeError) as error:
                    cache[key] = {'session': session, 'manifest_sha256': seal, 'error': str(error)}
            actual = cache[key]
            archive_by_id[reference['id']] = actual
            observed['archives'].append({key: value for key, value in actual.items()
                                         if key not in ('member_identities', 'artifact_root')})
            require('error' not in actual, 'archive verification refused: ' + actual.get('error', ''))
            if not actual['positive_worker_exit_verified']:
                unresolved.append('ARCHIVED_WORKER_EXIT_NOT_ZERO:' + session)
        reports = {}

        def sealed_report(archive_id, member):
            archive = archive_by_id[archive_id]
            relative_member(member)
            require(member in archive['member_identities'], 'report not sealed archive member')
            key = (archive_id, member)
            if key not in reports:
                fact, report_raw = file_fact(Path(archive['artifact_root']) / member, collect=True)
                require(fact == archive['member_identities'][member], 'sealed report changed')
                reports[key] = strict_json(report_raw)
            return reports[key]

        for check in entry.get('counts', []):
            actual = report_count(sealed_report(check['archive'], check['report']), check)
            expected = pointer(handoff, check['handoff_pointer']) if 'handoff_pointer' in check else check['expected']
            require(type(expected) is int and actual == expected, 'report count differs: ' + check['label'])
            observed['counts'].append({'label': check['label'], 'actual': actual, 'expected': expected,
                                       'report': check['report'], 'operation': check['operation'],
                                       'scope': check['scope'],
                                       'independently_recounted_report_cases': check['operation'] != 'value'})
        for check in entry.get('identities', []):
            actual = pointer(sealed_report(check['archive'], check['report']), check['report_pointer'])
            expected = pointer(handoff, check['handoff_pointer']) if 'handoff_pointer' in check else check['expected']
            require(type(actual) is type(expected) and actual == expected, 'sealed identity declaration differs: ' + check['label'])
            observed['identity_checks'].append({'label': check['label'], 'actual': actual,
                'scope': 'SEALED_REPORT_DECLARATION_NOT_FRESH_BINARY_OR_DAEMON_MEASUREMENT'})
        for source in entry.get('sources', []):
            revision = pointer(handoff, source['revision_pointer'])
            require(revision == source['revision'], 'declared publication revision differs')
            current, _ = file_fact(Path(source['repository']) / source['relative_path'])
            original = git_file_fact(source['repository'], revision, source['relative_path'])
            require(current == original and current['sha256'] == source['sha256'], 'method source drift or Git identity differs')
            binding = source.get('sealed_source_binding')
            if binding:
                declared = pointer(sealed_report(binding['archive'], binding['report']), binding['report_pointer'])
                require(declared == current['sha256'], 'source hash not bound to measured report')
            observed['sources'].append({'relative_path': source['relative_path'], 'revision': revision, **current,
                                         'working_bytes_match_git': True, 'remote_publication_reverified': False,
                                         'sealed_execution_source_binding': 'DECLARED_HASH_MATCHED' if binding else 'NEEDS_MANUAL_REVIEW',
                                         'scope': 'DECLARED_FILE_ONLY_NOT_TRANSITIVE_RUNTIME_OR_IMAGE'})
        for layer in LAYERS:
            declaration = entry['layers'][layer]
            for link in declaration['links']:
                archive = archive_by_id[link['archive']]
                relative_member(link['member'])
                require(link['member'] in archive['member_identities'], 'layer link not a sealed member')
            observed['layers'][layer] = {'links': declaration['links'], 'scope': declaration['scope'],
                                         'status': 'LINKED_FACTS_NOT_SCIENTIFIC_CERTIFICATION'}
            if declaration.get('manual_review', True):
                observed['layers'][layer]['status'] = 'NEEDS_MANUAL_REVIEW'
        require(file_fact(entry['handoff']['path'])[0] == handoff_fact, 'handoff changed')
    except (ValueError, OSError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
        unresolved.append(str(error))
    observed['evidence_fact_status'] = 'NEEDS_MANUAL_REVIEW' if unresolved else 'VERIFIED_EVIDENCE_FACTS_ONLY'
    observed['disposition'] = 'NEEDS_MANUAL_REVIEW'
    return observed


def reconcile(base, mapping_path, archives):
    base_fact, base_raw = file_fact(base, collect=True)
    mapping_fact, mapping_raw = file_fact(mapping_path, collect=True)
    mapping = strict_json(mapping_raw)
    require(isinstance(mapping, dict) and mapping.get('schema') == 'AB_EVIDENCE_RECONCILIATION_MAPPING_V1',
            'mapping schema differs')
    require(base_fact['sha256'] == mapping['base_sha256'], 'historical base SHA differs')
    reader = csv.DictReader(io.StringIO(base_raw.decode('utf-8-sig'), newline=''), delimiter='\t')
    require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames), 'base columns differ')
    rows = list(reader)
    require(len(rows) == mapping['expected_rows'] == 120 and
            all(None not in row and all(value is not None for value in row.values()) for row in rows),
            'fixed 120-row denominator/schema required')
    identifiers = [row['function_id'] for row in rows]
    require(all(identifier and identifier.startswith('FUNC_') for identifier in identifiers) and
            len(set(identifiers)) == 120, 'duplicate or absent fixed function ID')
    entries = mapping['mappings']
    require(1 <= len(entries) <= 6 and len({entry['function_id'] for entry in entries}) == len(entries) and
            len({entry['mapping_id'] for entry in entries}) == len(entries), 'mapping ID/denominator duplicate')
    by_id = {row['function_id']: row for row in rows}
    for entry in entries:
        require(entry['function_id'] in by_id and by_id[entry['function_id']]['original_kind'] == entry['original_kind'],
                'mapping original identity differs')
        require(entry['route'] != 'ORIGINAL' or entry['adapter_kind'] == entry['original_kind'],
                'alternative cannot certify original kind')
    indexed = {entry['function_id']: entry for entry in entries}
    cache = {}
    reconciled = []
    for row in rows:
        item = {'function_id': row['function_id'], 'historical_row': row,
                'historical_row_sha256': hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'historical_status_unchanged': row['original_current_official'],
                'deployment': 'NOT_GRANTED', 'research': 'NOT_GRANTED'}
        item['current_review'] = observe_mapping(indexed[row['function_id']], archives, cache) if row['function_id'] in indexed else {
            'disposition': 'INHERITED_HISTORICAL_NOT_REVERIFIED_THIS_ROUND', 'qualification_upgraded': False}
        reconciled.append(item)
    adapters = mapping['minimum_AB_adapters']
    require(isinstance(adapters, list) and len(adapters) == 5 and len({row['kind'] for row in adapters}) == 5,
            'five minimum A/B adapter kinds must remain separate')
    require(file_fact(base)[0] == base_fact and file_fact(mapping_path)[0] == mapping_fact, 'index inputs changed')
    return {'schema': 'AB_EVIDENCE_RECONCILIATION_V1', 'base': {'path': str(base), **base_fact, 'rows': 120,
                'ordered_ids_sha256': hashlib.sha256('\n'.join(identifiers).encode()).hexdigest()},
            'mapping': {'path': str(mapping_path), **mapping_fact}, 'slots': reconciled,
            'minimum_AB_adapters_outside_original_denominator': adapters,
            'additional_routes_outside_original_denominator': mapping.get('additional_routes', []),
            'summary': {'fixed_original_slots': 120, 'mapped_slots': len(entries),
                'inherited_not_reverified_slots': 120 - len(entries),
                'mapped_verified_fact_packets': sum(row['current_review'].get('evidence_fact_status') == 'VERIFIED_EVIDENCE_FACTS_ONLY' for row in reconciled),
                'new_original_slots': 0, 'scientific_certificates_issued': 0},
            'evidence_is_not_independent_method_reexecution': True, 'production_state_observed': False,
            'filesystem_observation_is_not_an_atomic_snapshot': True,
            'scientific_authorization_granted': False, 'g0_granted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--mapping', required=True, type=Path)
    parser.add_argument('--archives', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    require(permanent is not None, 'managed permanent evidence directory required')
    output = checked_path(arguments.output or Path(permanent) / 'ab-evidence-reconciliation.json')
    require(output.is_relative_to(checked_path(permanent)) and not output.exists() and output.parent.is_dir(),
            'new output must remain under managed permanent evidence')
    implementation_fact = file_fact(__file__)[0]
    result = reconcile(arguments.base, arguments.mapping, arguments.archives)
    require(file_fact(__file__)[0] == implementation_fact, 'reconciler source changed')
    result['implementation'] = {'path': __file__, **implementation_fact}
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
