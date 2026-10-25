import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "research-adapters/cachexia-lcmm/scripts/lcmm.R"
CASES = ROOT / "tests/test_lcmm_bind_precision.py"
GUARDS = ROOT / "tests/test_lcmm_publication_binding.py"
OLD_SHA = "92bedf32d5c48070df0354b0ee08c0d0f64e0fcb7cf44d7abd0da2945a0d43d8"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(module, test_name=None):
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(test_name, module) if test_name else unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return result, stream.getvalue()


def main():
    permanent = Path(os.environ["AUTONOMICS_VALIDATION_PERMANENT"]) / "lcmm-bind-and-audit-precision"
    permanent.mkdir(mode=0o700)
    current = PROGRAM.read_bytes()
    repaired = b'jsonlite::write_json(request, Sys.getenv("AUTONOMICS_OUTPUT0"), auto_unbox = TRUE, pretty = TRUE, digits = 17, null = "null")'
    assert current.count(repaired) == 1
    audit_repair = b'request_json = jsonlite::toJSON(request, auto_unbox = TRUE, digits = 17, null = "null")'
    assert current.count(audit_repair) == 1
    old = current.replace(audit_repair, audit_repair.replace(b"digits = 17", b"digits = NA"), 1)
    binder_only_sha = '15e7a0516716420198fa80652777696040d422d0437c45dfaa9dd6d51ba2e1e0'
    assert hashlib.sha256(old).hexdigest() == binder_only_sha
    original_bytes = old.replace(repaired, repaired.replace(b"digits = 17", b"digits = NA"), 1)
    assert hashlib.sha256(original_bytes).hexdigest() == OLD_SHA
    with tempfile.TemporaryDirectory(prefix="lcmm-bind-original-") as directory:
        original = Path(directory) / "lcmm.R"
        original.write_bytes(old)
        old_cases = load(CASES, "old_lcmm_bind")
        old_cases.PROGRAM = original
        before, log = execute(old_cases, 'LcmmBindPrecisionTests.test_audit_request_json_preserves_numeric_and_structural_semantics')
        assert before.testsRun == 1 and len(before.failures) == 1 and not before.errors and not before.skipped
        (permanent / "before-reconstructed-source.log").write_text(log)
    after, log = execute(load(CASES, "current_lcmm_bind"))
    assert after.testsRun == 4 and after.wasSuccessful() and not after.skipped
    (permanent / "after.log").write_text(log)
    guards, log = execute(load(GUARDS, "current_lcmm_guards"))
    assert guards.testsRun == 5 and guards.wasSuccessful() and not guards.skipped
    (permanent / "guards.log").write_text(log)
    assert PROGRAM.read_bytes() == current
    files = (PROGRAM, CASES, GUARDS, Path(__file__), ROOT / "tools/prove_lcmm_combined_pipeline.py")
    verification = {
        "schema": "LCMM_BIND_AND_REQUEST_AUDIT_PRECISION_INCREMENT_V2",
        "before_byte_identical_reconstructed_sha256": binder_only_sha,
        "original_before_both_repairs_sha256": OLD_SHA,
        "current_dispatcher_sha256": hashlib.sha256(current).hexdigest(),
        "before_cases": 1, "before_failures": 1, "after_cases": 4, "after_failures": 0,
        "adjacent_unit_guards": 5, "guard_failures": 0,
        "source_files": {str(filename.relative_to(ROOT)): hashlib.sha256(filename.read_bytes()).hexdigest() for filename in files},
        "scope": "ACTUAL_BIND_BLOCK_AND_REQUEST_AUDIT_AST_NOT_FULL_LCMM_CONTAINER_ENTRY",
        "source_hash_replacement_only_semantics_checked": True,
        "source_input_hashes_unchanged": True,
        "source_stable_during_execution": True,
        "live_credentials_read": False, "network_requests": 0, "lcmm_fits": 0,
        "production_modified": False, "scientific_release_granted": False, "g0_granted": False,
    }
    (permanent / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps({"state": "PASS", "cases": 9, "prior_failures_reproduced": 1}))


if __name__ == "__main__":
    main()
