"""Fail-closed v4.1 study guards, separate from official statistical algorithms."""

from decimal import Decimal, InvalidOperation
import math


def probability(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Probability cannot be boolean")
    number = float(value)
    if math.isnan(number):
        return None
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError("Probability outside [0,1]")
    return number


def required_flag(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be an audited boolean")
    return value


def select_primary(overlap, ivw_p, mrlap_p, *, usual_eligible, overlap_evidence,
                   mrlap_eligible, rules):
    flags = {"usual_eligible": usual_eligible, "overlap_evidence": overlap_evidence,
             "mrlap_eligible": mrlap_eligible}
    for name, value in flags.items():
        required_flag(value, name)
    policy = rules["pairwise"]["primary_p_policy"]
    if overlap not in policy:
        raise ValueError("Overlap class is not frozen")
    ivw_p, mrlap_p = probability(ivw_p), probability(mrlap_p)
    result = {"raw_p": None, "primary_method": "NA", "status": "NOT_ESTIMABLE"}
    if not usual_eligible or overlap == "O3":
        result["reason"] = "PRIMARY_ELIGIBILITY_FAILED"
    elif not overlap_evidence or overlap == "O2":
        result["reason"] = "OVERLAP_UNRESOLVED"
    else:
        source = policy[overlap]["primary"]
        selected = ivw_p if source == "IVW" else mrlap_p
        if source == "MRlap_corrected" and not mrlap_eligible:
            result["reason"] = "OVERLAP_UNRESOLVED"
        elif source not in {"IVW", "MRlap_corrected"} or selected is None:
            result["reason"] = "PRIMARY_RESULT_MISSING"
        else:
            result.update(raw_p=selected, primary_method=source, status="ESTIMATED",
                          reason=f"FROZEN_{overlap}")
    result["adjustment_p"] = 1.0 if result["raw_p"] is None else result["raw_p"]
    return result


def palindrome_filter(effect, other, eaf_x, eaf_y, *, aligned, rules):
    required_flag(aligned, "aligned")
    alleles = (str(effect).upper(), str(other).upper())
    if any(len(allele) != 1 or allele not in "ACGT" for allele in alleles) or alleles[0] == alleles[1]:
        return "REQUIRES_VARIANT_HARMONIZER"
    if frozenset(alleles) not in {frozenset("AT"), frozenset("CG")}:
        return "NONPALINDROMIC_REQUIRES_OTHER_QC"
    if not aligned:
        return "EXCLUDE_DIRECTION_UNRESOLVED"
    frequencies = []
    for value in (eaf_x, eaf_y):
        if value is None or str(value).strip().lower() in {"", "na", "nan"}:
            return "EXCLUDE_MISSING_EAF"
        if isinstance(value, bool):
            raise ValueError("EAF cannot be boolean")
        try:
            number = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError("Invalid EAF") from error
        if not number.is_finite() or not 0 <= number <= 1:
            raise ValueError("EAF outside [0,1]")
        frequencies.append(number)
    instrument = rules["instrument"]
    low, high = map(lambda value: Decimal(str(value)), instrument["palindrome_ambiguous_eaf"])
    if not instrument["palindrome_boundaries_inclusive"]:
        raise ValueError("The v4.1 closed-boundary contract changed")
    if any(low <= value <= high for value in frequencies):
        return "EXCLUDE_AMBIGUOUS"
    if abs(frequencies[0] - frequencies[1]) > Decimal(str(instrument["palindrome_max_eaf_difference"])):
        return "EXCLUDE_FREQUENCY_MISMATCH"
    return "PASS_THIS_FILTER_ONLY"


def joint_probability(component_p, *, same_construct):
    required_flag(same_construct, "same_construct")
    if len(component_p) != 2:
        raise ValueError("A registered two-edge path must have exactly two components")
    values = [probability(value) for value in component_p]
    return None if not same_construct or any(value is None for value in values) else max(values)


def complete_family(locked_ids, results, *, method):
    identifiers = list(locked_ids)
    if (not identifiers or any(not isinstance(identifier, str) or not identifier for identifier in identifiers)
            or len(set(identifiers)) != len(identifiers)):
        raise ValueError("Frozen family IDs must be unique and nonempty")
    actual = [row["test_id"] for row in results]
    if len(set(actual)) != len(actual) or not set(actual).issubset(identifiers):
        raise ValueError("Duplicate or unregistered result ID")
    if method not in {"BH", "BY"}:
        raise ValueError("Unsupported family method")
    lookup = {row["test_id"]: row for row in results}
    output = []
    for identifier in identifiers:
        row = dict(lookup.get(identifier, {"test_id": identifier, "raw_p": None, "status": "NOT_RUN"}))
        row["raw_p"] = probability(row["raw_p"])
        if row["raw_p"] is None and row.get("status") == "ESTIMATED":
            raise ValueError("ESTIMATED row cannot have missing raw P")
        if row["raw_p"] is not None and row.get("status") != "ESTIMATED":
            raise ValueError("Failed/unrun rows cannot carry a primary P")
        row["adjustment_p"] = 1.0 if row["raw_p"] is None else row["raw_p"]
        output.append(row)
    count = len(output)
    factor = sum(1 / rank for rank in range(1, count + 1)) if method == "BY" else 1.0
    # NOT_ESTIMABLE is a completed scientific outcome; only unfinished work
    # (NOT_RUN/FAILED) keeps the family formally incomplete and unqualified
    # for completion or disclosure.
    family_status = "INCOMPLETE" if any(row.get("status") in {"NOT_RUN", "FAILED"} for row in output) else "COMPLETE"
    order = sorted(range(count), key=lambda index: (output[index]["adjustment_p"], index))
    running = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        running = min(running, output[index]["adjustment_p"] * count * factor / rank)
        output[index]["q"] = running
        output[index]["family_size"] = count
        output[index]["correction"] = method
        output[index]["family_status"] = family_status
    return output


def signature_eligibility(members, matrix_ids, config):
    matrix = list(matrix_ids)
    if len(set(matrix)) != len(matrix) or any(not identifier for identifier in matrix):
        raise ValueError("Matrix gene IDs must be unique and nonempty")
    originals = {}
    targets = {}
    for row in members:
        original, direction, target = row["original_id"], row["direction"], row["matrix_id"]
        if not original or direction not in {"up", "down"}:
            raise ValueError("Invalid frozen signature member")
        if original in originals:
            if originals[original] != (direction, target):
                raise ValueError("Conflicting duplicate signature member")
            continue
        originals[original] = (direction, target)
        if target:
            if target in targets:
                raise ValueError("Mapping is not one-to-one; resolve before scoring")
            targets[target] = original
    if not originals:
        raise ValueError("Empty frozen signature")
    matrix_set = set(matrix)
    measured = {original for original, (_, target) in originals.items() if target in matrix_set}
    coverage = len(measured) / len(originals)
    directional = {}
    passed = len(measured) >= config["members_min"] and coverage >= config["coverage_min"]
    for direction in ("up", "down"):
        expected = {original for original, (arm, _) in originals.items() if arm == direction}
        present = expected & measured
        directional[direction] = {"original": len(expected), "measured": len(present),
                                  "coverage": len(present) / len(expected) if expected else None}
        if expected and len(present) / len(expected) < config["signed_arm_coverage_min"]:
            passed = False
    return {"eligible": passed, "original": len(originals), "measured": len(measured),
            "coverage": coverage, "directions": directional,
            "missing_original_ids": sorted(set(originals) - measured),
            "score_members": [{"gene": target, "direction": direction}
                              for original, (direction, target) in originals.items() if original in measured],
            "scope": "COVERAGE_ONLY_NOT_INPUT_SCALE_DONOR_OR_G0_ACCEPTANCE"}


def primary_rows(edges, decisions, results, rules):
    identifiers = [row["edge_id"] for row in edges]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("Edge universe identities invalid")
    if len(edges) != rules["planned_counts"]["A_PRIMARY_EDGES"] + rules["planned_counts"]["A_EXPANDED_EDGES"]:
        raise ValueError("Edge universe denominator mismatch")
    for family in ("A_PRIMARY_EDGES", "A_EXPANDED_EDGES"):
        if sum(row["family"] == family for row in edges) != rules["planned_counts"][family]:
            raise ValueError("Edge family denominator mismatch")
    decision_ids = [row["edge_id"] for row in decisions]
    result_ids = [row["edge_id"] for row in results]
    if (len(set(decision_ids)) != len(decision_ids) or set(decision_ids) != set(identifiers)
            or len(set(result_ids)) != len(result_ids) or not set(result_ids).issubset(identifiers)):
        raise ValueError("Decision/result edge identities invalid")
    decision_map = {row["edge_id"]: row for row in decisions}
    result_map = {row["edge_id"]: row for row in results}
    output = []
    for edge in edges:
        identifier = edge["edge_id"]
        decision = decision_map[identifier]
        result = result_map.get(identifier)
        if decision.get("status") != "FROZEN":
            selected = {"raw_p": None, "adjustment_p": 1.0, "primary_method": "NA",
                        "status": "NOT_RUN", "reason": "PRIMARY_DECISION_NOT_FROZEN"}
        else:
            for name in ("usual_eligible", "overlap_evidence", "mrlap_eligible"):
                required_flag(decision[name], name)
            execution = None if result is None else result.get("execution_status")
            if result is None:
                # No result record at all: the task never produced output. This is
                # an execution fact, not a scientific estimability verdict.
                selected = {"raw_p": None, "adjustment_p": 1.0, "primary_method": "NA",
                            "status": "NOT_RUN", "reason": "PRIMARY_RESULT_RECORD_MISSING"}
            elif execution in {"FAILED", "NOT_RUN"}:
                if any(result.get(key) is not None for key in ("ivw_p", "mrlap_p")):
                    raise ValueError(f"{execution} result record cannot carry a primary P")
                selected = {"raw_p": None, "adjustment_p": 1.0, "primary_method": "NA",
                            "status": execution, "reason": f"PRIMARY_EXECUTION_{execution}"}
            elif execution != "COMPLETED":
                raise ValueError("Result record must declare execution_status COMPLETED/FAILED/NOT_RUN")
            else:
                selected = select_primary(decision["overlap_class"], result.get("ivw_p"), result.get("mrlap_p"),
                                          usual_eligible=decision["usual_eligible"], overlap_evidence=decision["overlap_evidence"],
                                          mrlap_eligible=decision["mrlap_eligible"], rules=rules)
        output.append({"test_id": identifier, "exposure_id": edge["exposure_id"], "outcome_id": edge["outcome_id"],
                       "family": edge["family"], "overlap_class": decision["overlap_class"], **selected})
    return output


def path_rows(paths, edges, rules):
    identifiers = [row["path_id"] for row in paths]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("Path universe identities invalid")
    edge_ids = [row["test_id"] for row in edges]
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError("Duplicate primary edge result")
    lookup = {row["test_id"]: row for row in edges}
    output = []
    for path in paths:
        first, second = lookup.get(path["xm_edge_id"]), lookup.get(path["my_edge_id"])
        if first is None or second is None:
            raise ValueError("Path component edge missing from full ledger")
        if ((first["exposure_id"], first["outcome_id"]) != (path["x_id"], path["m_id"])
                or (second["exposure_id"], second["outcome_id"]) != (path["m_id"], path["y_id"])):
            raise ValueError("Path component construct identity mismatch")
        raw = [None if row["raw_p"] in (None, "NA", "") else probability(row["raw_p"]) for row in (first, second)]
        if any(value is not None and row["status"] != "ESTIMATED" for value, row in zip(raw, (first, second))):
            raise ValueError("Failed component cannot carry primary P")
        if any(value is None and row["status"] == "ESTIMATED" for value, row in zip(raw, (first, second))):
            raise ValueError("Estimated component cannot have missing P")
        statuses = [row["status"] for row in (first, second)]
        if any(value not in {"ESTIMATED", "NOT_ESTIMABLE", "NOT_RUN", "FAILED"} for value in statuses):
            raise ValueError("Component ledger status not registered")
        # Component execution states propagate verbatim: an unrun or technically
        # failed component never collapses into a scientific NOT_ESTIMABLE verdict.
        if "NOT_RUN" in statuses:
            combined, status, reason = None, "NOT_RUN", "COMPONENT_NOT_RUN"
        elif "FAILED" in statuses:
            combined, status, reason = None, "FAILED", "COMPONENT_FAILED"
        else:
            combined = joint_probability(raw, same_construct=True)
            status = "ESTIMATED" if combined is not None else "NOT_ESTIMABLE"
            reason = "COMPONENT_MAX" if combined is not None else "COMPONENT_NOT_ESTIMABLE"
        output.append({"test_id": path["path_id"], "family": path["family"],
                       "xm_edge_id": path["xm_edge_id"], "my_edge_id": path["my_edge_id"],
                       "component_statuses": ",".join(statuses),
                       "raw_p": combined, "status": status, "reason": reason})
    for family in ("A_PRIMARY_PATHS", "A_EXPANDED_PATHS"):
        selected = [row for row in output if row["family"] == family]
        if len(selected) != rules["planned_counts"][family]:
            raise ValueError("Path family denominator mismatch")
        adjusted = complete_family([row["test_id"] for row in selected], selected, method="BY")
        for target, row in zip(selected, adjusted):
            target.update(adjustment_p=row["adjustment_p"], q_by=row["q"], family_size=row["family_size"],
                          family_status=row["family_status"])
    if len(output) != sum(rules["planned_counts"][family] for family in ("A_PRIMARY_PATHS", "A_EXPANDED_PATHS")):
        raise ValueError("Unregistered path family")
    return output

def read_table(path):
    import csv
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        columns = reader.fieldnames or []
        rows = list(reader)
    if (not columns or len(set(columns)) != len(columns)
            or any(None in row or any(value is None for value in row.values()) for row in rows)):
        raise ValueError("Malformed contract TSV")
    return columns, rows


def write_table(path, columns, rows):
    import csv
    with open(path, "x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: "NA" if row[key] is None else row[key] for key in columns} for row in rows)


# Registered study protocols. The guards' consumed surface (planned counts,
# primary P policy, instrument rules) is byte-identical between these two
# contracts; only the governing identity differs. v4.0 is the frozen research
# contract; v4.1 is an engineering reference and never a research contract.
# The active protocol is an explicit per-invocation governance decision,
# never inferred from file layout or silently defaulted.
PROTOCOLS = {
    "4.0": {"role": "RESEARCH_CONTRACT"},
    "4.1": {"role": "ENGINEERING_REFERENCE_NOT_A_RESEARCH_CONTRACT"},
}


def resolve_active_protocol(config, environ):
    active = environ.get("CACHEXIA_ACTIVE_PROTOCOL")
    if not active:
        raise ValueError("Active study protocol is ungoverned: CACHEXIA_ACTIVE_PROTOCOL is required")
    if active not in PROTOCOLS:
        registered = ", ".join(sorted(PROTOCOLS))
        raise ValueError(f"Unknown study protocol {active!r}; registered: {registered}")
    declared = config.get("version")
    if declared != active:
        raise ValueError(f"Rules version {declared!r} does not match governed protocol {active!r}")
    return active


def main():
    import hashlib
    import json
    import os
    from pathlib import Path
    import sys
    operation = os.environ["CACHEXIA_OPERATION"]
    config_path = Path(os.environ["AUTONOMICS_INPUT0"])
    audit = {"operation": operation,
             "scientific_G0_granted": False, "scope": "EXECUTION_CONTRACT_ONLY_NOT_SCIENTIFIC_QUALIFICATION"}
    code = 0
    try:
        config_bytes = config_path.read_bytes()
        config = json.loads(config_bytes)
        audit["config_sha256"] = hashlib.sha256(config_bytes).hexdigest()
        if operation == "primary":
            active = resolve_active_protocol(config, os.environ)
            audit.update(active_protocol=active, active_protocol_role=PROTOCOLS[active]["role"],
                         rules_version=config["version"])
            request = json.loads(Path(os.environ["AUTONOMICS_INPUT1"]).read_text())
            _, registry = read_table(os.environ["AUTONOMICS_INPUT2"])
            output = primary_rows(registry, request["decisions"], request["results"], config)
            write_table(os.environ["AUTONOMICS_OUTPUT0"], list(output[0]), output)
            audit.update(rows=len(output), estimable=sum(row["status"] == "ESTIMATED" for row in output),
                         not_run=sum(row["status"] == "NOT_RUN" for row in output),
                         failed=sum(row["status"] == "FAILED" for row in output),
                         eligibility_attestations_verified=False)
        elif operation == "paths":
            active = resolve_active_protocol(config, os.environ)
            audit.update(active_protocol=active, active_protocol_role=PROTOCOLS[active]["role"],
                         rules_version=config["version"])
            _, primary = read_table(os.environ["AUTONOMICS_INPUT1"])
            _, registry = read_table(os.environ["AUTONOMICS_INPUT2"])
            output = path_rows(registry, primary, config)
            write_table(os.environ["AUTONOMICS_OUTPUT0"], list(output[0]), output)
            audit.update(rows=len(output), estimable=sum(row["status"] == "ESTIMATED" for row in output),
                         not_run=sum(row["status"] == "NOT_RUN" for row in output),
                         failed=sum(row["status"] == "FAILED" for row in output),
                         families_incomplete=len({row["family"] for row in output
                                                  if row["family_status"] == "INCOMPLETE"}))
        elif operation == "family":
            active = resolve_active_protocol(config, os.environ)
            audit.update(active_protocol=active, active_protocol_role=PROTOCOLS[active]["role"],
                         rules_version=config["version"])
            request = json.loads(Path(os.environ["AUTONOMICS_INPUT1"]).read_text())
            columns, registry = read_table(os.environ["AUTONOMICS_INPUT2"])
            family = request["family"]
            id_column = request["id_column"]
            if id_column not in {"edge_id", "path_id", "test_id", "analysis_id"} or id_column not in columns:
                raise ValueError("Frozen family ID column invalid")
            locked = [row[id_column] for row in registry if row["family"] == family]
            expected = config["planned_counts"].get(family, config["new_supportive_planned_counts"].get(family))
            if expected is None or len(locked) != expected:
                raise ValueError("Frozen family denominator mismatch")
            primary = complete_family(locked, request["results"], method="BH")
            sensitivity = complete_family(locked, request["results"], method="BY")
            output = [{**row, "q_bh": row["q"], "q_by": sensitivity[index]["q"]}
                      for index, row in enumerate(primary)]
            write_table(os.environ["AUTONOMICS_OUTPUT0"],
                        ["test_id", "raw_p", "status", "adjustment_p", "q_bh", "q_by",
                         "family_size", "family_status"], output)
            audit.update(family=family, family_size=len(locked),
                         family_status=primary[0]["family_status"],
                         required_primary_correction="BY" if "PATHS" in family else "BH")
        elif operation == "palindrome":
            active = resolve_active_protocol(config, os.environ)
            audit.update(active_protocol=active, active_protocol_role=PROTOCOLS[active]["role"],
                         rules_version=config["version"])
            columns, rows = read_table(os.environ["AUTONOMICS_INPUT1"])
            required = {"snp", "effect_allele_exposure", "other_allele_exposure",
                        "effect_allele_outcome", "other_allele_outcome",
                        "eaf_exposure", "eaf_outcome", "mr_keep"}
            if not required.issubset(columns) or len({row["snp"] for row in rows}) != len(rows):
                raise ValueError("Official harmonized row identities/schema invalid")
            eligible = []
            reasons = []
            for row in rows:
                if row["mr_keep"].lower() not in {"true", "false"}:
                    raise ValueError("mr_keep must retain official boolean semantics")
                aligned = (row["effect_allele_exposure"].upper() == row["effect_allele_outcome"].upper()
                           and row["other_allele_exposure"].upper() == row["other_allele_outcome"].upper())
                reason = palindrome_filter(row["effect_allele_exposure"], row["other_allele_exposure"],
                                           row["eaf_exposure"], row["eaf_outcome"], aligned=aligned, rules=config)
                if row["mr_keep"].lower() != "true":
                    reason = "EXCLUDE_OFFICIAL_HARMONIZER"
                if reason in {"PASS_THIS_FILTER_ONLY", "NONPALINDROMIC_REQUIRES_OTHER_QC"} and aligned:
                    eligible.append(row)
                elif reason == "NONPALINDROMIC_REQUIRES_OTHER_QC" and not aligned:
                    reason = "EXCLUDE_DIRECTION_UNRESOLVED"
                reasons.append({"snp": row["snp"], "reason": reason})
            write_table(os.environ["AUTONOMICS_OUTPUT0"], columns, eligible)
            audit.update(input_rows=len(rows), eligible_rows=len(eligible), variant_audit=reasons)
        elif operation == "signature":
            request = json.loads(Path(os.environ["AUTONOMICS_INPUT1"]).read_text())
            columns, matrix = read_table(os.environ["AUTONOMICS_INPUT2"])
            result = signature_eligibility(request["members"], [row[columns[0]] for row in matrix], config)
            write_table(os.environ["AUTONOMICS_OUTPUT0"], ["gene", "direction"], result["score_members"] if result["eligible"] else [])
            audit.update(result)
            if not result["eligible"]:
                raise ValueError("Frozen signature coverage/minimum failed; no scoring")
        else:
            raise ValueError("Unknown study guard")
        audit["status"] = "TECHNICAL_CONTRACT_PASS"
    except (ValueError, KeyError, TypeError, OSError) as error:
        audit.update(status="BLOCKED", error=str(error))
        code = 2
    Path(os.environ["AUTONOMICS_OUTPUT1"]).write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    Path(os.environ["AUTONOMICS_OUTPUT2"]).write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    if code:
        print(audit["error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
