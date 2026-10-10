import csv
import gzip
import hashlib
import json
import math
import os
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
import scipy
from scipy.stats import binomtest


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def table(path, required):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not set(required) <= set(reader.fieldnames):
            raise ValueError("missing or duplicate TSV column identities")
        rows = list(reader)
    if not rows or any(None in row or any(row[column] is None or not row[column].strip() for column in required) for row in rows):
        raise ValueError("empty, incomplete or ragged TSV records")
    if any(row[column] != row[column].strip() or any(character in row[column] for character in "\r\n\t") for row in rows for column in required):
        raise ValueError("ambiguous whitespace/control characters in TSV identities")
    return rows


def write_table(path, columns, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def check_hashes(request, paths):
    if request.get("input_sha256") != [digest(path) for path in paths]:
        raise ValueError("frozen input SHA256 identity differs")
    if request.get("network_type") != "physical" or request.get("namespace") not in ("STRING_PROTEIN_ID", "SYMBOL_CASE_SENSITIVE"):
        raise ValueError("physical network type and explicit namespace are required")
    if not request.get("provenance_attestation"):
        raise ValueError("network provenance attestation is required; metadata is not authentication")


def graph_and_sets(paths, request):
    if request.get("component_policy") != "REQUIRE_CONNECTED_EXACT_GRAPH" or request.get("distance_type") != "unweighted_shortest_path":
        raise ValueError("component and unweighted distance policies must be explicitly frozen")
    graph = nx.Graph()
    for row in table(paths[0], ("node_a", "node_b")):
        if row["node_a"] == row["node_b"]:
            raise ValueError("self-loop needs upstream explicit filtering")
        graph.add_edge(row["node_a"], row["node_b"])
    if not nx.is_connected(graph):
        raise ValueError("disconnected graph; no implicit largest-component selection")
    sets = defaultdict(set)
    for row in table(paths[1], ("set_id", "role", "node_id")):
        key = (row["role"], row["set_id"])
        if row["role"] not in ("S", "T") or row["node_id"] in sets[key]:
            raise ValueError("set role or duplicate member identity invalid")
        sets[key].add(row["node_id"])
    tests = request.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("predeclared test combinations are required")
    identities = []
    for test in tests:
        if set(test) != {"test_id", "set_s", "set_t", "measure"} or any(not isinstance(value, str) or not value for value in test.values()):
            raise ValueError("test identities invalid")
        if test["measure"] not in ("closest", "separation") or ("S", test["set_s"]) not in sets or ("T", test["set_t"]) not in sets:
            raise ValueError("unsupported measure or unknown registered set")
        identities.append(test["test_id"])
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate frozen test ID")
    if request.get("declared_test_ids") != identities:
        raise ValueError("frozen family test identities/order differ")
    return graph, sets, tests


def distance(lengths, source, target, measure):
    def nearest(first, second, exclude_self=False):
        if exclude_self and len(first) == 1:
            return [0.0]
        return [min(lengths[origin][destination] for destination in second if not exclude_self or origin != destination) for origin in first]

    first = nearest(source, target)
    if measure == "closest":
        return float(np.mean(first))
    return float(np.mean(first + nearest(target, source)) - (np.mean(nearest(source, source, True)) + np.mean(nearest(target, target, True))) / 2)


class ShortestPathLengths:
    def __init__(self, graph, capacity=128):
        self.graph = graph
        self.capacity = capacity
        self.cache = OrderedDict()

    def __getitem__(self, origin):
        if origin not in self.cache:
            self.cache[origin] = dict(nx.single_source_shortest_path_length(self.graph, origin))
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
        self.cache.move_to_end(origin)
        return self.cache[origin]


def distance_rows(graph, sets, tests):
    lengths = ShortestPathLengths(graph)
    rows = []
    for test in tests:
        source, target = sorted(sets[("S", test["set_s"])]), sorted(sets[("T", test["set_t"])])
        missing = sorted((set(source) | set(target)) - set(graph))
        rows.append({**test, "d_observed": "NA" if missing else distance(lengths, source, target, test["measure"]),
            "n_s": len(source), "n_t": len(target), "execution_status": "COMPLETED",
            "result_status": "NOT_ESTIMABLE" if missing else "ESTIMABLE", "reason": "OUTSIDE_FROZEN_GRAPH:" + json.dumps(missing) if missing else ""})
    return lengths, rows


def randomization(graph, sets, tests, lengths, observed, background, request, draws_path, pool_path):
    count = int(os.environ["CN_N_RANDOM"])
    seed = int(os.environ["CN_SEED"])
    if type(request.get("n_random")) is not int or type(request.get("seed")) is not int or count != request["n_random"] or seed != request["seed"] or count < 10000 or seed < 0 or seed > 2147483647:
        raise ValueError("frozen n_random/seed differ or outside the scoped budget")
    resolution, maximum_se = request.get("p_resolution"), request.get("max_mc_se_worst_case")
    if type(resolution) not in (float, int) or type(maximum_se) not in (float, int) or not 0 < resolution < 1 or not 0 < maximum_se < 1:
        raise ValueError("explicit positive Monte Carlo precision budgets required")
    if 1 / (count + 1) > resolution or .5 / math.sqrt(count) > maximum_se:
        raise ValueError("locked randomization count cannot satisfy predeclared Monte Carlo precision")
    if request.get("matching") != "DEGREE_EXPRESSION_DETECTABILITY" or request.get("exclude_original_seeds") != "ALL_REGISTERED_SEED_NODES" or request.get("overlap_policy") != "INDEPENDENT_BETWEEN_ROLES" or type(request.get("null_sd_ddof")) is not int or request["null_sd_ddof"] != 0:
        raise ValueError("joint matching, seed exclusion, overlap and null SD policies must be explicit")
    width = request.get("degree_bin_width")
    if type(width) is not int or width < 1 or not request.get("background_strata_attestation"):
        raise ValueError("degree width and expression/detectability strata provenance required")
    originals = set().union(*sets.values())
    strata, eligible, pools, ledger = {}, set(), defaultdict(list), []
    for row in background:
        node = row["node_id"]
        if node in strata or row["eligible"] not in ("true", "false"):
            raise ValueError("background duplicate or invalid eligibility")
        if row["eligible"] == "true" and node not in graph:
            raise ValueError("eligible background node absent from frozen graph")
        degree = graph.degree(node) if node in graph else None
        strata[node] = (degree // width if degree is not None else None, row["expression_bin"], row["detectability_bin"])
        if row["eligible"] == "true":
            eligible.add(node)
            if node not in originals:
                pools[strata[node]].append(node)
        ledger.append({"node_id": node, "degree": "NA" if degree is None else degree,
            "degree_bin": "NA" if degree is None else degree // width, "expression_bin": row["expression_bin"],
            "detectability_bin": row["detectability_bin"], "eligible": row["eligible"], "excluded_original_seed": str(node in originals).lower()})
    write_table(pool_path, list(ledger[0]), sorted(ledger, key=lambda row: row["node_id"]))
    pools = {key: sorted(value) for key, value in pools.items()}
    output, draws = [], []
    for test, row in zip(tests, observed, strict=True):
        source, target = sorted(sets[("S", test["set_s"])]), sorted(sets[("T", test["set_t"])])
        row = dict(row)
        row.update({column: "NA" for column in ("d_rand_mean", "d_rand_sd", "z", "p_lower_raw", "p_upper_raw", "mc_se_lower", "mc_se_upper", "lower_ci_low", "lower_ci_high", "upper_ci_low", "upper_ci_high")})
        row.update(n_random_used=0, p_lower_for_adjustment=1.0, p_upper_for_adjustment=1.0)
        if row["result_status"] == "ESTIMABLE" and not (set(source) | set(target)) <= eligible:
            row.update(result_status="NOT_ESTIMABLE", reason="SEED_NOT_IN_ELIGIBLE_BACKGROUND")
        requirements = [Counter(strata[node] for node in members) for members in (source, target)] if row["result_status"] == "ESTIMABLE" else []
        if requirements and any(len(pools.get(key, [])) < needed for counts in requirements for key, needed in counts.items()):
            row.update(result_status="NOT_ESTIMABLE", reason="INSUFFICIENT_JOINT_MATCHED_POOL")
        if row["result_status"] == "NOT_ESTIMABLE":
            row["d_observed"] = "NA"
            output.append(row)
            continue
        identity = hashlib.sha256(test["test_id"].encode()).digest()
        entropy = [seed, *[int.from_bytes(identity[index:index + 4], "little") for index in range(0, 16, 4)]]
        rng = np.random.default_rng(np.random.SeedSequence(entropy))
        null = []
        for draw in range(count):
            selected = [sorted(node for key, needed in sorted(counts.items()) for node in rng.choice(pools[key], size=needed, replace=False).tolist()) for counts in requirements]
            value = distance(lengths, *selected, test["measure"])
            null.append(value)
            draws.append({"test_id": test["test_id"], "draw": draw, "s_nodes_json": json.dumps(selected[0]), "t_nodes_json": json.dumps(selected[1]), "d_null": value})
        values = np.asarray(null)
        mean, sd = float(values.mean()), float(values.std(ddof=0))
        row.update(d_rand_mean=mean, d_rand_sd=sd, z=(row["d_observed"] - mean) / sd if sd > 0 else "NA", n_random_used=count)
        for tail, hits in (("lower", int((values <= row["d_observed"]).sum())), ("upper", int((values >= row["d_observed"]).sum()))):
            probability = (hits + 1) / (count + 1)
            interval = binomtest(hits, count).proportion_ci(confidence_level=.95, method="exact")
            row.update({f"p_{tail}_raw": probability, f"p_{tail}_for_adjustment": probability,
                f"mc_se_{tail}": math.sqrt(probability * (1 - probability) / (count + 1)),
                f"{tail}_ci_low": interval.low, f"{tail}_ci_high": interval.high})
        if sd == 0:
            row["reason"] = "ZERO_NULL_VARIANCE_Z_UNDEFINED"
        output.append(row)
    write_table(draws_path, ("test_id", "draw", "s_nodes_json", "t_nodes_json", "d_null"), draws)
    return output


def physical_filter(paths, request):
    organism, release = request.get("organism"), request.get("release")
    if request.get("namespace") != "STRING_PROTEIN_ID" or not isinstance(organism, str) or not organism.isdigit() or release != "12.0":
        raise ValueError("scoped STRING 12.0 organism/namespace invalid")
    expected = [f"https://stringdb-downloads.org/download/protein.physical.links.v{release}/{organism}.protein.physical.links.v{release}.txt.gz",
        f"https://stringdb-downloads.org/download/protein.info.v{release}/{organism}.protein.info.v{release}.txt.gz"]
    if request.get("source_urls") != expected or request.get("evidence_policy") != "PHYSICAL_COMBINED_SCORE_ALL_CHANNELS" or request.get("self_loop_policy") != "DROP_WITH_LEDGER":
        raise ValueError("physical source URLs/evidence/self-loop policy differ; channel-specific restriction requires another input")
    threshold = request.get("min_score")
    if type(threshold) is not int or not 0 <= threshold <= 1000:
        raise ValueError("STRING combined score threshold must be an integer in [0,1000]")
    info = {}
    with gzip.open(paths[1], "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not {"#string_protein_id", "preferred_name"} <= set(reader.fieldnames):
            raise ValueError("STRING protein info header invalid")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("ragged STRING protein info record")
            node, name = row["#string_protein_id"], row["preferred_name"]
            if not node or not name or node in info or not node.startswith(organism + "."):
                raise ValueError("STRING info identifier missing/duplicate/wrong organism")
            info[node] = name
    if not info:
        raise ValueError("empty STRING protein info")
    edges, counts = {}, Counter()
    with gzip.open(paths[0], "rt", encoding="utf-8") as stream:
        if stream.readline().split() != ["protein1", "protein2", "combined_score"]:
            raise ValueError("STRING physical combined-score header invalid")
        for line in stream:
            fields = line.split()
            if len(fields) != 3 or not fields[2].isdigit() or not 0 <= int(fields[2]) <= 1000:
                raise ValueError("malformed STRING physical edge/score")
            first, second, score = fields[0], fields[1], int(fields[2])
            if first not in info or second not in info:
                raise ValueError("physical endpoint absent from frozen protein info")
            counts["raw_records"] += 1
            if score < threshold:
                counts["below_threshold"] += 1
                continue
            if first == second:
                counts["self_loops_dropped"] += 1
                continue
            key = tuple(sorted((first, second)))
            if key in edges and edges[key] != score:
                raise ValueError("discordant reciprocal physical edge scores")
            if key in edges:
                counts["duplicate_edges_collapsed"] += 1
            edges[key] = score
    if not edges:
        raise ValueError("no qualifying physical edges")
    rows = [{"node_a": first, "node_b": second, "combined_score": score} for (first, second), score in sorted(edges.items())]
    write_table(os.environ["AUTONOMICS_OUTPUT0"], ("node_a", "node_b", "combined_score"), rows)
    write_table(os.environ["AUTONOMICS_OUTPUT1"], ("node_id", "preferred_name"), [{"node_id": node, "preferred_name": name} for node, name in sorted(info.items())])
    return {"counts": dict(counts), "kept_undirected_edges": len(rows), "preferred_name_collisions": sum(value - 1 for value in Counter(info.values()).values()),
        "preferred_names_not_used_as_edge_identifiers": True, "score_is_string_confidence_not_effect_size": True,
        "download_authenticity_is_attestation_not_machine_certification": True}


def run():
    mode = os.environ["CN_MODE"]
    if mode not in ("distance", "null", "string_filter"):
        raise ValueError("unknown network execution mode")
    paths = [os.environ[f"AUTONOMICS_INPUT{port}"] for port in range(3 if mode == "null" else 2)]
    request = json.loads(Path(os.environ[f"AUTONOMICS_INPUT{len(paths)}"]).read_text())
    check_hashes(request, paths)
    audit = {"execution_status": "COMPLETED", "scientific_release": False, "g0_granted": False, "mode": mode,
        "input_sha256": [digest(path) for path in paths], "request_sha256": digest(os.environ[f"AUTONOMICS_INPUT{len(paths)}"]),
        "network_provenance_and_strata_are_attestations": True,
        "engine": {"networkx": nx.__version__, "numpy": np.__version__, "scipy": scipy.__version__}, "research_family_adjustment_performed": False}
    if mode == "string_filter":
        audit.update(physical_filter(paths, request))
    else:
        graph, sets, tests = graph_and_sets(paths, request)
        lengths, rows = distance_rows(graph, sets, tests)
        if mode == "null":
            rows = randomization(graph, sets, tests, lengths, rows, table(paths[2], ("node_id", "expression_bin", "detectability_bin", "eligible")), request,
                os.environ["AUTONOMICS_OUTPUT1"], os.environ["AUTONOMICS_OUTPUT2"])
            audit.update(n_random=request["n_random"], seed=request["seed"],
                mc_ci="Clopper-Pearson 95% interval for raw binomial exceedance probability, NOT corrected p CI or family significance",
                mc_se="approximate add-one-smoothed empirical tail SE; not SE of the null-distance mean",
                null_model="study joint-stratified null, NOT author Guney degree-only sampler",
                cross_role_overlap="independent draws; observed S/T intersection size is NOT preserved",
                zero_null_variance_z="NA; empirical tails remain reported")
        write_table(os.environ["AUTONOMICS_OUTPUT0"], list(rows[0]), rows)
        audit.update(test_ids=[row["test_id"] for row in rows], network_nodes=len(graph), network_edges=graph.number_of_edges(),
            shortest_path_cache_max_sources=lengths.capacity,
            estimable=sum(row["result_status"] == "ESTIMABLE" for row in rows), nonestimable=sum(row["result_status"] == "NOT_ESTIMABLE" for row in rows))
    report_port = 3 if mode == "null" else 2 if mode == "string_filter" else 1
    Path(os.environ[f"AUTONOMICS_OUTPUT{report_port}"]).write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        mode = os.environ.get("CN_MODE")
        report_port = 3 if mode == "null" else 2 if mode == "string_filter" else 1
        for port in range(report_port):
            path = os.environ.get(f"AUTONOMICS_OUTPUT{port}")
            if path:
                Path(path).unlink(missing_ok=True)
        report = os.environ.get(f"AUTONOMICS_OUTPUT{report_port}")
        if report:
            Path(report).write_text(json.dumps({"execution_status": "FAILED", "status": "BLOCKED", "error": str(error), "scientific_release": False, "g0_granted": False}, indent=2) + "\n")
        raise SystemExit(2)
