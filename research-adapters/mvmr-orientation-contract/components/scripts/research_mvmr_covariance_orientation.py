#!/usr/bin/env python3
"""Orient supplied source-effect covariance using the actual joint sign ledger.

No covariance is estimated here. Both exposure axes and the complete retained
SNP order must be explicit. This component grants no source, G0 or scientific
qualification; the protected DAG must separately establish producer lineage.
"""
import csv
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

if 'validator' not in globals():
    import research_mvmr_covariance as validator

LABELS = ['recipe', 'joint', 'ledger', 'harmonization_audit', 'joint_identity',
          'exposure0', 'exposure1', 'source_covariance', 'evidence_pack']
JOINT_HEADER = ['SNP', 'beta_Y', 'se_Y', 'beta_X0', 'se_X0', 'beta_X1', 'se_X1']
SOURCE_HEADER = ['snp', 'chr', 'pos', 'beta', 'se', 'effect_allele',
                 'other_allele', 'eaf', 'pval']
LEDGER_HEADER = ['snp', 'chr', 'pos', 'anchor_effect_allele', 'anchor_other_allele',
                 'status', 'reason_exposure0', 'reason_exposure1', 'reason_outcome',
                 'sign_exposure0', 'sign_exposure1', 'sign_outcome']
RAW_KEYS = ['schema_version', 'analysis_id', 'purpose', 'exposure_ids', 'snp_ids',
            'matrices', 'pair_provenance']


def check(condition, message):
    if not condition:
        raise ValueError(message)


def table(path, header, bounded=True):
    rows = []
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        check(reader.fieldnames == header, 'actual table header/order differs')
        for row in reader:
            check(None not in row and all(x is not None for x in row.values()),
                  'malformed actual table row')
            rows.append(row)
            if bounded:
                check(len(rows) <= 4096, 'joint selection exceeds qualified bound; no clipping')
    return rows


def close(actual, expected):
    return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-300)


def source_rows(path, snps):
    """Scan complete normalized bytes but retain only the declared joint rows.

    Full-source duplicate/QC qualification belongs to the native producer;
    duplicate retained IDs always fail here. No P value selects a covariance.
    """
    found = {}
    wanted = set(snps)
    with Path(path).open(newline='') as stream:
        check(stream.readline().rstrip('\n\r').split('\t') == SOURCE_HEADER,
              'normalized source header differs')
        for line in stream:
            check(len(line) <= 1024**2, 'source row exceeds bounded parser')
            fields = line.rstrip('\n\r').split('\t')
            check(len(fields) == len(SOURCE_HEADER), 'malformed normalized source row')
            if fields[0] in wanted:
                check(fields[0] not in found, 'duplicate retained source variant')
                found[fields[0]] = dict(zip(SOURCE_HEADER, fields))
    check(set(found) == wanted, 'retained joint variant missing from actual source')
    return found


def evidence_files(pack, supplied, directory):
    validator.exact_keys(pack, ['schema_version', 'evidence'], 'evidence pack')
    check(type(pack['schema_version']) is int and pack['schema_version'] == 1,
          'unsupported evidence pack schema')
    evidence = pack['evidence']
    check(isinstance(evidence, dict) and evidence, 'actual provenance bytes required')
    required = {r['evidence_id'] for r in supplied['pair_provenance']}
    check(set(evidence) == required, 'exact provenance evidence set required')
    result = {}
    for n, (ident, artifact) in enumerate(evidence.items()):
        validator.exact_keys(artifact, ['sha256', 'content_hex'], 'evidence artifact')
        h, text = artifact['sha256'], artifact['content_hex']
        check(isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h) and
              isinstance(text, str) and re.fullmatch('(?:[0-9a-f]{2})*', text),
              'complete evidence SHA256 and lowercase byte hex required')
        b = bytes.fromhex(text)
        check(hashlib.sha256(b).hexdigest() == h, 'actual provenance bytes SHA256 mismatch')
        path = Path(directory) / ('evidence-' + str(n))
        path.write_bytes(b)
        result[ident] = path
    return result


def orient(inputs):
    check(len(inputs) == len(LABELS), 'nine actual inputs required')
    paths = dict(zip(LABELS, map(Path, inputs)))
    before = {k: validator.digest(p) for k, p in paths.items()}
    for name, path in paths.items():
        if name not in {'exposure0', 'exposure1'}:
            check(path.stat().st_size <= 8 * 1024**2, 'orientation input exceeds 8MiB bound')
    c = validator.load_json(paths['recipe'])
    validator.exact_keys(c, ['schema_version', 'protocol_version', 'status', 'analysis_id',
        'purpose', 'exposure_ids', 'source_orientation', 'transform', 'relative_tolerance',
        'input_sha256'], 'orientation recipe')
    check(type(c['schema_version']) is int and c['schema_version'] == 1,
          'supported orientation recipe schema required')
    protocol = validator.frozen_protocol(c)
    check(c['purpose'] == 'SNP_EXPOSURE_ESTIMATE_COVARIANCE' and
          c['source_orientation'] == 'NORMALIZED_SOURCE_EFFECT_ALLELES' and
          c['transform'] == 'D_SIGMA_D_ACTUAL_JOINT_LEDGER_NO_PROJECTION',
          'explicit source-effect covariance orientation required')
    ids = validator.identities(c['exposure_ids'], 'exposure_ids', minimum=2)
    check(len(ids) == 2, 'qualified orientation adapter requires exactly two exposures')
    analysis = validator.identities([c['analysis_id']], 'analysis_id')[0]
    tolerance = validator.finite(c['relative_tolerance'], 'relative_tolerance')
    check(0 < tolerance <= 1e-8, 'explicit bounded covariance tolerance required')
    validator.exact_keys(c['input_sha256'], LABELS[1:], 'actual orientation input hashes')
    check(all(c['input_sha256'][k] == before[k] for k in LABELS[1:]),
          'orientation input SHA256 mismatch')
    data = table(paths['joint'], JOINT_HEADER)
    snps = validator.identities([r['SNP'] for r in data], 'joint SNPs', minimum=0)
    for row in data:
        for col in JOINT_HEADER[1:]:
            v = float(row[col])
            check(math.isfinite(v) and (not col.startswith('se_') or v > 0),
                  'positive finite SE and finite joint coefficients required')
    identity = validator.load_json(paths['joint_identity'])
    validator.exact_keys(identity, ['type', 'analysis_id', 'exposure_ids', 'outcome_id',
        'snp_ids', 'harmonized_sha256', 'outcome_used_for_selection'], 'joint identity')
    check(identity['type'] == 'FROZEN_JOINT_INPUT_IDENTITY_NOT_SOURCE_QUALIFICATION' and
          identity['analysis_id'] == analysis and identity['exposure_ids'] == ids and
          identity['snp_ids'] == snps and identity['harmonized_sha256'] == before['joint'] and
          identity['outcome_used_for_selection'] is False,
          'actual joint identity or axes differ')
    audit = validator.load_json(paths['harmonization_audit'])
    check(audit['scope'] == 'OFFICIAL_JOINT_HARMONIZATION_NOT_SELECTION_OR_SCIENTIFIC_APPROVAL' and
          audit['analysis_id'] == analysis and audit['exposure_ids'] == ids and
          audit['outcome_id'] == identity['outcome_id'] and audit['retained_ids'] == snps and
          audit['harmonized_sha256'] == before['joint'] and audit['ledger_sha256'] == before['ledger'] and
          audit['outcome_used_for_selection'] is False and audit['formal_authorized'] is False and
          audit['scientific_approval_verified'] is False and
          audit['source_to_joint_exposure_signs_available_in_ledger'] is True and
          audit['covariance_orientation_not_inferred_or_transformed'] is True,
          'actual harmonization audit or full ledger binding differs')
    for n in range(2):
        check(audit['input_sha256']['exposure' + str(n)] == before['exposure' + str(n)] and
              audit['selection']['source_exposure_sha256_by_id'][ids[n]] == before['exposure' + str(n)],
              'actual normalized source hash differs from joint producer')
    ledger = table(paths['ledger'], LEDGER_HEADER)
    selected = validator.identities([r['snp'] for r in ledger], 'complete selected SNP ledger', minimum=0)
    check(selected == audit['selected_ids'], 'complete selected ledger identity differs')
    for row in ledger:
        check(row['status'] in {'RETAINED', 'EXCLUDED'}, 'unknown harmonization ledger state')
        reasons = [row['reason_exposure0'], row['reason_exposure1'], row['reason_outcome']]
        check((not any(reasons)) == (row['status'] == 'RETAINED'),
              'harmonization ledger retained status/reasons disagree')
    retained = [r for r in ledger if r['status'] == 'RETAINED']
    check([r['snp'] for r in retained] == snps, 'retained ledger universe/order differs')
    source = [source_rows(paths['exposure' + str(n)], snps) for n in range(2)]
    signs = []
    for row, aligned in zip(retained, data):
        check(row['anchor_effect_allele'] in {'A', 'C', 'G', 'T'} and
              row['anchor_other_allele'] in {'A', 'C', 'G', 'T'} and
              row['anchor_effect_allele'] != row['anchor_other_allele'], 'invalid anchor alleles')
        per_snp = []
        for n in range(2):
            text = row['sign_exposure' + str(n)]
            check(text in {'1', '-1'}, 'actual retained exposure sign must be +1 or -1')
            sign = int(text)
            raw = source[n][row['snp']]
            check(raw['chr'] == row['chr'] and raw['pos'] == row['pos'],
                  'actual source and selected coordinates differ')
            beta, se = float(raw['beta']), float(raw['se'])
            check(math.isfinite(beta) and math.isfinite(se) and se > 0 and
                  close(float(aligned['beta_X' + str(n)]), sign * beta) and
                  close(float(aligned['se_X' + str(n)]), se),
                  'actual signed source coefficient or unchanged SE differs')
            # Non-palindromes have an independently recoverable allele sign.
            # Palindrome direction is the actual official frequency-resolved
            # producer sign; beta=0 is never used to infer that direction.
            pair = raw['effect_allele'] + raw['other_allele']
            anchor = row['anchor_effect_allele'] + row['anchor_other_allele']
            check(len(pair) == 2 and all(a in 'ACGT' for a in pair) and pair[0] != pair[1],
                  'invalid normalized source alleles')
            if pair not in {'AT', 'TA', 'CG', 'GC'}:
                complement = pair.translate(str.maketrans('ACGT', 'TGCA'))
                check(anchor in {pair, pair[::-1], complement, complement[::-1]},
                      'source alleles incompatible with actual joint anchor')
                expected = 1 if anchor in {pair, complement} else -1
                check(sign == expected, 'joint ledger sign disagrees with actual source alleles')
            per_snp.append(sign)
        signs.append(per_snp)
    raw = validator.load_json(paths['source_covariance'])
    validator.exact_keys(raw, RAW_KEYS + ['source_orientation'], 'source covariance')
    axes = raw['source_orientation']
    validator.exact_keys(axes, ['type', 'source_exposure_sha256_by_id', 'effect_alleles'],
                         'source covariance orientation axes')
    check(axes['type'] == c['source_orientation'] and
          axes['source_exposure_sha256_by_id'] == {ids[n]: before['exposure' + str(n)] for n in range(2)},
          'source covariance is not bound to the actual normalized effect alleles')
    expected_alleles = [[[source[n][s]['effect_allele'], source[n][s]['other_allele']]
                         for n in range(2)] for s in snps]
    check(axes['effect_alleles'] == expected_alleles, 'explicit covariance allele axes differ')
    check(raw['analysis_id'] == analysis and raw['exposure_ids'] == ids and raw['snp_ids'] == snps,
          'exact retained source covariance axes required; projection is forbidden')
    supplied = {k: raw[k] for k in RAW_KEYS}
    with tempfile.TemporaryDirectory(prefix='mvmr-covariance-orientation-') as temporary:
        temporary = Path(temporary)
        evidence = evidence_files(validator.load_json(paths['evidence_pack']), supplied, temporary)
        rp, cp = temporary / 'covariance-recipe.json', temporary / 'covariance.json'
        cp.write_text(json.dumps(supplied, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
        recipe = {'schema_version': 1, 'protocol_version': protocol, 'status': 'FROZEN',
            'analysis_id': analysis, 'purpose': c['purpose'], 'exposure_ids': ids,
            'snp_column': 'SNP', 'standard_error_columns': {ids[n]: 'se_X' + str(n) for n in range(2)},
            'relative_tolerance': tolerance,
            'input_sha256': {'harmonized_data': before['joint'], 'covariance': validator.digest(cp)}}
        rp.write_text(json.dumps(recipe))
        validation = validator.validate_covariance(rp, paths['joint'], cp, evidence)
        oriented = dict(supplied)
        oriented['matrices'] = [[[float(m[i][j]) * sign[i] * sign[j] for j in range(2)]
                                  for i in range(2)] for m, sign in zip(supplied['matrices'], signs)]
        contents = (json.dumps(oriented, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
        cp.write_bytes(contents)
        recipe['input_sha256']['covariance'] = validator.digest(cp)
        rp.write_text(json.dumps(recipe))
        after_validation = validator.validate_covariance(rp, paths['joint'], cp, evidence)
        check(after_validation['status'] == validation['status'] and
              after_validation['unresolved_pairs'] == validation['unresolved_pairs'],
              'orientation must preserve provenance status')
    check(before == {k: validator.digest(p) for k, p in paths.items()},
          'orientation input changed during validation')
    receipt = {'schema_version': 1, 'scope': 'MVMR_SOURCE_COVARIANCE_ORIENTATION_ONLY',
        'status': validation['status'], 'analysis_id': analysis, 'exposure_ids': ids,
        'snp_ids': snps, 'selected_ids': selected, 'input_sha256': before,
        'transform': c['transform'], 'source_orientation': c['source_orientation'],
        'signs_in_joint_order': signs, 'oriented_covariance_sha256': hashlib.sha256(contents).hexdigest(),
        'evidence_sha256': validation['evidence_sha256'], 'unresolved_pairs': validation['unresolved_pairs'],
        'covariance_estimated': False, 'implicit_zero_covariance': False,
        'variant_projection_performed': False, 'scientific_approval_verified': False,
        'g0_pass': False, 'formal_authorized': False}
    report = (json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    return [contents, report], receipt


def produce(inputs, outputs):
    outputs = list(map(Path, outputs))
    check(len(outputs) == 2 and outputs[0] != outputs[1] and
          outputs[0].parent == outputs[1].parent, 'two distinct outputs in one existing directory required')
    parent = outputs[0].parent
    check(parent.is_dir() and not parent.is_symlink(), 'regular existing output directory required')
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    pending, published = [], []
    try:
        # Directory-inode flock avoids unlink/recreate identity windows and
        # automatically releases on cancellation/crash. Foreign writers still
        # cannot be overwritten: each final link is independently no-clobber.
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check(not any(os.path.lexists(p) for p in outputs), 'output exists; refusing overwrite')
        check(not any(p.resolve() in {Path(i).resolve() for i in inputs} for p in outputs),
              'output aliases an input')
        payloads, receipt = orient(inputs)
        for payload in payloads:
            fd, name = tempfile.mkstemp(prefix='.mvmr-orientation-', dir=parent)
            pending.append(Path(name))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        check(receipt['input_sha256'] == dict(zip(LABELS, [validator.digest(p) for p in inputs])),
              'orientation input changed before publication')
        for src, target in zip(pending, outputs):
            os.link(src, target)
            published.append((src, target))
        os.fsync(directory)
        return receipt
    except BaseException:
        for src, target in reversed(published):
            if os.path.lexists(target):
                a, b = src.lstat(), target.lstat()
                if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                    target.unlink()
        raise
    finally:
        for path in pending:
            path.unlink()
        os.close(directory)


def main():
    if len(sys.argv) == 12:
        inputs, outputs = sys.argv[1:10], sys.argv[10:12]
    elif len(sys.argv) == 1:
        inputs = [os.environ['AUTONOMICS_INPUT' + str(n)] for n in range(9)]
        outputs = [os.environ['AUTONOMICS_OUTPUT' + str(n)] for n in range(2)]
    else:
        raise ValueError('nine input paths and two output paths required')
    r = produce(inputs, outputs)
    print(json.dumps({'scope': r['scope'], 'status': r['status'], 'snp_count': len(r['snp_ids']),
                      'formal_authorized': False}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        print('BLOCKED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
