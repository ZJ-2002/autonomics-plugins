# Current-engine lm proof: prepared, not yet executed

`tools/build_current_r_lm.py` exports one exact Git candidate containing only
the explicit `official_lm_dag` example added to its declared engine parent.
It refuses a non-build session, a nonexact commit or a new dependency cache.
Compilation is release/locked/offline, with two jobs, an exact source-revision
stamp and before/after source identities. The executable is preserved once in
the managed permanent packet; the shared canonical cache is not deleted.

`tools/prove_current_r_lm.py` then requires that actual executable/build identity,
the exact full engine commit, ContentRequired input hashing, serial execution
and no incremental cache. It uses only file I/O Rust nodes plus the official
R plugin. A historical executable or best-effort hash report is rejected.

The complete 46-case independent reference packet from session
`372140b7eea947c698b1544a68888604` is rehashed against its fixed archive manifest
before use. Only the small required synthetic inputs/contracts and already
computed independent RDS/table oracles are copied. No official oracle is rerun,
no failed case disappears, no tolerance is enlarged, and the old report is not
relabeled as current. All five published ports, output hashes, failure diagnostics,
terminal materialization and independent complete-model readback remain required.

Three new unit checks verify workflow wiring and refusal of historical identity,
best-effort hashing, unrelated failures and partial terminal output. Together
with the existing source tests, 131 required cases passed before integrating
the concurrently published verifier family. These are preparation/source tests,
not execution of the new Rust example or current-engine method DAGs.

At this checkpoint another conversation's managed build holds the unique large
build slot. No competing build, cache deletion or historical-binary substitution
is authorized. The current-engine probe remains uncompiled/unexecuted, and no
whole-node or daemon/scientific/G0 qualification is issued.

The original official-method/historical-DAG proofs and primary R release-function
identity evidence remain separate and unchanged. Current-engine execution is
the next pending technical layer, not a new scientific method or a new function
slot in the fixed 120-candidate denominator.
