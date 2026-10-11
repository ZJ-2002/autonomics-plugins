#!/usr/bin/env python3
"""Validate supplied SNP-exposure covariance bytes; never infer or approve them.

This preparation adapter does not execute MVMR, freeze a family, or grant G0.
It reads standard errors and identities, without using effects or P values.
The covariance of exposure estimates is distinct from exposure-outcome overlap
and from covariance between the two coefficients of a mediation path.
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import re

SUPPORTED_PROTOCOLS = frozenset({'4.2.1', '4.3.2'})


def frozen_protocol(recipe):
    """Select an explicit known recipe version, without granting authority."""
    version = recipe.get('protocol_version')
    if (not isinstance(version, str) or version not in SUPPORTED_PROTOCOLS
            or recipe.get('status') != 'FROZEN'):
        reject('explicit frozen supported covariance protocol required')
    return version


def reject(message):
    raise ValueError(message)


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        reject(f'{label}: exact fields required')


def digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        reject(f'input must be a regular, non-symlink file: {path}')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                reject(f'duplicate JSON field: {key}')
            result[key] = value
        return result

    def nonfinite(value):
        reject(f'non-finite JSON constant: {value}')

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=nonfinite)


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        reject(f'{label}: finite number required')
    return float(value)


def identities(values, label, minimum=1):
    if not isinstance(values, list) or len(values) < minimum or any(
            not isinstance(v, str) or not v or v != v.strip() for v in values):
        reject(f'{label}: nonempty ordered identities required')
    if len(values) != len(set(values)):
        reject(f'{label}: duplicate identity')
    return values


def positive_semidefinite(correlation, tolerance):
    """Semidefinite Cholesky, including singular matrices, on the SE-scaled matrix.

    Scaling avoids accepting a physically invalid covariance simply because
    all source standard errors are small. The tolerance is explicit in the
    frozen recipe; it is not a data-selected ridge or a repair operation.
    """
    size = len(correlation)
    lower = [[0.0] * size for _ in range(size)]
    for i in range(size):
        pivot = correlation[i][i] - math.fsum(v * v for v in lower[i][:i])
        if pivot < -tolerance:
            reject('SNP covariance matrix is not positive semidefinite')
        lower[i][i] = math.sqrt(max(pivot, 0.0))
        for j in range(i + 1, size):
            residual = correlation[j][i] - math.fsum(
                lower[j][k] * lower[i][k] for k in range(i))
            if lower[i][i] == 0:
                if abs(residual) > tolerance:
                    reject('singular SNP covariance matrix is not positive semidefinite')
            else:
                lower[j][i] = residual / lower[i][i]


def validate_covariance(recipe_path, data_path, covariance_path, evidence_paths):
    """Return a technical receipt only, including explicit unresolved records.

    evidence_paths maps registered evidence IDs to actual files. Each pair
    must bind one evidence artifact and identify the estimation approach and
    sample relationship. Their scientific adequacy is a separate signed
    review; this adapter cannot establish disjoint participants from labels.
    """
    before = {'recipe': digest(recipe_path), 'harmonized_data': digest(data_path),
              'covariance': digest(covariance_path)}
    recipe = load_json(recipe_path)
    exact_keys(recipe, ['schema_version', 'protocol_version', 'status', 'analysis_id',
                        'purpose', 'exposure_ids', 'snp_column', 'standard_error_columns',
                        'input_sha256', 'relative_tolerance'], 'recipe')
    if type(recipe['schema_version']) is not int or recipe['schema_version'] != 1:
        reject('unsupported covariance recipe schema')
    frozen_protocol(recipe)
    if recipe['purpose'] != 'SNP_EXPOSURE_ESTIMATE_COVARIANCE':
        reject('wrong covariance purpose; overlap or path covariance cannot substitute')
    analysis = identities([recipe['analysis_id']], 'analysis_id')[0]
    exposures = identities(recipe['exposure_ids'], 'exposure_ids', minimum=2)
    exact_keys(recipe['input_sha256'], ['harmonized_data', 'covariance'], 'input_sha256')
    for name in ['harmonized_data', 'covariance']:
        if recipe['input_sha256'][name] != before[name]:
            reject(f'input SHA256 mismatch: {name}')
    tolerance = finite(recipe['relative_tolerance'], 'relative_tolerance')
    if not 0 < tolerance <= 1e-8:
        reject('relative_tolerance must be explicit and within (0, 1e-8]')
    exact_keys(recipe['standard_error_columns'], exposures, 'standard_error_columns')
    columns = [recipe['snp_column']] + [recipe['standard_error_columns'][e] for e in exposures]
    identities(columns, 'input columns')
    errors, snps = [], []
    with Path(data_path).open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not set(columns) <= set(reader.fieldnames):
            reject('harmonized data columns absent or duplicated')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                reject('malformed harmonized data row')
            snps.append(row[columns[0]])
            try:
                se = [float(row[c]) for c in columns[1:]]
            except ValueError:
                reject('non-numeric exposure standard error')
            if any(not math.isfinite(s) or s <= 0 for s in se):
                reject('positive finite exposure standard errors required')
            errors.append(se)
    # Empty joint selections still need a byte-bound receipt so the method can
    # retain its planned coefficient rows as NOT_ESTIMABLE instead of silently
    # shrinking the hypothesis family. This never makes an empty model usable.
    identities(snps, 'SNP identities', minimum=0)
    covariance = load_json(covariance_path)
    exact_keys(covariance, ['schema_version', 'analysis_id', 'purpose', 'exposure_ids',
                            'snp_ids', 'matrices', 'pair_provenance'], 'covariance')
    if type(covariance['schema_version']) is not int or covariance['schema_version'] != 1:
        reject('unsupported supplied covariance schema')
    if covariance['analysis_id'] != analysis or covariance['purpose'] != recipe['purpose']:
        reject('covariance analysis identity or purpose mismatch')
    if covariance['exposure_ids'] != exposures or covariance['snp_ids'] != snps:
        reject('covariance axes must equal the actual exposure and SNP ordering')
    matrices = covariance['matrices']
    if not isinstance(matrices, list) or len(matrices) != len(snps):
        reject('exactly one supplied covariance matrix per SNP required')
    for index, matrix in enumerate(matrices):
        k = len(exposures)
        if not isinstance(matrix, list) or len(matrix) != k or any(
                not isinstance(row, list) or len(row) != k for row in matrix):
            reject('SNP covariance matrix dimension mismatch')
        numeric = [[finite(v, 'covariance') for v in row] for row in matrix]
        corr = [[numeric[i][j] / errors[index][i] / errors[index][j]
                 for j in range(k)] for i in range(k)]
        if any(not math.isfinite(v) for row in corr for v in row):
            reject('non-finite scaled covariance')
        for i in range(k):
            if abs(corr[i][i] - 1) > tolerance:
                reject('covariance diagonal differs from actual exposure SE squared')
            for j in range(i):
                if abs(corr[i][j] - corr[j][i]) > tolerance:
                    reject('SNP covariance matrix is not symmetric')
        positive_semidefinite(corr, tolerance)
    pairs = list(itertools.combinations(exposures, 2))
    provenance = covariance['pair_provenance']
    if not isinstance(provenance, list) or len(provenance) != len(pairs):
        reject('complete pairwise covariance provenance required')
    evidence_before, unresolved = {}, []
    for record, expected in zip(provenance, pairs):
        exact_keys(record, ['exposure_pair', 'method', 'sample_relationship', 'evidence_id',
                            'evidence_sha256', 'justification', 'status'], 'pair provenance')
        if record['exposure_pair'] != list(expected):
            reject('pair provenance ordering or identity mismatch')
        if record['method'] not in {'SOURCE_DATA', 'PROVIDER_MATRIX',
                                    'JUSTIFIED_CORRELATION_AND_OVERLAP_MODEL',
                                    'VALIDATED_SUMMARY_ESTIMATE', 'JUSTIFIED_ZERO'}:
            reject('explicit supported covariance provenance method required')
        if record['sample_relationship'] not in {'DISJOINT', 'FULL_OVERLAP',
                                                 'KNOWN_PARTIAL_OVERLAP', 'UNKNOWN_PARTIAL_OVERLAP'}:
            reject('explicit exposure sample relationship required')
        if record['method'] == 'JUSTIFIED_CORRELATION_AND_OVERLAP_MODEL' and record['sample_relationship'] == 'UNKNOWN_PARTIAL_OVERLAP':
            reject('unknown partial overlap cannot use a fully specified overlap formula')
        if record['method'] == 'JUSTIFIED_ZERO':
            if record['sample_relationship'] != 'DISJOINT':
                reject('this zero-covariance adapter requires documented disjoint samples; other justifications need a separately reviewed adapter')
            i, j = [exposures.index(e) for e in expected]
            if any(matrix[i][j] != 0 or matrix[j][i] != 0 for matrix in matrices):
                reject('JUSTIFIED_ZERO provenance conflicts with supplied matrix')
        if record['status'] not in {'RECORD_AVAILABLE_NOT_SCIENTIFICALLY_APPROVED', 'UNRESOLVED'}:
            reject('covariance preparation must not assert scientific approval')
        identities([record['justification']], 'provenance justification')
        identities([record['evidence_id']], 'provenance evidence identity')
        evidence_id = record['evidence_id']
        if evidence_id not in evidence_paths or not re.fullmatch('[0-9a-f]{64}', str(record['evidence_sha256'])):
            reject('actual covariance evidence artifact and full SHA256 required')
        actual = digest(evidence_paths[evidence_id])
        if actual != record['evidence_sha256']:
            reject('covariance evidence artifact SHA256 mismatch')
        evidence_before[evidence_id] = actual
        if record['status'] == 'UNRESOLVED':
            unresolved.append(list(expected))
    after = {'recipe': digest(recipe_path), 'harmonized_data': digest(data_path),
             'covariance': digest(covariance_path)}
    if before != after or any(digest(evidence_paths[e]) != sha for e, sha in evidence_before.items()):
        reject('covariance input changed during validation')
    return {'schema_version': 1, 'scope': 'MVMR_COVARIANCE_PREPARATION_ONLY',
            'status': 'BLOCKED_UNRESOLVED_PROVENANCE' if unresolved else 'TECHNICAL_BYTES_VALIDATED',
            'analysis_id': analysis, 'exposure_ids': exposures, 'snp_count': len(snps),
            'pair_count': len(pairs), 'input_sha256': before, 'evidence_sha256': evidence_before,
            'unresolved_pairs': unresolved, 'scientific_approval_verified': False,
            'g0_pass': False, 'formal_authorized': False, 'mvmr_executed': False,
            'single_variable_mr_blocked': False, 'implicit_zero_covariance': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['recipe', 'data', 'covariance', 'evidence-map']:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    report = validate_covariance(args.recipe, args.data, args.covariance, load_json(args.evidence_map))
    print(json.dumps(report, sort_keys=True))
    return 2 if report['unresolved_pairs'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
