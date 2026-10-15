"""Read an exact published baseline before comparing AST in this interpreter.

ast.dump is not a cross-Python-version serialization format. Original source
bytes remain SHA256-pinned; neither missing Git history nor changed originals
may fall back to the current checkout or a newly observed golden AST hash.
"""
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def published_source(path, revision, sha256):
    relative = PurePosixPath(path)
    if (relative.is_absolute() or relative.as_posix() != path or '\\' in path
            or any(part in ('', '.', '..') for part in path.split('/'))
            or not re.fullmatch('[0-9a-f]{40}', revision)
            or not re.fullmatch('[0-9a-f]{64}', sha256)):
        raise ValueError('Exact relative published source identity required')
    result = subprocess.run(['git', '-C', str(ROOT), 'show', revision + ':' + path],
                            capture_output=True, timeout=30)
    if result.returncode or hashlib.sha256(result.stdout).hexdigest() != sha256:
        raise ValueError('Exact published Git source unavailable or changed')
    return result.stdout
