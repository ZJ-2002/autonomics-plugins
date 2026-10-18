"""SYNTHETIC_ONLY regression suite for synthetic-rule-net/evaluate.

Every EXPECTED value below is HARD-CODED from an independent hand calculation
on paper (documented per case); nothing here derives expectations from the
implementation under test. Each check is reported as three columns:
EXPECTED / ACTUAL / VERDICT. A correct rejection (structured error class,
non-zero exit, no partial outputs) is a PASS, not a test failure.

Run: python3 -B /work/scripts/test_synthetic.py  (plugin debug container)

Hand calculations (independent of evaluate.py):
- T1 activation/inhibition, X clamp=1, A'=X, C'=1-A:
    (A,C) 00->11->10->10 ; 01->11->10 ; 10->10 ; 11->10
    => unique fixed point A=1,C=0 ; readout mean(A,C)=(1+0)/2=0.5
- T2 four-cycle, A'=1-B, B'=A:  00->10->11->01->00, cycle_length=4, no fixed
    point; cycle mean(A,B) over the 4 states = 4/8 = 0.5
- T3 positive feedback A'=A OR B, B'=A OR B: 00 and 11 are fixed points,
    10->11, 01->11 => MULTI_STABLE=true, two fixed points, readouts 0.0/1.0
- T4 no-op intervention, X clamp=1, A'=X, B'=B self-holding with B init 1:
    (A,B) 01->11 ; 11->11 => baseline readout mean(A,B)=1.0 (NOT zero);
    intervention clamps identical => delta = 0.0
- T5 X required and unclamped => MISSING_REQUIRED_INPUT
- T6a parents:["Z"] (no node Z)        => DANGLING_REFERENCE
- T6b clamp B=2 with 2-state domain    => ILLEGAL_STATE_VALUE
- T6c table misses a parent combo key  => INCOMPLETE_RULE
- T6d 7 nodes vs max_nodes 6           => OUT_OF_DECLARED_SCOPE
- T7 legal-but-weird: constant K=1, input X clamped, ring A'=B, B'=A:
    00 fixed, 11 fixed, 01<->10 two-cycle => runs clean, 3 attractors,
    MULTI_STABLE=true, no error
- T8 determinism: same spec twice => byte-identical result/summary files
- T9 result JSON carries implementation_version
- S1 T2 with max_steps=3 (needs 4 transitions) => RESOURCE_BUDGET_EXCEEDED
- S2 T2 with max_steps=4 (state space 4 == budget) => still closes (pigeonhole)
- S3 update "asynchronous"  => OUT_OF_DECLARED_SCOPE
- S4 domain size 5         => OUT_OF_DECLARED_SCOPE
- S5 readout type "banana" => OUT_OF_DECLARED_SCOPE
- S6 table output 5 on 2-state node => ILLEGAL_STATE_VALUE
- S7 initial_states value 5 on 2-state node => ILLEGAL_STATE_VALUE
- S8 3-state ring T'=(T+1) mod 3 => single CYCLE(3) 0->1->2, readout 1.0
- S9 explicitly declared input value 0 => unique fixed point A=0
- S10 intervention flips X 1->0 (A'=X) => baseline 1.0, intervention 0.0,
     delta -1.0
- S11 constant-only model => single FIXED_POINT, state space 1, readout 1.0
- S12 different anchor file contents => byte-identical result.json (anchor
     is inert by construction; MVP-gate artifact only)
- S13 no anchor input => success (zero-input source contract)
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
EVALUATE = HERE / "evaluate.py"

ROWS = []


def record(label, expected, actual, ok):
    ROWS.append((label, expected, actual, "PASS" if ok else "FAIL"))


def run(spec):
    """Execute the zero-input env-driven adapter with self-cleaning toy outputs."""
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "result.json"
        summary = Path(tmp) / "summary.tsv"
        env = dict(os.environ)
        env.pop("AUTONOMICS_INPUT0", None)
        env["RULENET_SPEC"] = json.dumps(spec)
        env["AUTONOMICS_OUTPUT0"] = str(result)
        env["AUTONOMICS_OUTPUT1"] = str(summary)
        proc = subprocess.run([sys.executable, "-B", str(EVALUATE)],
                              env=env, capture_output=True, text=True)
        rj = result.read_bytes() if result.exists() else None
        sv = summary.read_bytes() if summary.exists() else None
        return proc, rj, sv


def ensure_ok(label, proc, rj, sv):
    """Guard for success-path cases: FAIL visibly instead of crashing."""
    if proc.returncode == 0 and rj is not None and sv is not None:
        return True
    err = (proc.stderr or "").strip().splitlines()
    record(label, "exit=0, result.json + summary.tsv written",
           "exit=%d, result=%s, summary=%s, stderr=%r"
           % (proc.returncode, rj is not None, sv is not None,
              err[0] if err else ""), False)
    return False


def fmt(state):
    return ";".join("%s=%s" % (k, state[k]) for k in sorted(state))


def expect_reject(label, spec, klass):
    proc, rj, sv = run(spec)
    stderr = (proc.stderr or "").strip().splitlines()
    first = stderr[0] if stderr else ""
    record(label, "exit!=0, stderr starts '%s:', no output files" % klass,
           "exit=%d, stderr=%r, files(result,summary)=(%s,%s)"
           % (proc.returncode, first or "", rj is not None, sv is not None),
           proc.returncode != 0 and first.startswith(klass + ":")
           and rj is None and sv is None)


SPEC_T1 = {
    "name": "T1_activation_inhibition",
    "state_domains": {"A": 2, "C": 2},
    "nodes": [
        {"id": "X", "kind": "input"},
        {"id": "A", "kind": "rule", "parents": ["X"],
         "table": {"0": 0, "1": 1}},
        {"id": "C", "kind": "rule", "parents": ["A"],
         "table": {"0": 1, "1": 0}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "clamps": {"X": 1},
    "max_nodes": 6,
    "max_steps": 64,
    "readout": {"type": "mean_nodes", "nodes": ["A", "C"]},
}

proc, rj, sv = run(SPEC_T1)
if ensure_ok("T1 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    atts = base["attractors"]
    record("T1 exit", "0", str(proc.returncode), proc.returncode == 0)
    record("T1 attractor count", "1 (unique)", str(len(atts)),
           len(atts) == 1)
    record("T1 attractor type", "FIXED_POINT", atts[0]["type"],
           atts[0]["type"] == "FIXED_POINT")
    record("T1 fixed point state", "A=1;C=0;X=1",
           fmt(atts[0]["states"][0]),
           atts[0]["states"][0] == {"X": 1, "A": 1, "C": 0})
    record("T1 readout mean(A,C)", "0.5", str(base["readout"]),
           base["readout"] == 0.5)
    record("T1 multi_stable", "False", str(base["multi_stable"]),
           base["multi_stable"] is False)
    record("T1 fixed_points count", "1", str(len(base["fixed_points"])),
           len(base["fixed_points"]) == 1)
    record("T1 stdout metadata only",
           "stdout contains implementation_version=", repr(proc.stdout[:80]),
           "implementation_version=" in proc.stdout)

SPEC_T2 = {
    "name": "T2_four_cycle",
    "state_domains": {"A": 2, "B": 2},
    "nodes": [
        {"id": "A", "kind": "rule", "parents": ["B"],
         "table": {"0": 1, "1": 0}},
        {"id": "B", "kind": "rule", "parents": ["A"],
         "table": {"0": 0, "1": 1}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "max_nodes": 6,
    "max_steps": 64,
    "readout": {"type": "mean_nodes", "nodes": ["A", "B"]},
}

proc, rj, sv = run(SPEC_T2)
if ensure_ok("T2 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    atts = base["attractors"]
    cycle = [fmt(s) for s in atts[0]["states"]]
    record("T2 exit", "0", str(proc.returncode), proc.returncode == 0)
    record("T2 attractor count", "1 (all initials reach the same cycle)",
           str(len(atts)), len(atts) == 1)
    record("T2 attractor type", "CYCLE", atts[0]["type"],
           atts[0]["type"] == "CYCLE")
    record("T2 cycle_length", "4", str(atts[0]["cycle_length"]),
           atts[0]["cycle_length"] == 4)
    record("T2 cycle states 00->10->11->01",
           "A=0;B=0 | A=1;B=0 | A=1;B=1 | A=0;B=1", " | ".join(cycle),
           cycle == ["A=0;B=0", "A=1;B=0", "A=1;B=1", "A=0;B=1"])
    record("T2 fixed_points", "[] (no fixed point)",
           str(base["fixed_points"]), base["fixed_points"] == [])
    record("T2 readout on cycle", "0.5", str(atts[0]["readout"]),
           atts[0]["readout"] == 0.5)

SPEC_T3 = {
    "name": "T3_positive_feedback_bistable",
    "state_domains": {"A": 2, "B": 2},
    "nodes": [
        {"id": "A", "kind": "rule", "parents": ["A", "B"],
         "table": {"0,0": 0, "0,1": 1, "1,0": 1, "1,1": 1}},
        {"id": "B", "kind": "rule", "parents": ["A", "B"],
         "table": {"0,0": 0, "0,1": 1, "1,0": 1, "1,1": 1}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "max_nodes": 6,
    "max_steps": 64,
    "readout": {"type": "mean_nodes", "nodes": ["A", "B"]},
}

proc, rj, sv = run(SPEC_T3)
if ensure_ok("T3 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    atts = base["attractors"]
    fps = sorted(fmt(s) for s in base["fixed_points"])
    record("T3 exit", "0", str(proc.returncode), proc.returncode == 0)
    record("T3 attractor count", "2", str(len(atts)), len(atts) == 2)
    record("T3 both fixed points 00 and 11",
           "A=0;B=0 , A=1;B=1", " , ".join(fps),
           fps == ["A=0;B=0", "A=1;B=1"])
    record("T3 MULTI_STABLE flag", "True", str(base["multi_stable"]),
           base["multi_stable"] is True)
    record("T3 per-attractor readouts", "0.0 and 1.0",
           str(sorted(a["readout"] for a in atts)),
           sorted(a["readout"] for a in atts) == [0.0, 1.0])
    record("T3 10 and 01 reach 11", "reached_from of 11 = [1,2,3]",
           str(atts[1]["reached_from"]), atts[1]["reached_from"] == [1, 2, 3])

SPEC_T4 = {
    "name": "T4_noop_intervention",
    "state_domains": {"A": 2, "B": 2},
    "nodes": [
        {"id": "X", "kind": "input", "required": True},
        {"id": "A", "kind": "rule", "parents": ["X"],
         "table": {"0": 0, "1": 1}},
        {"id": "B", "kind": "rule", "parents": ["B"],
         "table": {"0": 0, "1": 1}},
    ],
    "update": "synchronous",
    "initial_states": {"A": [0, 1], "B": [1]},
    "clamps": {"X": 1},
    "max_nodes": 6,
    "max_steps": 64,
    "readout": {"type": "mean_nodes", "nodes": ["A", "B"]},
    "intervention": {"clamps": {"X": 1}},
}

proc, rj, sv = run(SPEC_T4)
if ensure_ok("T4 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    inter = res["arms"]["intervention"]
    delta = res["delta"]
    record("T4 exit", "0", str(proc.returncode), proc.returncode == 0)
    record("T4 baseline readout mean(A,B)", "1.0 (must be non-zero!)",
           str(base["readout"]),
           base["readout"] == 1.0 and base["readout"] != 0)
    record("T4 delta identical clamps", "0.0", str(delta["delta"]),
           delta["delta"] == 0.0)
    record("T4 intervention readout", "1.0", str(inter["readout"]),
           inter["readout"] == 1.0)

expect_reject(
    "T5 missing required input",
    {
        "name": "T5_missing_required_input",
        "nodes": [
            {"id": "X", "kind": "input", "required": True},
            {"id": "A", "kind": "rule", "parents": ["X"],
             "table": {"0": 0, "1": 1}},
        ],
        "update": "synchronous",
        "readout": {"type": "node_value", "node": "A"},
    },
    "MISSING_REQUIRED_INPUT")

expect_reject(
    "T6a dangling parent reference",
    {
        "name": "T6a_dangling_reference",
        "nodes": [
            {"id": "A", "kind": "rule", "parents": ["Z"],
             "table": {"0": 0, "1": 1}},
        ],
        "update": "synchronous",
        "readout": {"type": "node_value", "node": "A"},
    },
    "DANGLING_REFERENCE")

expect_reject(
    "T6b clamp value outside 2-state domain",
    {
        "name": "T6b_illegal_state_value",
        "nodes": [
            {"id": "B", "kind": "input"},
            {"id": "A", "kind": "rule", "parents": ["B"],
             "table": {"0": 0, "1": 1}},
        ],
        "update": "synchronous",
        "clamps": {"B": 2},
        "readout": {"type": "node_value", "node": "A"},
    },
    "ILLEGAL_STATE_VALUE")

expect_reject(
    "T6c table misses parent combination",
    {
        "name": "T6c_incomplete_rule",
        "nodes": [
            {"id": "X", "kind": "input"},
            {"id": "A", "kind": "rule", "parents": ["X"], "table": {"0": 0}},
        ],
        "update": "synchronous",
        "clamps": {"X": 1},
        "readout": {"type": "node_value", "node": "A"},
    },
    "INCOMPLETE_RULE")

expect_reject(
    "T6d node count exceeds max_nodes",
    {
        "name": "T6d_out_of_declared_scope",
        "nodes": [{"id": "X", "kind": "input"}] + [
            {"id": "A%d" % i, "kind": "rule",
             "parents": ["X"] if i == 1 else ["A%d" % (i - 1)],
             "table": {"0": 0, "1": 1}} for i in range(1, 7)],
        "update": "synchronous",
        "clamps": {"X": 1},
        "max_nodes": 6,
        "readout": {"type": "node_value", "node": "A6"},
    },
    "OUT_OF_DECLARED_SCOPE")

SPEC_T7 = {
    "name": "T7_legal_but_weird",
    "state_domains": {"A": 2, "B": 2},
    "nodes": [
        {"id": "K", "kind": "constant", "value": 1},
        {"id": "X", "kind": "input"},
        {"id": "A", "kind": "rule", "parents": ["B"],
         "table": {"0": 0, "1": 1}},
        {"id": "B", "kind": "rule", "parents": ["A"],
         "table": {"0": 0, "1": 1}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "clamps": {"X": 0},
    "max_nodes": 6,
    "max_steps": 64,
    "readout": {"type": "mean_nodes", "nodes": ["A", "B"]},
}

proc, rj, sv = run(SPEC_T7)
if ensure_ok("T7 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    atts = base["attractors"]
    fps = sorted(fmt(s) for s in base["fixed_points"])
    cycles = [a for a in atts if a["type"] == "CYCLE"]
    record("T7 exit (legal model must run)", "0", str(proc.returncode),
           proc.returncode == 0)
    record("T7 attractor count", "3 (2 fixed + 1 cycle)", str(len(atts)),
           len(atts) == 3)
    record("T7 fixed points 00 and 11 survive",
           "A=0;B=0;K=1;X=0 , A=1;B=1;K=1;X=0", " , ".join(fps),
           fps == ["A=0;B=0;K=1;X=0", "A=1;B=1;K=1;X=0"])
    record("T7 ring gives CYCLE(2)", "1 cycle, length 2, states 01<->10",
           "%d cycle(s), length %s, %s"
           % (len(cycles),
              cycles[0]["cycle_length"] if cycles else None,
              " | ".join(fmt(s) for s in cycles[0]["states"])
              if cycles else ""),
           len(cycles) == 1 and cycles[0]["cycle_length"] == 2
           and [fmt(s) for s in cycles[0]["states"]] == ["A=0;B=1;K=1;X=0",
                                                         "A=1;B=0;K=1;X=0"])
    record("T7 MULTI_STABLE flag", "True", str(base["multi_stable"]),
           base["multi_stable"] is True)

proc_a, rj_a, sv_a = run(SPEC_T1)
proc_b, rj_b, sv_b = run(SPEC_T1)
record("T8 result.json byte-identical", "identical bytes",
       "identical" if rj_a == rj_b else "differ", rj_a == rj_b)
record("T8 summary.tsv byte-identical", "identical bytes",
       "identical" if sv_a == sv_b else "differ", sv_a == sv_b)
record("T8 outputs non-empty", "both files non-empty",
       "result=%dB summary=%dB" % (len(rj_a or b""), len(sv_a or b"")),
       bool(rj_a) and bool(sv_a))

res = json.loads(rj_a)
version = res.get("implementation_version")
record("T9 implementation_version present", "non-empty string",
       repr(version), isinstance(version, str) and bool(version))

s1 = dict(SPEC_T2)
s1["max_steps"] = 3
expect_reject("S1 budget 3 cannot close 4-cycle", s1,
              "RESOURCE_BUDGET_EXCEEDED")

s2 = dict(SPEC_T2)
s2["max_steps"] = 4
proc, rj, sv = run(s2)
if ensure_ok("S2 run", proc, rj, sv):
    res = json.loads(rj)
    atts = res["arms"]["baseline"]["attractors"]
    record("S2 budget == state space still closes (pigeonhole)",
           "exit=0, cycle_length=4", "exit=%d, cycle_length=%s"
           % (proc.returncode, atts[0]["cycle_length"] if atts else None),
           proc.returncode == 0 and atts and atts[0]["cycle_length"] == 4)

s3 = dict(SPEC_T1)
s3["update"] = "asynchronous"
expect_reject("S3 non-synchronous update", s3, "OUT_OF_DECLARED_SCOPE")

s4 = dict(SPEC_T1)
s4["state_domains"] = {"A": 5, "C": 2}
expect_reject("S4 domain size 5", s4, "OUT_OF_DECLARED_SCOPE")

s5 = dict(SPEC_T1)
s5["readout"] = {"type": "banana", "nodes": ["A"]}
expect_reject("S5 unknown readout type", s5, "OUT_OF_DECLARED_SCOPE")

s6 = dict(SPEC_T1)
s6["nodes"] = [
    {"id": "X", "kind": "input"},
    {"id": "A", "kind": "rule", "parents": ["X"], "table": {"0": 0, "1": 5}},
]
s6["state_domains"] = {"A": 2}  # fixture: drop node C removed above
s6["readout"] = {"type": "node_value", "node": "A"}
expect_reject("S6 table output outside domain", s6, "ILLEGAL_STATE_VALUE")

s7 = dict(SPEC_T1)
s7["initial_states"] = {"A": [0, 5]}
expect_reject("S7 initial state outside domain", s7, "ILLEGAL_STATE_VALUE")

SPEC_S8 = {
    "name": "S8_three_state_ring",
    "state_domains": {"T": 3},
    "nodes": [
        {"id": "T", "kind": "rule", "parents": ["T"],
         "table": {"0": 1, "1": 2, "2": 0}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "readout": {"type": "node_value", "node": "T"},
}
proc, rj, sv = run(SPEC_S8)
if ensure_ok("S8 run", proc, rj, sv):
    res = json.loads(rj)
    atts = res["arms"]["baseline"]["attractors"]
    record("S8 3-state domain CYCLE(3)",
           "1 attractor, CYCLE, length 3, states 0->1->2",
           "%d attractor(s), %s, length %s, %s"
           % (len(atts), atts[0]["type"] if atts else None,
              atts[0]["cycle_length"] if atts else None,
              "->".join(str(s["T"]) for s in atts[0]["states"])
              if atts else ""),
           len(atts) == 1 and atts[0]["type"] == "CYCLE"
           and atts[0]["cycle_length"] == 3
           and [s["T"] for s in atts[0]["states"]] == [0, 1, 2])
    record("S8 readout mean over cycle", "1.0", str(atts[0]["readout"]),
           atts[0]["readout"] == 1.0)

SPEC_S9 = {
    "name": "S9_explicit_input_zero",
    "nodes": [
        {"id": "X", "kind": "input", "value": 0},
        {"id": "A", "kind": "rule", "parents": ["X"],
         "table": {"0": 0, "1": 1}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "readout": {"type": "node_value", "node": "A"},
}
proc, rj, sv = run(SPEC_S9)
if ensure_ok("S9 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    atts = base["attractors"]
    record("S9 explicit input value 0", "unique fixed point A=0, readout 0.0",
           "%d attractor(s), %s, readout %s"
           % (len(atts), fmt(atts[0]["states"][0]) if atts else None,
              base["readout"]),
           len(atts) == 1 and atts[0]["states"][0] == {"X": 0, "A": 0}
           and base["readout"] == 0.0)

SPEC_S10 = {
    "name": "S10_intervention_flip",
    "nodes": [
        {"id": "X", "kind": "input"},
        {"id": "A", "kind": "rule", "parents": ["X"],
         "table": {"0": 0, "1": 1}},
    ],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "clamps": {"X": 1},
    "readout": {"type": "node_value", "node": "A"},
    "intervention": {"clamps": {"X": 0}},
}
proc, rj, sv = run(SPEC_S10)
if ensure_ok("S10 run", proc, rj, sv):
    res = json.loads(rj)
    delta = res["delta"]
    record("S10 intervention flips readout",
           "baseline=1.0, intervention=0.0, delta=-1.0",
           "baseline=%s, intervention=%s, delta=%s"
           % (delta["baseline_readout"], delta["intervention_readout"],
              delta["delta"]),
           delta["baseline_readout"] == 1.0
           and delta["intervention_readout"] == 0.0
           and delta["delta"] == -1.0)

SPEC_S11 = {
    "name": "S11_constant_only",
    "nodes": [{"id": "K", "kind": "constant", "value": 1}],
    "update": "synchronous",
    "initial_states": "exhaustive",
    "readout": {"type": "node_value", "node": "K"},
}
proc, rj, sv = run(SPEC_S11)
if ensure_ok("S11 run", proc, rj, sv):
    res = json.loads(rj)
    base = res["arms"]["baseline"]
    atts = base["attractors"]
    record("S11 constant-only model", "FIXED_POINT K=1, space 1, readout 1.0",
           "%s, space %d, readout %s"
           % (fmt(atts[0]["states"][0]) if atts else None,
              base["state_space_size"], base["readout"]),
           len(atts) == 1 and atts[0]["type"] == "FIXED_POINT"
           and atts[0]["states"][0] == {"K": 1}
           and base["state_space_size"] == 1 and base["readout"] == 1.0)

SPEC_S12_ANCHOR_ONE = "synthetic-rule-net MVP-gate anchor variant one\n"
SPEC_S12_ANCHOR_TWO = "DIFFERENT ANCHOR CONTENT " * 100
with tempfile.TemporaryDirectory() as tmp:
    outs = []
    for i, content in enumerate((SPEC_S12_ANCHOR_ONE, SPEC_S12_ANCHOR_TWO)):
        anchor = Path(tmp) / ("anchor%d.txt" % i)
        anchor.write_text(content, encoding="utf-8")
        result = Path(tmp) / ("r%d.json" % i)
        env = dict(os.environ)
        env["RULENET_SPEC"] = json.dumps(SPEC_T1)
        env["AUTONOMICS_INPUT0"] = str(anchor)
        env["AUTONOMICS_OUTPUT0"] = str(result)
        env["AUTONOMICS_OUTPUT1"] = str(Path(tmp) / ("s%d.tsv" % i))
        proc = subprocess.run([sys.executable, "-B", str(EVALUATE)],
                              env=env, capture_output=True, text=True)
        outs.append((proc.returncode,
                     result.read_bytes() if result.exists() else None))
    record("S12 anchor content never influences outputs",
           "same result.json bytes for two different anchor files",
           "rc=%d/%d, identical=%s" % (outs[0][0], outs[1][0],
                                       outs[0][1] == outs[1][1]),
           outs[0][0] == 0 and outs[1][0] == 0
           and outs[0][1] is not None and outs[0][1] == outs[1][1])

with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ)
    env.pop("AUTONOMICS_INPUT0", None)
    env["RULENET_SPEC"] = json.dumps(SPEC_T1)
    env["AUTONOMICS_OUTPUT0"] = str(Path(tmp) / "r.json")
    env["AUTONOMICS_OUTPUT1"] = str(Path(tmp) / "s.tsv")
    proc = subprocess.run([sys.executable, "-B", str(EVALUATE)],
                          env=env, capture_output=True, text=True)
    first = (proc.stderr or "").strip().splitlines()
    record("S13 zero-input invocation",
           "exit=0 without anchor",
           "exit=%d, stderr=%r" % (proc.returncode,
                                   first[0] if first else ""),
           proc.returncode == 0 and not first)

print("EXPECTED\tACTUAL\tVERDICT")
for label, expected, actual, verdict in ROWS:
    print("%s | %s\t%s\t%s" % (label, expected, actual, verdict))
failed = sum(1 for row in ROWS if row[3] == "FAIL")
print("TOTAL %d checks, %d failed" % (len(ROWS), failed))
sys.exit(1 if failed else 0)
