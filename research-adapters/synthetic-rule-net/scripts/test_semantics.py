"""Independent hand-calculated counterexamples; all files are disposable toys."""
import copy
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluate import evaluate, parse_spec, SpecError


def bistable():
    return {"name": "bistable", "nodes": [
        {"id": n, "kind": "rule", "parents": ["A", "B"],
         "table": {"0,0": 0, "0,1": 1, "1,0": 1, "1,1": 1}}
        for n in ["A", "B"]],
        "readout": {"type": "mean_nodes", "nodes": ["A", "B"]}}


def ramp(target, initial, semantics):
    return {"name": "ramp", "state_domains": {"X": 4},
            "nodes": [{"id": "X", "kind": "rule", "parents": [],
                       "table": {"": target}}],
            "initial_states": {"X": [initial]},
            "rule_semantics": semantics,
            "readout": {"type": "node_value", "node": "X"}}


class SemanticsTests(unittest.TestCase):
    def test_multistability_has_no_point_or_delta(self):
        spec = bistable()
        spec["intervention"] = {"clamps": {}}
        result = evaluate(spec)
        arm = result["arms"]["baseline"]
        self.assertIsNone(arm["readout"])
        self.assertFalse(arm["point_prediction_allowed"])
        self.assertEqual(arm["attractor_readout_values"], [0.0, 1.0])
        self.assertEqual(arm["attractor_readout_range"], [0.0, 1.0])
        self.assertIsNone(result["delta"]["delta"])
        self.assertFalse(result["delta"]["point_prediction_allowed"])

    def test_enumeration_and_node_order_leave_outputs_identical(self):
        expected = evaluate(bistable())
        for node_order in itertools.permutations(["A", "B"]):
            for av, bv in itertools.product(([0, 1], [1, 0]), repeat=2):
                spec = bistable()
                spec["nodes"].sort(key=lambda n: node_order.index(n["id"]))
                spec["initial_states"] = {"A": av, "B": bv}
                self.assertEqual(evaluate(spec), expected)

    def test_a_prespecified_single_initial_can_resolve_bistability(self):
        spec = bistable()
        spec["initial_states"] = {"A": [1], "B": [1]}
        arm = evaluate(spec)["arms"]["baseline"]
        self.assertEqual(arm["readout"], 1.0)
        self.assertTrue(arm["point_prediction_allowed"])

    def test_equal_readouts_do_not_hide_multiple_states(self):
        spec = bistable()
        spec["nodes"].append({"id": "K", "kind": "constant", "value": 1})
        spec["readout"] = {"type": "node_value", "node": "K"}
        arm = evaluate(spec)["arms"]["baseline"]
        self.assertTrue(arm["multi_stable"])
        self.assertIsNone(arm["readout"])
        self.assertEqual(arm["attractor_readout_values"], [1.0])

    def test_cycle_summary_requires_explicit_observation_policy(self):
        spec = {"name": "cycle", "nodes": [
            {"id": "X", "kind": "rule", "parents": ["X"],
             "table": {"0": 1, "1": 0}}],
            "readout": {"type": "node_value", "node": "X"},
            "intervention": {"clamps": {}}}
        result = evaluate(spec)
        arm = result["arms"]["baseline"]
        self.assertEqual(arm["attractors"][0]["readout"], 0.5)
        self.assertEqual(arm["attractors"][0]["state_readout_range"], [0.0, 1.0])
        self.assertEqual(arm["attractors"][0]["readout_kind"], "period_mean")
        self.assertIsNone(arm["readout"])
        self.assertIsNone(result["delta"]["delta"])
        spec["readout"]["cycle_policy"] = "period_mean"
        result = evaluate(spec)
        self.assertEqual(result["arms"]["baseline"]["readout"], 0.5)
        self.assertEqual(result["delta"]["delta"], 0.0)

    def test_multistability_cannot_be_resolved_by_cycle_policy(self):
        spec = bistable()
        spec["readout"]["cycle_policy"] = "period_mean"
        self.assertIsNone(evaluate(spec)["arms"]["baseline"]["readout"])

    def test_targets_move_one_unit_in_both_directions(self):
        for target, initial in [(3, 0), (0, 3)]:
            for semantics, transitions in [("next_state", 1), ("target_unit_step", 3)]:
                spec = ramp(target, initial, semantics)
                arm = evaluate(spec)["arms"]["baseline"]
                self.assertEqual(arm["attractors"][0]["transient_steps"], [transitions])
                self.assertEqual(arm["readout"], float(target))
                spec["max_steps"] = transitions
                with self.assertRaisesRegex(SpecError, "RESOURCE_BUDGET_EXCEEDED"):
                    evaluate(spec)
                spec["max_steps"] += 1
                self.assertEqual(evaluate(spec)["arms"]["baseline"], arm)

    def test_target_semantics_changes_feedback_cycle(self):
        spec = ramp(3, 0, "next_state")
        spec["nodes"][0].update(parents=["X"], table={"0": 3, "1": 3, "2": 0, "3": 0})
        direct = evaluate(spec)["arms"]["baseline"]["attractors"][0]
        self.assertEqual(direct["states"], [{"X": 0}, {"X": 3}])
        spec["rule_semantics"] = "target_unit_step"
        gradual = evaluate(spec)["arms"]["baseline"]["attractors"][0]
        self.assertEqual(gradual["states"], [{"X": 1}, {"X": 2}])
        self.assertEqual(gradual["transient_steps"], [1])

    def test_unknown_input_is_rejected_but_explicit_zero_is_allowed(self):
        spec = {"name": "input", "nodes": [{"id": "X", "kind": "input"}],
                "readout": {"type": "node_value", "node": "X"}}
        with self.assertRaisesRegex(SpecError, "MISSING_REQUIRED_INPUT"):
            evaluate(spec)
        spec["nodes"][0]["value"] = 0
        self.assertEqual(evaluate(spec)["arms"]["baseline"]["readout"], 0.0)
        spec["nodes"][0]["required"] = True
        with self.assertRaisesRegex(SpecError, "MISSING_REQUIRED_INPUT"):
            evaluate(spec)
        spec["clamps"] = {"X": 1}
        self.assertEqual(evaluate(spec)["arms"]["baseline"]["readout"], 1.0)

    def test_rule_table_alias_cannot_override_declared_entry(self):
        spec = ramp(3, 0, "next_state")
        spec["nodes"][0].update(parents=["X"], table={"0": 3, "1": 3, "2": 3, "3": 3, "00": 0})
        with self.assertRaisesRegex(SpecError, "OUT_OF_DECLARED_SCOPE"):
            evaluate(spec)

    def test_unsupported_policies_and_duplicate_json_keys_fail_closed(self):
        for section in ["spec", "readout", "node", "intervention"]:
            spec = bistable()
            if section == "spec":
                spec["initial_state_weights"] = [0.25, 0.75]
            elif section == "node":
                spec["nodes"][0]["default_rule"] = 0
            elif section == "intervention":
                spec["intervention"] = {"weights": [0.25, 0.75]}
            else:
                spec["readout"]["weights"] = [0.25, 0.75]
            with self.assertRaisesRegex(SpecError, "OUT_OF_DECLARED_SCOPE"):
                evaluate(spec)
        for raw in ['{"name":"first","name":"second"}', '{"name":NaN}']:
            with self.assertRaisesRegex(SpecError, "OUT_OF_DECLARED_SCOPE"):
                parse_spec(raw)

    def test_deleted_source_rule_is_not_restored_or_reused(self):
        # Source S contributes A's complete table. The held-out variant has
        # that contribution removed, retaining the same model name and paths.
        # A prior successful result must not supply the missing rule/result.
        complete = bistable()
        excluded = copy.deepcopy(complete)
        del excluded["nodes"][0]["table"]
        with tempfile.TemporaryDirectory() as tmp:
            result, summary = Path(tmp) / "result.json", Path(tmp) / "summary.tsv"
            env = dict(os.environ, AUTONOMICS_OUTPUT0=str(result), AUTONOMICS_OUTPUT1=str(summary))
            env.pop("AUTONOMICS_INPUT0", None)
            for spec, expected in [(complete, 0), (excluded, 2), (complete, 0), (excluded, 2)]:
                env["RULENET_SPEC"] = json.dumps(spec)
                process = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("evaluate.py"))],
                                         env=env, capture_output=True, text=True, check=False)
                self.assertEqual(process.returncode, expected, process.stderr)
                self.assertEqual(result.exists(), expected == 0)
                self.assertEqual(summary.exists(), expected == 0)
                if expected:
                    self.assertTrue(process.stderr.startswith("INCOMPLETE_RULE:"))


if __name__ == "__main__":
    unittest.main()
