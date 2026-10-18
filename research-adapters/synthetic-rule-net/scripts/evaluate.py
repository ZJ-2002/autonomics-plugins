"""Synthetic finite synchronous rule networks, schema 2.

Tables specify next states by default; rule_semantics=target_unit_step moves
at most one unit toward each table target, using the previous synchronous state.
Inputs require an explicit value or clamp. No implicit zero and no anchor file.
Attractor readouts summarize periods; only a unique fixed point supplies a
point prediction by default. A unique cycle requires explicit period_mean
policy; multiple attractors never select an arbitrary point. No biological
qualification or complete BMA compatibility is claimed. See README.md.
"""

import itertools
import json
import os
import sys
from pathlib import Path

IMPLEMENTATION_VERSION = "2.0.0"
SCHEMA_VERSION = 2
DEFAULT_MAX_NODES = 6
DEFAULT_MAX_STEPS = 64
NODE_KINDS = ("rule", "input", "constant")


class SpecError(Exception):
    """Structured fail-closed error; str(err) == "<CLASS>: <detail>"."""

    def __init__(self, cls, detail):
        super().__init__("%s: %s" % (cls, detail))
        self.cls = cls


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _known_fields(value, allowed, label):
    if not isinstance(value, dict):
        raise SpecError("OUT_OF_DECLARED_SCOPE", "%s must be an object" % label)
    if set(value) - set(allowed):
        raise SpecError("OUT_OF_DECLARED_SCOPE", "unknown field in %s" % label)


def parse_spec(raw):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite JSON constant")

    try:
        spec = json.loads(raw, object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except Exception as exc:  # noqa: BLE001 - sanitized, no echo of content
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "spec is not valid JSON (%s)" % type(exc).__name__)
    if not isinstance(spec, dict):
        raise SpecError("OUT_OF_DECLARED_SCOPE", "spec must be a JSON object")
    return spec


class Model(object):
    __slots__ = ("name", "max_nodes", "max_steps", "ids", "kinds", "domains",
                 "rules", "defaults", "required", "readout_type",
                 "readout_nodes", "baseline_clamps", "intervention_clamps",
                 "per_node_init", "rule_semantics", "cycle_policy")


def _validate_clamps(clamps, model, arm):
    if not isinstance(clamps, dict):
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "%s clamps must be an object" % arm)
    clean = {}
    for key, value in clamps.items():
        if key not in model.ids:
            raise SpecError("DANGLING_REFERENCE",
                            "%s clamps reference unknown node %r" % (arm, key))
        if not _is_int(value) or not 0 <= value < model.domains[key]:
            raise SpecError("ILLEGAL_STATE_VALUE",
                            "%s clamp value %r outside node %r %d-state domain"
                            % (arm, value, key, model.domains[key]))
        clean[key] = int(value)
    return clean


def build_model(spec):
    _known_fields(spec, {"name", "rule_semantics", "nodes", "state_domains",
                        "update", "max_nodes", "max_steps", "readout",
                        "clamps", "intervention", "initial_states"}, "spec")
    model = Model()
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "spec.name must be a non-empty string")
    model.name = name

    model.rule_semantics = spec.get("rule_semantics", "next_state")
    if model.rule_semantics not in ("next_state", "target_unit_step"):
        raise SpecError("OUT_OF_DECLARED_SCOPE", "unknown rule_semantics")
    readout_spec = spec.get("readout", {})
    model.cycle_policy = (readout_spec.get("cycle_policy", "unresolved")
                          if isinstance(readout_spec, dict) else "unresolved")
    if model.cycle_policy not in ("unresolved", "period_mean"):
        raise SpecError("OUT_OF_DECLARED_SCOPE", "unknown readout.cycle_policy")

    update = spec.get("update", "synchronous")
    if update != "synchronous":
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "update %r is not implemented; only 'synchronous' is "
                        "declared in scope" % (update,))

    max_nodes = spec.get("max_nodes", DEFAULT_MAX_NODES)
    if not _is_int(max_nodes) or max_nodes < 1:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "max_nodes must be a positive integer")
    max_steps = spec.get("max_steps", DEFAULT_MAX_STEPS)
    if not _is_int(max_steps) or max_steps < 1:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "max_steps must be a positive integer")
    model.max_nodes, model.max_steps = max_nodes, max_steps

    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "spec.nodes must be a non-empty array")
    if len(nodes) > max_nodes:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "node count %d exceeds declared max_nodes %d"
                        % (len(nodes), max_nodes))

    ids, kinds = [], {}
    for entry in nodes:
        if not isinstance(entry, dict):
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "each node must be an object")
        nid = entry.get("id")
        if not isinstance(nid, str) or not nid:
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "each node needs a non-empty string id")
        if nid in kinds:
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "duplicate node id %r" % nid)
        kind = entry.get("kind")
        if kind not in NODE_KINDS:
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "node %r has unknown kind %r (declared: "
                            "rule|input|constant)" % (nid, kind))
        _known_fields(entry, {"id", "kind"} | {
            "rule": {"parents", "table"},
            "input": {"value", "required"},
            "constant": {"value"},
        }[kind], "node")
        ids.append(nid)
        kinds[nid] = kind
    model.ids, model.kinds = ids, kinds

    raw_domains = spec.get("state_domains", {})
    if not isinstance(raw_domains, dict):
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "state_domains must be an object")
    for key, size in raw_domains.items():
        if key not in kinds:
            raise SpecError("DANGLING_REFERENCE",
                            "state_domains references unknown node %r" % key)
        if not _is_int(size) or not 2 <= size <= 4:
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "node %r declares domain size %r; only 2..4 "
                            "discrete states are in declared scope"
                            % (key, size))
    model.domains = {nid: int(raw_domains.get(nid, 2)) for nid in ids}

    rules, defaults, required = {}, {}, set()
    for entry in nodes:
        nid, kind = entry["id"], entry["kind"]
        domain = model.domains[nid]
        if kind == "constant":
            for bad in ("parents", "table"):
                if bad in entry:
                    raise SpecError("OUT_OF_DECLARED_SCOPE",
                                    "constant node %r must not declare %r"
                                    % (nid, bad))
            if "value" not in entry:
                raise SpecError("OUT_OF_DECLARED_SCOPE",
                                "constant node %r must declare value" % nid)
            value = entry["value"]
            if not _is_int(value) or not 0 <= value < domain:
                raise SpecError("ILLEGAL_STATE_VALUE",
                                "constant node %r value %r outside its "
                                "%d-state domain" % (nid, value, domain))
            defaults[nid] = int(value)
        elif kind == "input":
            for bad in ("parents", "table"):
                if bad in entry:
                    raise SpecError("OUT_OF_DECLARED_SCOPE",
                                    "input node %r must not declare %r"
                                    % (nid, bad))
            flag = entry.get("required", False)
            if not isinstance(flag, bool):
                raise SpecError("OUT_OF_DECLARED_SCOPE",
                                "input node %r required flag must be boolean"
                                % nid)
            if flag:
                required.add(nid)
            if "value" in entry:
                value = entry["value"]
                if not _is_int(value) or not 0 <= value < domain:
                    raise SpecError("ILLEGAL_STATE_VALUE",
                                    "input node %r default outside its domain" % nid)
                defaults[nid] = int(value)
        else:  # rule
            if "parents" not in entry or "table" not in entry:
                raise SpecError("INCOMPLETE_RULE",
                                "rule node %r must declare both parents and "
                                "table" % nid)
            parents = entry["parents"]
            if (not isinstance(parents, list)
                    or not all(isinstance(p, str) and p for p in parents)):
                raise SpecError("OUT_OF_DECLARED_SCOPE",
                                "rule node %r parents must be an array of "
                                "node ids" % nid)
            for parent in parents:
                if parent not in kinds:
                    raise SpecError("DANGLING_REFERENCE",
                                    "rule node %r references unknown parent %r"
                                    % (nid, parent))
            table = entry["table"]
            if not isinstance(table, dict) or not table:
                raise SpecError("INCOMPLETE_RULE",
                                "rule node %r table must be a non-empty "
                                "object" % nid)
            for combo in itertools.product(
                    *[range(model.domains[p]) for p in parents]):
                key = ",".join(str(v) for v in combo)
                if key not in table:
                    raise SpecError("INCOMPLETE_RULE",
                                    "rule node %r table misses parent "
                                    "combination %r" % (nid, key))
            lookup = {}
            for key, out in table.items():
                parts = [] if key == "" else key.split(",")
                if len(parts) != len(parents):
                    raise SpecError("OUT_OF_DECLARED_SCOPE",
                                    "rule node %r table key %r has wrong arity "
                                    "for parents %r" % (nid, key, parents))
                values = []
                for part in parts:
                    if not part.lstrip("-").isdigit():
                        raise SpecError("OUT_OF_DECLARED_SCOPE",
                                        "rule node %r table key %r is not "
                                        "integer-encoded" % (nid, key))
                    values.append(int(part))
                if key != ",".join(str(v) for v in values):
                    raise SpecError("OUT_OF_DECLARED_SCOPE",
                                    "table keys must use canonical integers")
                for parent, pv in zip(parents, values):
                    if not 0 <= pv < model.domains[parent]:
                        raise SpecError("ILLEGAL_STATE_VALUE",
                                        "rule node %r table key %r uses value "
                                        "%d outside parent %r domain"
                                        % (nid, key, pv, parent))
                if not _is_int(out) or not 0 <= out < domain:
                    raise SpecError("ILLEGAL_STATE_VALUE",
                                    "rule node %r table output %r for key %r "
                                    "outside its %d-state domain"
                                    % (nid, out, key, domain))
                lookup[tuple(values)] = int(out)
            rules[nid] = {"parents": list(parents), "table": lookup}
    model.rules, model.defaults, model.required = rules, defaults, required

    readout = spec.get("readout")
    if not isinstance(readout, dict):
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "spec.readout must be an object")
    rtype = readout.get("type")
    _known_fields(readout, {"type", "cycle_policy"} |
                  ({"nodes"} if rtype == "mean_nodes" else {"node"}), "readout")
    if rtype == "mean_nodes":
        rnodes = readout.get("nodes")
        if (not isinstance(rnodes, list) or not rnodes
                or not all(isinstance(x, str) and x for x in rnodes)):
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "mean_nodes readout needs a non-empty nodes "
                            "array of node ids")
    elif rtype == "node_value":
        rnode = readout.get("node")
        if not isinstance(rnode, str) or not rnode:
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "node_value readout needs a node id")
        rnodes = [rnode]
    else:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "unknown readout type %r (declared: mean_nodes | "
                        "node_value)" % (rtype,))
    for node in rnodes:
        if node not in kinds:
            raise SpecError("DANGLING_REFERENCE",
                            "readout references unknown node %r" % node)
    model.readout_type, model.readout_nodes = rtype, list(rnodes)

    model.baseline_clamps = _validate_clamps(spec.get("clamps", {}), model,
                                             "baseline")
    intervention = spec.get("intervention")
    model.intervention_clamps = None
    if intervention is not None:
        if not isinstance(intervention, dict):
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "intervention must be an object")
        _known_fields(intervention, {"clamps"}, "intervention")
        merged = dict(model.baseline_clamps)
        merged.update(_validate_clamps(intervention.get("clamps", {}), model,
                                       "intervention"))
        model.intervention_clamps = merged

    arms = [("baseline", model.baseline_clamps)]
    if model.intervention_clamps is not None:
        arms.append(("intervention", model.intervention_clamps))
    for arm_name, clamps in arms:
        unknown_inputs = {nid for nid in ids if kinds[nid] == "input"
                          and nid not in defaults}
        missing = sorted((model.required | unknown_inputs) - set(clamps))
        if missing:
            raise SpecError("MISSING_REQUIRED_INPUT",
                            "%s arm has unresolved input(s) or missing required clamp(s): %s"
                            % (arm_name, ", ".join(missing)))

    init = spec.get("initial_states", "exhaustive")
    per_node_init = {}
    if init == "exhaustive":
        pass
    elif isinstance(init, dict):
        for key, values in init.items():
            if key not in kinds:
                raise SpecError("DANGLING_REFERENCE",
                                "initial_states references unknown node %r"
                                % key)
            if kinds[key] != "rule":
                raise SpecError("OUT_OF_DECLARED_SCOPE",
                                "initial_states may only enumerate rule "
                                "nodes; %r has kind %r"
                                % (key, kinds[key]))
            if not isinstance(values, list) or not values:
                raise SpecError("OUT_OF_DECLARED_SCOPE",
                                "initial_states for %r must be a non-empty "
                                "array" % key)
            for value in values:
                if not _is_int(value) or not 0 <= value < model.domains[key]:
                    raise SpecError("ILLEGAL_STATE_VALUE",
                                    "initial state value %r outside node %r "
                                    "%d-state domain"
                                    % (value, key, model.domains[key]))
            per_node_init[key] = sorted({int(v) for v in values})
    else:
        raise SpecError("OUT_OF_DECLARED_SCOPE",
                        "initial_states must be 'exhaustive' or an object "
                        "mapping rule nodes to value arrays")
    for key in per_node_init:
        if key in model.baseline_clamps or (
                model.intervention_clamps is not None
                and key in model.intervention_clamps):
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "initial_states enumerates node %r which is "
                            "clamped in at least one arm" % key)
    model.per_node_init = per_node_init
    return model


def _canonical_cycle(cycle):
    """Rotation-invariant identity of a periodic state sequence."""
    k = len(cycle)
    return min(tuple(cycle[(i + j) % k] for i in range(k)) for j in range(k))


def simulate_arm(model, clamps):
    """Explore one arm: fixed nodes held, free rule nodes enumerated."""
    fixed = {}
    for nid in model.ids:
        if nid in clamps:
            fixed[nid] = clamps[nid]
        elif nid in model.defaults:
            fixed[nid] = model.defaults[nid]
    all_ids = sorted(model.ids)
    pos = {nid: i for i, nid in enumerate(all_ids)}
    free_ids = [nid for nid in all_ids if nid not in fixed]
    transitions = [(pos[nid], tuple(pos[p] for p in model.rules[nid]["parents"]),
                    model.rules[nid]["table"]) for nid in free_ids]
    state_space = 1
    for nid in free_ids:
        state_space *= model.domains[nid]
    init_sets = [model.per_node_init.get(nid, list(range(model.domains[nid])))
                 for nid in free_ids]

    initials = []
    for combo in itertools.product(*init_sets):
        # Free rule nodes are filled from the combo; all other nodes are fixed.
        state = [fixed.get(nid, 0) for nid in all_ids]
        for nid, value in zip(free_ids, combo):
            state[pos[nid]] = value
        initials.append(tuple(state))

    def full_dict(state):
        return {nid: state[pos[nid]] for nid in all_ids}

    def step(state):
        nxt = list(state)
        for target, pidx, table in transitions:
            value = table[tuple(state[j] for j in pidx)]
            if model.rule_semantics == "target_unit_step":
                value = state[target] + (value > state[target]) - (value < state[target])
            nxt[target] = value
        return tuple(nxt)

    attractors, by_key = [], {}
    for index, s0 in enumerate(initials):
        seen = {s0: 0}
        traj = [s0]
        current, cycle = s0, None
        for _ in range(model.max_steps):
            current = step(current)
            if current in seen:
                start = seen[current]
                cycle = traj[start:]
                transient = start
                break
            seen[current] = len(traj)
            traj.append(current)
        if cycle is None:
            # Unreachable when state_space <= max_steps (pigeonhole).
            raise SpecError("RESOURCE_BUDGET_EXCEEDED",
                            "trajectory from initial state #%d did not close "
                            "within max_steps=%d transitions (reachable "
                            "state space %d)"
                            % (index, model.max_steps, state_space))
        key = _canonical_cycle(cycle)
        if key in by_key:
            attractor = attractors[by_key[key]]
            attractor["reached_from"].append(index)
            attractor["transient_steps"].append(transient)
        else:
            by_key[key] = len(attractors)
            attractors.append({"cycle": key, "reached_from": [index],
                               "transient_steps": [transient]})

    reported = []
    for attractor in sorted(attractors, key=lambda a: a["cycle"]):
        states = [full_dict(s) for s in attractor["cycle"]]
        if model.readout_type == "mean_nodes":
            values = [sd[n] for sd in states for n in model.readout_nodes]
        else:
            values = [sd[model.readout_nodes[0]] for sd in states]
        length = len(states)
        reported.append({
            "type": "FIXED_POINT" if length == 1 else "CYCLE",
            "cycle_length": length,
            "states": states,
            "readout": round(sum(values) / len(values), 12),
            "readout_kind": "fixed_point" if length == 1 else "period_mean",
            "state_readout_range": [
                min(sum(sd[n] for n in model.readout_nodes) / len(model.readout_nodes)
                    for sd in states),
                max(sum(sd[n] for n in model.readout_nodes) / len(model.readout_nodes)
                    for sd in states)],
            "reached_from": attractor["reached_from"],
            "transient_steps": attractor["transient_steps"],
        })

    unique = len(reported) == 1
    has_cycle = any(a["type"] == "CYCLE" for a in reported)
    point_allowed = unique and (not has_cycle or model.cycle_policy == "period_mean")
    summaries = sorted({a["readout"] for a in reported})
    return {
        "clamps": {k: clamps[k] for k in sorted(clamps)},
        "resolved_inputs": {
            nid: {"value": fixed[nid],
                  "source": "clamp" if nid in clamps else "explicit_value"}
            for nid in all_ids if model.kinds[nid] == "input"},
        "state_space_size": state_space,
        "initial_states": [full_dict(s) for s in initials],
        "attractors": reported,
        "fixed_points": [a["states"][0] for a in reported
                         if a["cycle_length"] == 1],
        "multi_stable": len(reported) > 1,
        "readout": reported[0]["readout"] if point_allowed else None,
        "point_prediction_allowed": point_allowed,
        "readout_from": ("multiple_attractors" if not unique else
                         "explicit_period_mean" if has_cycle and point_allowed else
                         "unresolved_cycle" if has_cycle else "unique_fixed_point"),
        "attractor_readout_values": summaries,
        "attractor_readout_range": [min(summaries), max(summaries)],
    }


def evaluate(spec):
    model = build_model(spec)
    result = {
        "schema_version": SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "name": model.name,
        "update": "synchronous",
        "rule_semantics": model.rule_semantics,
        "cycle_policy": model.cycle_policy,
        "max_nodes": model.max_nodes,
        "max_steps": model.max_steps,
        "readout_type": model.readout_type,
        "readout_nodes": list(model.readout_nodes),
        "state_domains": {nid: model.domains[nid] for nid in sorted(model.ids)},
        "arms": {"baseline": simulate_arm(model, model.baseline_clamps)},
        "delta": None,
    }
    if model.intervention_clamps is not None:
        baseline = result["arms"]["baseline"]
        intervened = simulate_arm(model, model.intervention_clamps)
        result["arms"]["intervention"] = intervened
        result["delta"] = {
            "baseline_readout": baseline["readout"],
            "intervention_readout": intervened["readout"],
            "delta": (round(intervened["readout"] - baseline["readout"], 12)
                      if baseline["point_prediction_allowed"]
                      and intervened["point_prediction_allowed"] else None),
            "point_prediction_allowed": (baseline["point_prediction_allowed"]
                                         and intervened["point_prediction_allowed"]),
        }
    return result


def render_tsv(result):
    lines = ["arm\tattractor_index\ttype\tcycle_length\treadout_summary\tstates\t"
             "reached_from_count"]
    for arm_name in ("baseline", "intervention"):
        arm = result["arms"].get(arm_name)
        if arm is None:
            continue
        for i, attractor in enumerate(arm["attractors"]):
            states = "|".join(";".join("%s=%s" % (k, sd[k])
                                       for k in sorted(sd))
                              for sd in attractor["states"])
            lines.append("\t".join([
                arm_name, str(i), attractor["type"],
                str(attractor["cycle_length"]), str(attractor["readout"]),
                states, str(len(attractor["reached_from"]))]))
    return "\n".join(lines) + "\n"


def main():
    out_json = Path(os.environ.get("AUTONOMICS_OUTPUT0", "result.json"))
    out_tsv = Path(os.environ.get("AUTONOMICS_OUTPUT1", "summary.tsv"))
    try:
        raw = os.environ.get("RULENET_SPEC")
        if raw is None or not raw.strip():
            raise SpecError("OUT_OF_DECLARED_SCOPE",
                            "RULENET_SPEC env must carry the JSON spec; it is "
                            "empty")
        result = evaluate(parse_spec(raw))
    except SpecError as err:
        # Fail closed: remove partial outputs, class-prefixed stderr, exit 2.
        out_json.unlink(missing_ok=True)
        out_tsv.unlink(missing_ok=True)
        print(str(err), file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - internal defect, sanitized, exit 3
        # Never echo spec-derived tracebacks into logs; outputs stay absent.
        out_json.unlink(missing_ok=True)
        out_tsv.unlink(missing_ok=True)
        print("INTERNAL_ERROR: synthetic-rule-net evaluator failed on the "
              "declared spec; see plugin workspace for reproduction",
              file=sys.stderr)
        return 3
    payload = json.dumps(result, sort_keys=True, indent=2,
                         ensure_ascii=False) + "\n"
    tsv = render_tsv(result)
    for path, text in ((out_json, payload), (out_tsv, tsv)):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    # Run metadata goes to stdout only; never into the output files.
    baseline = result["arms"]["baseline"]
    print("synthetic-rule-net name=%s implementation_version=%s"
          % (result["name"], IMPLEMENTATION_VERSION))
    print("baseline: initial_states=%d attractors=%d multi_stable=%s"
          % (len(baseline["initial_states"]), len(baseline["attractors"]),
             baseline["multi_stable"]))
    if "intervention" in result["arms"]:
        arm = result["arms"]["intervention"]
        print("intervention: initial_states=%d attractors=%d multi_stable=%s"
              % (len(arm["initial_states"]), len(arm["attractors"]),
                 arm["multi_stable"]))
    if result["delta"] is not None:
        print("delta=%s" % result["delta"]["delta"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
