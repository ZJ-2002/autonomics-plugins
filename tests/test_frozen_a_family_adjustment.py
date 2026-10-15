"""Dependency-free adapter contracts; explicit R toy mode requires a managed session."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prove_frozen_a_family_contract import COUNTS, SOURCES

FAMILY = ROOT / 'research-adapters/frozen-a-family-adjustment'
DEFINITION = b'adjust_full <- function(p,method="BH") p.adjust(ifelse(is.finite(p),p,1),method=method)\n'
DEFINITION_SHA = '2d110232f5f1c3097d763686df1ecec5212e3ca18b4b226ac8f5562c388813fd'
INPUTS = ['vectors.tsv', 'assembly.tsv', 'assembly-receipt.json', 'g0_v432_methods.R']
OUTPUTS = ['adjusted.tsv', 'adjustment.RDS', 'adjustment-receipt.json', 'adjustment.log']
RECEIPT_FIELDS = {'schema', 'scope', 'scenario', 'input_sha256', 'output_sha256', 'R_version',
    'stats_version', 'adjustment_definition_sha256', 'vector_count', 'rows', 'family_counts',
    'official_function', 'invocation', 'missing_for_adjustment', 'MR_estimates_computed',
    'scientific_authorization_granted', 'g0_granted'}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_table(path, names, rows):
    with path.open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=names, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def fixture(root, methods, *, scenario='INTERIOR', ledger=False):
    root.mkdir()
    inputs, outputs = root / 'inputs', root / 'outputs'
    inputs.mkdir()
    outputs.mkdir()
    scope = 'FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH' if ledger else 'SYNTHETIC_NOT_RESEARCH'
    scenario = 'REAL_FROZEN_NA_LEDGER' if ledger else scenario
    ids = {family: [family + '_TOY_' + str(index) for index in range(count)] for family, count in COUNTS.items()}
    assembly = []
    for family, members in ids.items():
        for index, identifier in enumerate(members):
            raw = 'NA' if ledger or index % 3 == 0 else repr(.001 + index * .0001)
            assembly.append(dict(analysis_id=identifier, family_id=family, scope=scope, scenario=scenario,
                p_raw=raw, primary_method='NA' if ledger else 'SYNTHETIC_FIXTURE',
                reason='NOT_ESTIMABLE' if ledger else 'ADJUSTER_INPUT_VALIDATION_ONLY'))
    by_id = {row['analysis_id']: row for row in assembly}
    vectors = []
    for family, members in ids.items():
        for method in ['BH', 'BY'] if family.endswith('EDGES') else ['BY']:
            for identifier in members:
                vectors.append(dict(vector_id='/'.join([scope, scenario, family, method]),
                    analysis_id=identifier, p_raw=by_id[identifier]['p_raw'], method=method))
    write_table(inputs / INPUTS[0], ['vector_id', 'analysis_id', 'p_raw', 'method'], vectors)
    write_table(inputs / INPUTS[1], ['analysis_id', 'family_id', 'scope', 'scenario', 'p_raw', 'primary_method', 'reason'], assembly)
    (inputs / INPUTS[3]).write_bytes(methods)
    receipt = dict(schema='FROZEN_A_FAMILY_ASSEMBLY_RECEIPT_V1', scope=scope, scenario=scenario,
        source_inputs=[dict(port=index, name=name, bytes=size, sha256=sha)
            for index, (name, size, sha) in enumerate(SOURCES)], family_counts=COUNTS, family_ids=ids,
        output_sha256={name: checksum(inputs / name) for name in ['assembly.tsv', 'vectors.tsv']},
        assembly_rows=564, vector_rows=840, vector_count=6, raw_missing_preserved=True,
        original_python_functions=['primary_p', 'strict_conjunction', 'assert_locked_ids'],
        original_python_sha256=SOURCES[7][2], request_sha256=hashlib.sha256(b'toy-request-not-scientific').hexdigest(),
        official_adjustment_performed=False, MR_estimates_computed=False,
        scientific_authorization_granted=False, g0_granted=False)
    (inputs / INPUTS[2]).write_text(json.dumps(receipt, allow_nan=False) + '\n')
    return inputs, outputs, receipt


class FrozenAFamilyAdjustmentContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (FAMILY / 'scripts/adjust.R').read_text()
        self.manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())

    def test_exact_single_kind_four_ports_copy_and_zero_parameters(self):
        self.assertEqual(self.manifest['plugin_name'], 'frozen-a-family-adjustment')
        self.assertEqual(len(self.manifest['nodes']), 1)
        node = self.manifest['nodes'][0]
        self.assertEqual(node['kind'], 'frozen_a_family_adjust')
        self.assertEqual(node['ports']['inputs'], [{'type': 'file'}] * 4)
        self.assertEqual([port['path'] for port in node['ports']['outputs']], OUTPUTS)
        self.assertEqual(node['stage_in_mode'], 'copy')
        self.assertNotIn('params', node)
        self.assertEqual(node['command']['script_file'], 'scripts/adjust.R')

    def test_exact_existing_official_image_and_bounded_readonly_resources(self):
        self.assertEqual(self.manifest['image']['reference'],
            'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d')
        self.assertEqual(self.manifest['nodes'][0]['resources'], dict(cpus=1.0, memory='1Gi',
            network='isolated', read_only_rootfs=True, pull_policy='never', pids_limit=64))

    def test_all_nine_original_source_names_sizes_and_hashes_are_explicit(self):
        for name, size, sha in SOURCES:
            self.assertIn('"' + name + '"', self.source)
            self.assertIn(str(size) + 'L', self.source)
            self.assertIn('"' + sha + '"', self.source)
        self.assertIn('length(receipt$source_inputs) == 9L', self.source)
        self.assertIn('integer_scalar(item$port, index - 1L)', self.source)

    def test_only_exact_original_adjustment_definition_is_evaluated(self):
        self.assertEqual(hashlib.sha256(DEFINITION).hexdigest(), DEFINITION_SHA)
        self.assertIn(DEFINITION_SHA, self.source)
        self.assertIn('text_checksum(definition) == DEFINITION_SHA', self.source)
        self.assertIn('new.env(parent = asNamespace("stats"))', self.source)
        self.assertIn('eval(parse(text = definition), envir = official)', self.source)
        self.assertIn('official$adjust_full(raw, method)', self.source)
        self.assertNotRegex(self.source, r'\bsource\s*\(')

    def test_exact_r_version_and_raw_na_are_preserved_separately_from_adjustment_one(self):
        self.assertIn('as.character(getRversion()) == "4.6.1"', self.source)
        self.assertIn('as.character(packageVersion("stats")) == "4.6.1"', self.source)
        self.assertIn('p_raw = raw', self.source)
        self.assertIn('p_for_adjustment = ifelse(is.na(raw), 1, raw)', self.source)
        self.assertIn('adjusted <- vectors', self.source)
        self.assertIn('sprintf("%.17g", value)', self.source)

    def test_shape_scope_scenario_complete_ids_and_per_family_roles_are_checked(self):
        for fragment in ['"Exact technical scope and scenario required"', '"Complete rectangular TSV required"',
                '"Frozen denominators cannot change"', '"Complete frozen family members required"',
                '"Assembly family order differs from its declared frozen IDs"',
                '"Vector raw P or ordered IDs differ from assembly"']:
            self.assertIn(fragment, self.source)
        self.assertIn('if (grepl("EDGES$", family)) c("BH", "BY") else "BY"', self.source)
        self.assertIn('all(is.na(raw))', self.source)

    def test_duplicate_json_keys_and_nonfinite_or_boolean_numbers_are_not_coerced(self):
        self.assertIn('!anyDuplicated(names(value))', self.source)
        self.assertIn('all(is.finite(value))', self.source)
        self.assertIn('is.numeric(value) && !is.logical(value)', self.source)
        self.assertIn('all(is.finite(parsed[!absent]))', self.source)
        self.assertIn('all(parsed[!absent] >= 0 & parsed[!absent] <= 1)', self.source)

    def test_rds_is_complete_not_summary_only(self):
        for field in ['vectors = results', 'input_sha256 = input_hashes', 'adjustment_definition = definition',
                'analysis_id = vectors$analysis_id[positions]', 'p_raw = raw', 'p_for_adjustment =',
                'q = value', 'method = method', 'n_total = length(raw)']:
            self.assertIn(field, self.source)
        self.assertIn('saveRDS(', self.source)

    def test_adjustment_receipt_has_exact_protocol_fields_and_no_authority(self):
        block = self.source.split('result_receipt <- list(', 1)[1].split('jsonlite::write_json', 1)[0]
        for field in RECEIPT_FIELDS:
            self.assertRegex(block, r'\b' + re.escape(field) + r'\s*=')
        for field in ['MR_estimates_computed', 'scientific_authorization_granted', 'g0_granted']:
            self.assertIn(field + ' = FALSE', block)
        self.assertIn('invocation = "adjust_full(p, method)"', block)
        self.assertIn('official_function = "stats::p.adjust"', block)

    def test_publication_registers_only_successful_links_and_rolls_back_owned_content(self):
        block = self.source.split('publish <- function(index, expected)', 1)[1]
        self.assertLess(block.index('file.link('), block.index('published[[length(published)'))
        self.assertIn('if (identical(current, record$fact)) unlink(record$path)', self.source)
        self.assertIn('"Final output identity or content differs"', self.source)
        self.assertIn('"Staged output changed before publication"', self.source)
        self.assertIn('"Published output identity or content differs"', self.source)
        self.assertIn('2L', self.source)

    def test_staging_cleanup_is_identity_bound_and_never_recursive(self):
        self.assertNotIn('recursive = TRUE', self.source)
        self.assertIn('identical(current, stage$fact)', self.source)
        self.assertIn('if (!same_directory()) return(invisible(NULL))', self.source)
        self.assertIn('list.files(stage$directory, all.files = TRUE, no.. = TRUE)', self.source)
        self.assertIn('system2("rmdir"', self.source)

    def test_all_stage_writers_and_error_log_require_owned_identity(self):
        self.assertIn('"Staged content changed before writing"', self.source)
        self.assertIn('"Staging directory identity changed"', self.source)
        self.assertIn('"Completed staged output differs from its recorded identity or content"', self.source)
        self.assertIn('if (!logged) tryCatch(publish_preflight_log(', self.source)
        self.assertIn('input_timestamps <- vapply(inputs, file_identity, character(1))', self.source)
        self.assertIn('identical(vapply(inputs, file_identity, character(1)), input_timestamps)', self.source)

    def test_toy_fixture_is_self_contained_complete_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs, outputs, receipt = fixture(Path(temporary) / 'toy', b'toy-method-file-not-an-official-reference')
            self.assertEqual(set(receipt['family_counts']), set(COUNTS))
            self.assertEqual(sum(map(len, receipt['family_ids'].values())), 564)
            for name in ['assembly.tsv', 'vectors.tsv']:
                self.assertEqual(checksum(inputs / name), receipt['output_sha256'][name])
            with (inputs / 'vectors.tsv').open() as handle:
                rows = list(csv.DictReader(handle, delimiter='\t'))
            self.assertEqual(len(rows), 840)
            self.assertEqual(len({row['vector_id'] for row in rows}), 6)
            self.assertEqual(list(outputs.iterdir()), [])

    def test_real_ledger_fixture_keeps_every_raw_probability_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs, _, receipt = fixture(Path(temporary) / 'toy', b'toy-method-file', ledger=True)
            self.assertEqual(receipt['scope'], 'FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH')
            with (inputs / 'assembly.tsv').open() as handle:
                rows = list(csv.DictReader(handle, delimiter='\t'))
            self.assertEqual(len(rows), 564)
            self.assertTrue(all(row['p_raw'] == 'NA' for row in rows))
            self.assertFalse(receipt['scientific_authorization_granted'])


def r_toy():
    permanent = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent or not os.environ.get('TMPDIR'):
        raise RuntimeError('Explicit managed session required for R runtime evidence')
    output = Path(permanent) / 'frozen-a-family-adjustment-r-toy'
    output.mkdir()
    methods = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0') / SOURCES[8][0]
    original = methods.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCES[8][2]:
        raise RuntimeError('Exact unchanged original methods required')
    script = FAMILY / 'scripts/adjust.R'
    before = checksum(script)
    records = []
    for label in ['synthetic-positive', 'all-missing-ledger', 'wrong-source-hash', 'wrong-vector-p',
                  'mixed-scenario', 'duplicate-json-key', 'nonfinite-json', 'wrong-method-source', 'existing-output']:
        inputs, outputs, receipt = fixture(output / label, original, ledger=label == 'all-missing-ledger')
        if label == 'wrong-source-hash':
            receipt['source_inputs'][0]['sha256'] = '0' * 64
        elif label == 'wrong-vector-p':
            path = inputs / 'vectors.tsv'
            rows = path.read_text().splitlines()
            fields = rows[2].split('\t')
            fields[2] = '0.99'
            rows[2] = '\t'.join(fields)
            path.write_text('\n'.join(rows) + '\n')
            receipt['output_sha256']['vectors.tsv'] = checksum(path)
        elif label == 'mixed-scenario':
            receipt['scenario'] = 'BOUNDARY'
        elif label == 'nonfinite-json':
            receipt['assembly_rows'] = float('inf')
        elif label == 'wrong-method-source':
            (inputs / INPUTS[3]).write_bytes(original + b'\n')
        payload = json.dumps(receipt, allow_nan=True)
        if label == 'duplicate-json-key':
            payload = payload[:-1] + ',"g0_granted":false}'
        (inputs / INPUTS[2]).write_text(payload + '\n')
        sentinel = outputs / OUTPUTS[0]
        if label == 'existing-output':
            sentinel.write_bytes(b'foreign-existing-output')
        hashes = {name: checksum(inputs / name) for name in INPUTS}
        environment = dict(os.environ)
        environment.update({'AUTONOMICS_INPUT' + str(index): str(inputs / name) for index, name in enumerate(INPUTS)})
        environment.update({'AUTONOMICS_OUTPUT' + str(index): str(outputs / name) for index, name in enumerate(OUTPUTS)})
        process = subprocess.run(['/usr/bin/Rscript', '--vanilla', str(script)], env=environment,
            capture_output=True, text=True, timeout=60)
        (output / label / 'stdout.log').write_text(process.stdout)
        (output / label / 'stderr.log').write_text(process.stderr)
        positive = label in ['synthetic-positive', 'all-missing-ledger']
        if process.returncode != (0 if positive else 2):
            raise RuntimeError('R toy outcome differs: ' + label + ': ' + process.stderr)
        if positive:
            observed = json.loads((outputs / OUTPUTS[2]).read_text())
            if set(observed) != RECEIPT_FIELDS or observed['rows'] != 840 or observed['g0_granted'] is not False:
                raise RuntimeError('R toy receipt differs')
        elif label == 'existing-output':
            if sentinel.read_bytes() != b'foreign-existing-output':
                raise RuntimeError('Foreign sentinel was modified')
        elif any((outputs / name).exists() for name in OUTPUTS[:3]):
            raise RuntimeError('Failed adjustment published normal outputs: ' + label)
        if hashes != {name: checksum(inputs / name) for name in INPUTS}:
            raise RuntimeError('R toy changed input bytes')
        records.append(dict(case=label, actual_exit=process.returncode, input_sha256=hashes,
            output_sha256={path.name: checksum(path) for path in outputs.iterdir()}, scientific_authorization_granted=False))
    if checksum(script) != before or methods.read_bytes() != original:
        raise RuntimeError('Method source changed during R toy')
    report = dict(scope='SYNTHETIC_ADJUSTER_IO_NOT_FROZEN_REGISTRY_QUALIFICATION', cases=records,
        script_sha256=before, official_container_executed=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(cases=len(records), g0_granted=False)))


def r_stage_toy():
    permanent = os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    temporary = os.environ.get('TMPDIR')
    if not permanent or not temporary:
        raise RuntimeError('Explicit managed session required for R staging evidence')
    output = Path(permanent) / 'frozen-a-family-adjustment-stage-toy'
    output.mkdir()
    source = FAMILY / 'scripts/adjust.R'
    before = checksum(source)
    snapshot = output / 'adjust.R'
    snapshot.write_bytes(source.read_bytes())
    program = output / 'stage-toy.R'
    program.write_text(r'''
arguments <- commandArgs(TRUE)
for (expression in parse(arguments[1])) {
  if (is.call(expression) && identical(expression[[1]], as.name("<-")) &&
      !identical(expression[[2]], as.name("status"))) eval(expression)
}
root <- arguments[2]
stopifnot(dir.create(root))
normal <- create_stage(root, "normal.log")
write_stage(normal, function(path) writeLines("owned", path))
clean_stage(normal)
stopifnot(!dir.exists(normal$directory))
cat("PASS normal-owned-retirement\n")
unknown <- create_stage(root, "known.log")
write_stage(unknown, function(path) writeLines("owned", path))
writeLines("foreign-extra", file.path(unknown$directory, "extra"))
clean_stage(unknown)
stopifnot(dir.exists(unknown$directory), !file.exists(unknown$path),
  identical(readLines(file.path(unknown$directory, "extra")), "foreign-extra"))
cat("PASS unknown-member-preserved\n")
replacement <- create_stage(root, "replacement.log")
write_stage(replacement, function(path) writeLines("owned", path))
stopifnot(file.rename(replacement$directory, paste0(replacement$directory, ".original")))
stopifnot(dir.create(replacement$directory))
writeLines("foreign-directory", replacement$path)
stopifnot(inherits(tryCatch(write_stage(replacement, function(path) cat("BAD", file = path, append = TRUE)),
  error = identity), "error"))
clean_stage(replacement)
stopifnot(identical(readLines(replacement$path), "foreign-directory"))
cat("PASS foreign-directory-neither-appended-nor-deleted\n")
modified <- create_stage(root, "modified.log")
write_stage(modified, function(path) writeLines("owned", path))
before_identity <- modified$fact$identity
writeLines("foreign-same-inode", modified$path)
stopifnot(identical(owned_fact(modified$path)$identity[1:2], before_identity[1:2]))
stopifnot(inherits(tryCatch(write_stage(modified, function(path) cat("BAD", file = path, append = TRUE)),
  error = identity), "error"))
clean_stage(modified)
stopifnot(identical(readLines(modified$path), "foreign-same-inode"))
cat("PASS same-inode-change-neither-appended-nor-deleted\n")
for (mutation in c("directory", "same-inode", "post-write")) {
  case <- file.path(root, paste0("execute-", mutation))
  stopifnot(dir.create(case))
  for (index in 0:3) {
    input <- file.path(case, paste0("input", index))
    writeLines("toy-non-scientific", input)
    do.call(Sys.setenv, setNames(list(input), paste0("AUTONOMICS_INPUT", index)))
    do.call(Sys.setenv, setNames(list(file.path(case, paste0("output", index))), paste0("AUTONOMICS_OUTPUT", index)))
  }
  damaged_path <- NULL
  run_adjustment <- function(inputs, stages) {
    if (mutation == "post-write") {
      for (stage in stages[1:3]) write_stage(stage, function(path) writeLines("toy-owned-output", path))
      damaged_path <<- stages[[1]]$path
      writeLines("foreign-execute-log", damaged_path)
      return(invisible(NULL))
    }
    stage <- stages[[4]]
    damaged_path <<- stage$path
    if (mutation == "directory") {
      stopifnot(file.rename(stage$directory, paste0(stage$directory, ".original")))
      stopifnot(dir.create(stage$directory))
    }
    writeLines("foreign-execute-log", stage$path)
    stop("INJECTED_STAGE_REPLACEMENT", call. = FALSE)
  }
  stopifnot(identical(execute(), 2L), identical(readLines(damaged_path), "foreign-execute-log"))
  marker <- if (mutation == "post-write") "Completed staged output differs" else "INJECTED_STAGE_REPLACEMENT"
  stopifnot(any(grepl(marker, readLines(Sys.getenv("AUTONOMICS_OUTPUT3")), fixed = TRUE)))
  stopifnot(!any(file.exists(vapply(0:2, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), character(1)))))
  cat(paste0("PASS execute-", mutation, "-foreign-log-preserved-exclusive-fallback\n"))
}
''')
    process = subprocess.run(['/usr/bin/Rscript', '--vanilla', str(program), str(snapshot),
        str(Path(temporary) / 'adjustment-stage-toy')], capture_output=True, text=True, timeout=60)
    (output / 'stdout.log').write_text(process.stdout)
    (output / 'stderr.log').write_text(process.stderr)
    expected = ['normal-owned-retirement', 'unknown-member-preserved',
        'foreign-directory-neither-appended-nor-deleted', 'same-inode-change-neither-appended-nor-deleted',
        'execute-directory-foreign-log-preserved-exclusive-fallback',
        'execute-same-inode-foreign-log-preserved-exclusive-fallback',
        'execute-post-write-foreign-log-preserved-exclusive-fallback']
    observed = process.stdout.splitlines()
    passed = process.returncode == 0 and observed == ['PASS ' + name for name in expected]
    report = dict(scope='ACTUAL_R_STAGE_HELPERS_AND_EXECUTE_IO_TOY_NOT_STATISTICAL_PROOF',
        script_sha256=before, source_after_unchanged=checksum(source) == before,
        cases=expected, exit_code=process.returncode, exact_markers_passed=passed,
        official_container_executed=False, scientific_authorization_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    if not passed or checksum(source) != before:
        raise RuntimeError('Actual R staging toy failed: ' + process.stderr)
    print(json.dumps(dict(stage_cases=len(expected), g0_granted=False)))


if __name__ == '__main__':
    if '--r-toy' in sys.argv or '--r-stage-toy' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--r-toy', action='store_true')
        parser.add_argument('--r-stage-toy', action='store_true')
        arguments = parser.parse_args()
        if arguments.r_toy:
            r_toy()
        if arguments.r_stage_toy:
            r_stage_toy()
    else:
        unittest.main()
