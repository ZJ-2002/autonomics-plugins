"""Assemble only the individually hash-qualified cis component bytes."""
import argparse
import hashlib
import json
from pathlib import Path

HEADER = b'# Generated from individually qualified component bytes; see component-source.json.\n\n'
COMPONENTS = ['research_cis_ld.R', 'research_cis_mr.R']


def assembled(family):
    family = Path(family)
    lock = json.loads((family / 'component-source.json').read_bytes())
    if (lock.get('schema_version') != 1 or lock.get('scientific_authorization') is not False or
            lock.get('assembly_order') != COMPONENTS + ['entry.R'] or
            set(lock.get('component_files', {})) != set(COMPONENTS)):
        raise ValueError('Complete explicit unapproved component source lock required')
    parts = []
    for name in COMPONENTS:
        path = family / 'components' / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Actual regular component bytes required')
        raw = path.read_bytes()
        if lock['component_files'][name] != {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('Qualified component source identity differs')
        parts.append(raw)
    entry = family / 'entry.R'
    if entry.is_symlink() or not entry.is_file():
        raise ValueError('Actual entry source required')
    return HEADER + b'\n'.join(parts) + entry.read_bytes()


def check(family):
    family = Path(family)
    expected = assembled(family)
    path = family / 'scripts/cis_mr.R'
    if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
        raise ValueError('Runnable cis adapter differs from qualified components and entry')
    return hashlib.sha256(expected).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', type=Path, default=Path(__file__).resolve().parents[1] / 'research-adapters/cis-mr-declared')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(check(args.family))
    else:
        (args.family / 'scripts/cis_mr.R').write_bytes(assembled(args.family))
        print(check(args.family))
