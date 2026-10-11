#!/usr/bin/env python3
"""Produce a byte-bound covariance receipt from four actual container inputs.

This adapter reuses the preparation validator. Unknown provenance is a retained
data status, not a failed scientific task: downstream MVMR can retain coefficients
while suppressing F/Q. It grants no source qualification or scientific approval.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

if 'validator' not in globals():
    import research_mvmr_covariance as validator


def produce(recipe, data, covariance, pack_path, output):
    inputs = [Path(p) for p in (recipe, data, covariance, pack_path)]
    target = Path(output)
    if os.path.lexists(target):
        raise ValueError('output exists; refusing overwrite')
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise ValueError('existing regular output directory required')
    before = [validator.digest(p) for p in inputs]
    if any(p.stat().st_size > 8 * 1024**2 for p in inputs):
        raise ValueError('covariance input exceeds the qualified 8MiB bound')
    if target.resolve() in {p.resolve() for p in inputs}:
        raise ValueError('output aliases an input')
    pack = validator.load_json(pack_path)
    validator.exact_keys(pack, ['schema_version', 'evidence'], 'evidence pack')
    if type(pack['schema_version']) is not int or pack['schema_version'] != 1:
        raise ValueError('unsupported evidence pack schema')
    evidence = pack['evidence']
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError('actual evidence artifacts required')
    supplied = validator.load_json(covariance)
    required = {record['evidence_id'] for record in supplied['pair_provenance']}
    if set(evidence) != required:
        raise ValueError('exact provenance evidence identity set required')
    # Evidence IDs are never interpreted as paths. Temporary names are assigned
    # locally, preventing path traversal even for arbitrary registered labels.
    with tempfile.TemporaryDirectory(prefix='mvmr-covariance-evidence-') as temporary:
        source_paths = {}
        for index, (ident, artifact) in enumerate(evidence.items()):
            validator.exact_keys(artifact, ['sha256', 'content_hex'], 'evidence artifact')
            h, text = artifact['sha256'], artifact['content_hex']
            if (not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h)
                    or not isinstance(text, str) or not re.fullmatch('(?:[0-9a-f]{2})*', text)):
                raise ValueError('complete SHA256 and lowercase even-length hex required')
            b = bytes.fromhex(text)
            if hashlib.sha256(b).hexdigest() != h:
                raise ValueError('actual evidence bytes SHA256 mismatch')
            p = Path(temporary) / str(index)
            with p.open('xb') as stream:
                stream.write(b)
            source_paths[ident] = p
        receipt = validator.validate_covariance(recipe, data, covariance, source_paths)
    if before != [validator.digest(p) for p in inputs]:
        raise ValueError('covariance node input changed during validation')
    contents = (json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
                + '\n').encode()
    fd, name = tempfile.mkstemp(prefix='.mvmr-covariance-', dir=target.parent)
    pending = Path(name)
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    published = False
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        if before != [validator.digest(p) for p in inputs]:
            raise ValueError('covariance node input changed before publication')
        # No clobber even if another writer wins after the initial precheck.
        os.link(pending, target)
        published = True
        os.fsync(directory)
    except BaseException:
        # Remove only our inode if a durability failure follows publication.
        if published and os.path.lexists(target):
            a, b = target.lstat(), pending.lstat()
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                target.unlink()
        raise
    finally:
        pending.unlink()
        os.close(directory)
    return receipt


def main():
    if len(sys.argv) == 6:
        args = sys.argv[1:]
    elif len(sys.argv) == 1:
        args = [os.environ['AUTONOMICS_INPUT' + str(i)] for i in range(4)]
        args.append(os.environ['AUTONOMICS_OUTPUT0'])
    else:
        raise ValueError('four input paths and one output required')
    report = produce(*args)
    # An unresolved receipt is successfully produced. Its retained status tells
    # the method to skip covariance-dependent diagnostics, without blocking IVW.
    print(json.dumps({'scope': 'MVMR_COVARIANCE_BYTES_ONLY', 'status': report['status'],
                      'snp_count': report['snp_count'], 'formal_authorized': False}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('BLOCKED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
