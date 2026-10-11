#!/usr/bin/env python3
"""Bundle the byte-exact shared validator and covariance node; check is read-only."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render():
    validation = (ROOT / 'scripts/research_mvmr_covariance.py').read_text()
    entry = (ROOT / 'scripts/research_mvmr_covariance_node.py').read_text()
    return ('#!/usr/bin/env python3\nimport types\n'
            'validator = types.ModuleType("research_mvmr_covariance")\n'
            'exec(compile(bytes.fromhex("' + validation.encode().hex()
            + '").decode("utf-8"), "bundled-covariance-validator", "exec"), '
            'validator.__dict__)\n' + entry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'study_plugins/mvmr-covariance-contract/scripts/run-covariance.py'
    if args.check:
        if target.is_symlink() or not target.is_file() or target.read_bytes() != render().encode():
            raise SystemExit('covariance wrapper absent or stale')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render())
        target.chmod(0o755)
