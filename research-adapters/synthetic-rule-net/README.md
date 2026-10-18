# synthetic-rule-net

Synthetic-only finite synchronous rule-network reference evaluator, version
2.0.0, result schema 2. Standard-library Python, zero file inputs, two outputs:
`result.json` and `summary.tsv`. The whole model comes from the JSON-encoded
`spec` parameter. This supplies small-network mathematical checks; it does not
certify biological models or complete BMA compatibility.

## Schema and update semantics

```json
{
  "name": "four_state_target",
  "nodes": [{"id": "X", "kind": "rule", "parents": [], "table": {"": 3}}],
  "state_domains": {"X": 4},
  "update": "synchronous",
  "rule_semantics": "target_unit_step",
  "initial_states": {"X": [0]},
  "readout": {"type": "node_value", "node": "X"}
}
```

- Each node has 2–4 states (default 2) and kind `rule`, `input` or `constant`.
- `rule_semantics=next_state` (default, preserves version 1 transition rules)
  treats table values as next states. `target_unit_step` treats them as targets
  and moves by at most one unit per synchronous step. A constant target 3 from
  initial 0 gives 0→3 or 0→1→2→3, respectively. Both modes use the previous
  complete state for every node. Clamps hold their specified values directly.
- Rule nodes must supply `parents` and a complete `table`. Keys are canonical
  comma-separated integers in parent order; a parentless rule uses `""`.
  Missing rules or combinations fail `INCOMPLETE_RULE`; no inference from
  arrows, fallback rules, persistent cache or previous result files occurs.
- Input nodes must have a clamp or explicitly declare `value`. Missing input
  information fails `MISSING_REQUIRED_INPUT`; unknown never implies zero.
  `required=true` requires a clamp in every arm even when `value` is declared.
  Constants require `value`. All values must be within the node domain.
- Baseline `clamps` may target any node. Optional `intervention.clamps` overrides
  baseline clamps. `initial_states` is `"exhaustive"` or a map from free rule
  nodes to nonempty lists of initial values; unlisted free nodes sweep their
  domains. Duplicate values and permutations have identical meaning. Initial
  states, cycle rotations and attractor ordering are canonicalized.
- Readouts are `node_value` with `node`, or `mean_nodes` with a nonempty `nodes`
  list. Values are raw state levels, without biological normalization.
- `max_nodes` (default 6) is a caller-declared node limit; `max_steps` (default
  64) limits transitions per trajectory. Failure to close within the latter
  fails `RESOURCE_BUDGET_EXCEEDED`. Container CPU/memory/timeout limits remain
  required. No qualification for 40–80-node models is implied.

## Safe prediction contract (breaking schema change)

Per-attractor `readout` is a summary: a fixed-point readout or a mean over one
complete cycle. `readout_kind` distinguishes `fixed_point` from `period_mean`;
`state_readout_range` gives the range of instantaneous readouts in that cycle.
A cycle mean does not describe a stationary fractional state.

An arm always includes all attractors, their periodic states, initial-state
memberships, transient step counts, fixed points, and `multi_stable`.

| Arm result | `readout` | `point_prediction_allowed` |
| --- | --- | --- |
| One reachable fixed point | its value | true |
| One cycle, default policy | null | false |
| One cycle, explicit `readout.cycle_policy="period_mean"` | period mean | true |
| Multiple attractors (even with equal summaries) | null | false |

`attractor_readout_values` and `attractor_readout_range` retain the set/range of
attractor summaries. These are neither probability weights nor a confidence
interval. The scalar eligibility flag is a mathematical output contract; it
does not grant scientific permission to interpret a period mean as an observed
response. Such interpretation must be specified independently before analysis.

A prespecified single initial state can restrict the reachable attractors.
Unspecified state weights are not inferred from basin sizes. Weighted initial
state mixtures are outside this implementation's scope and must not be passed
as an ignored policy.

For an intervention, `delta.delta` is null unless both arms allow scalar
predictions. No attraction-branch pairing or weighting is invented. Downstream
consumers must require schema 2, check `point_prediction_allowed`, and reject
null scalar values; converting null to zero is invalid. The TSV names its
per-attractor field `readout_summary` and is an attractor table, not a scalar
prediction table. There is no `first_initial_state` fallback.

## Errors and execution

Structured validation errors exit 2 with the class prefix: `DANGLING_REFERENCE`,
`ILLEGAL_STATE_VALUE`, `INCOMPLETE_RULE`, `MISSING_REQUIRED_INPUT`,
`OUT_OF_DECLARED_SCOPE`, or `RESOURCE_BUDGET_EXCEEDED`. Unexpected evaluation
errors exit 3 with sanitized `INTERNAL_ERROR`. Failed evaluation removes prior
result/summary files so a previous success cannot masquerade as the new result.
No research files are read. No network is used. Runtime policy remains a pinned
Python image, isolated networking, read-only rootfs, 1 CPU, 512 MiB and timeout.

The zero-input manifest requires the updated RSI installation gate. Version 1
anchor nodes/connections must be removed when creating a version 2 DAG; never
rewrite archived R21 runs or their installed snapshots. The installed plugin
must be activated through the normal lifecycle and its new identity verified;
editing a development workspace alone does not update a resident registry.

## Verification and boundaries

```sh
python3 -B scripts/test_synthetic.py
python3 -B scripts/test_semantics.py
```

The first suite retains the original 53 checks, updating explicit-zero and
zero-input expectations to the new contract. The second adds independent
counterexamples for multiple attractors, cycles, permutations, prescribed
initial states, target steps in both directions, different feedback cycles,
missing inputs, table aliases, and a source-rule deletion. In the last case a
source contributes a complete rule table; after removal, repeated calls with
the same model name and output paths reject the missing rule and delete stale
outputs. This tests the evaluator boundary. It does not qualify upstream
biological source exclusion or the DAG scheduler's cache identity.

Ordinary plugin outputs are accessible through the ordinary DAG interface.
Formal holdout work needs the protected worker/store entry, signed contracts,
real deployment identity and role/object/stage denial tests. A JSON flag or
this plugin's mathematical tests cannot supply access isolation. See
`docs/plugin-development-recovery.md` in the autonomics engine repository.
