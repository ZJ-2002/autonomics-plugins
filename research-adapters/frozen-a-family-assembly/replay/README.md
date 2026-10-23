# Already-seen real-result technical replay v1

This separate tool removes the engineering inability to transport already-seen
finite MR results through complete frozen families. It does not widen either
existing production kind, manifest or primary-result contract. No plugin is
registered and no production pin is changed by adding these files.

`seen_real_v1.py` accepts the same nine exact frozen source roles as `family.py`,
plus `SEEN_REAL_A_FAMILY_REPLAY_REQUEST_V1` JSON with exactly these keys:

- `schema`, and `scope = SEEN_REAL_TECHNICAL_REPLAY_V1_NOT_RESEARCH`.
- `sources`: one to three `{source_id,path,sha256}` already-seen result TSVs.
- `seen_history`: one record per source with matching `source_id`/`sha256` and
  `declaration = ALREADY_SEEN_NOT_INDEPENDENT`. Use either an exact `seen_at` ISO
  timestamp including timezone, or the bounded-date fields below, never both.
- `edges`: one to three records containing `analysis_id`, `status`, `source_id`,
  `selector`, `p_column`, and `estimator`. `selector` is a nonempty dictionary of
  exact string cells and must select exactly one TSV row. No method/P column is
  guessed. `ESTIMATED` reads a finite [0,1] P from `p_column`; `FAILED` and
  `NOT_ESTIMABLE` require `p_column = null`. Unprovided frozen edges are `NOT_RUN`.

The view history is a hash-bound declaration, not an independently authenticated
scientific signature. The caller must retain the original viewing/audit evidence.
An estimator label is provenance, not certification of that estimator or P value.

When an existing log explicitly says the exact first-view time is unknown, use
`precision = ON_OR_BEFORE_DATE`, `upper_bound_date = YYYY-MM-DD`,
`exact_first_view_known = false`, `history_file = {path,sha256}`, and
`analysis_ids` naming exactly the selected edges supplied by this result source.
The original TSV must contain one matching row per ID, with
`first_result_viewed_at = ON_OR_BEFORE_YYYY-MM-DD_EXACT_FIRST_VIEW_UNKNOWN`,
`status = LEGACY_PIPELINE_ANALYZED`, and
`allowed_identity = LEGACY_EXPLORATORY_TECHNICAL_REANALYSIS`. The receipt preserves
the history-file SHA, each complete original lexical row, its original line bytes
and SHA. Future dates, mixed precision, absent/duplicate IDs and mismatched source
mapping are rejected. No midnight or newly observed audit time is substituted for
an unknown historical first-view time. This additional strict V1 branch carries
existing history faithfully; it does not modify that history or scientific rules.
The bound applies to the logged analysis identity, not to the first viewing or
creation of every later result byte stream. The receipt marks this distinction;
the separate sealed prior-seen source establishes which result bytes are replayed.

The tool validates the original frozen universes and locks, then emits 564 rows:
276 edges and 288 paths. The four family sizes remain 88/188/36/252; the separate
696 registry total is not rewritten. Path replay values use the original strict
IUT helper. Any missing component gives raw `NA`, not the other component's P.
`FAILED`, `NOT_RUN`, and `NOT_ESTIMABLE` remain distinct. Only adjustment vectors
receive 1 for missing values. Six vectors contain all 840 expected rows.

All numerical fields are explicitly `replay_*`. Every `p_primary` is always NA,
including an IVW reading from an unresolved O2 edge. No eligibility or primary
override is accepted. Family completion, independent replication, authorization
and G0 are never granted. A later primary implementation must consume separately
validated eligibility receipts; this tool cannot fabricate or bypass them.

Run actual data only inside the existing managed acceptance lifecycle, with a
new output directory in its scratch or permanent technical evidence namespace:

```text
python3 -B replay/seen_real_v1.py --frozen-source SOURCE0 ... SOURCE8 --request REQUEST.json --output NEW_REPLAY_DIR
Rscript --vanilla replay/adjust_seen_v1.R NEW_REPLAY_DIR/replay-vectors.tsv NEW_REPLAY_DIR/replay-assembly.json SOURCE8 NEW_ADJUSTMENT_DIR
```

The R stage requires official R/stats 4.6.1 and the exact original methods file.
It extracts and SHA-checks the same frozen `adjust_full` definition already used
by the existing official adjustment adapter, then calls that definition against
the complete vectors. No Python adjustment formula is introduced. It preserves
the full R objects and emits only `replay-adjusted.tsv`, `replay-adjustment.RDS`
and a technical receipt. It is deliberately not compatible with the primary
publisher's receipt schema. Both output directories must be new; partial failure
is not a completion receipt and never overwrites historical output.

The Python toy tests prove input/status/family transport and primary isolation,
not an actual official R invocation or real-data DAG/deployment. A managed
already-seen three-edge run plus official R object/readback comparison remains
to be performed before calling the new technical replay path runtime-verified.
No GWAS, harmonisation, MR, new scientific hypothesis test or production restart
is necessary for that follow-up. Existing official correction evidence is reused
for the unchanged algorithm; only the new transport contract needs verification.
