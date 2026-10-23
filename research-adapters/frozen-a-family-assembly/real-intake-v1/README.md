# A real-result input candidate V1

This is an executable, separate input contract for existing real result carriers.
It is neither `replay/seen_real_v1.py` nor either existing production input kind.
No existing `family.py`, manifest, replay evidence, production pin, scientific
register, signature or denominator is changed. The source lock is reused from
`family.py`; all nine actual source byte counts/SHA256 are checked before intake.

Current scope: `A_REAL_INPUT_CANDIDATE_V1_QUALIFICATION_PENDING`.
Request schema: `A_REAL_INPUT_REQUEST_V1`.

The active byte-locked decision register contains **275 PENDING decisions and one
A_X01_M06 `LOCKED_O2_PRIMARY_NA`**, not 276 pending decisions. The latter records
`INPUTS_QUALIFIED;OVERLAP_UNRESOLVED`, `NOT_QUALIFIED_NOT_ENABLED`, `NA` primary,
`EXPLORATORY_ONLY` IVW and `method_selected_from_p=NO`. Its existing input card and
harmonization-qualification files are read and their actual byte identities are
retained in `decision_evidence`. This carries existing evidence; it does not grant
scientific authorization. The frozen original `primary_p` helper is also checked
for its O2 missing-primary behavior. Other exact register rows remain pending.

This implementation completes real result/status transport into the full family,
qualification blocking, strict missing propagation and the independent official R
connection. **Finite-primary qualification admission is not completed**: current
frozen inputs contain no qualified primary row or defined, authenticated success
receipt interface. The candidate accepts real finite observed P values while
preserving missing primary. It rejects caller eligibility booleans, approval
flags, O classes and primary overrides. A future signed register/receipt interface
requires an explicit versioned source-lock and contract update, not a new spelling
of `approved` in V1. O2 IVW cannot be promoted to the unavailable MRlap primary.

## Request and source identity

Top-level keys are exactly `schema`, `scope`, `sources`, `seen_history`, `edges`.
There are 1–276 sources, each exactly `{source_id,path,sha256}`, and one matching
history per source. V1 deliberately requires the already-seen identity handled by
the existing replay history validator. It does not authorize previously unseen
scientific execution or turn observed evidence into independent confirmation.

`seen_history` uses the existing XOR exact-time or bounded-date contract without
modification; see `../replay/README.md`. Unknown first-view time stays unknown;
`ON_OR_BEFORE_DATE` keeps the original history TSV SHA and complete lexical row
bytes, and never substitutes midnight or the result carrier creation time.

`edges` contains 1–276 unique frozen edge records with exactly:

- `analysis_id`, `status`, `source_id`, `selector`, `estimator`.
- `analysis_id_column`, `method_column`, `status_column`: exact source column
  names. The selected source row must carry the same frozen ID, method and status.
- `p_column`: explicit column for `ESTIMATED`; null for failures.
- `failure_reason_column`: null for `ESTIMATED`; a nonempty source-ledger reason
  column for `FAILED` or `NOT_ESTIMABLE`.
- `rds`: `{path,sha256}` for every estimated result; null permitted on failures.

All paths are absolute ordinary canonical files with no symlink ancestors. All
source selectors are exact lexical dictionaries and must select exactly one row.
No method/P-column guessing or rounding recovery is performed. An estimated P
must be finite in [0,1]. Every declared source must be used. Omitted frozen edges
are `NOT_RUN`; executed failures and non-estimable results remain distinct.

**Input RDS is an opaque byte-identity binding**, not a `readRDS` or numerical
agreement proof between the carrier's R object and TSV. The receipt binds the
selected original row, source SHA, estimator, declared RDS SHA and frozen decision
row. If scientific admission needs RDS/TSV numerical concordance, the original
method-specific object schema and its validated extractor remain required inputs.
The newly produced official adjustment RDS, separately, is read back and all six
vectors/840 values are compared exactly with the original in-memory R objects.

## Executable chain and DAG interfaces

Run the actual-data driver only through the managed acceptance lifecycle. The
following is a command template, not a claim of a real-data execution:

```text
python3 -B scripts/research_validation_session.py run -- python3 -B /ABS/plugins/research-adapters/frozen-a-family-assembly/real-intake-v1/intake.py --frozen-source SOURCE0 SOURCE1 SOURCE2 SOURCE3 SOURCE4 SOURCE5 SOURCE6 SOURCE7 SOURCE8 --request /ABS/real-request.json --output /ABS/NEW_OUTPUT --rscript /usr/bin/Rscript
```

`NEW_OUTPUT` must be new and its parent canonical. Use the managed permanent
technical evidence namespace for required acceptance output; canonical scientific
inputs remain outside disposable scratch. The driver never runs MR/GWAS or edits
source evidence. It launches official R/stats 4.6.1, checks actual exit status and
emits `real-chain.json` only after successful official adjustment and SHA/readback
receipt checks. Failure output is retained without a completion receipt.

DAG candidate interface (not registered/deployed):

1. Python `assemble(frozen_paths,request_path)` or CLI without `--rscript` consumes
   the original nine File roles plus request File and the request's explicitly
   declared source/history/RDS File dependencies. The caller must declare and
   mount those canonical dependencies read-only; JSON paths alone are not a DAG
   ownership/staging contract. It emits `real-family.tsv`, `real-vectors.tsv`,
   `real-assembly.json` (three File outputs).
2. Independent official stage consumes vector File, assembly-receipt File,
   original frozen R-method File, and a new output directory:

   `Rscript --vanilla ../../frozen-a-family-adjustment/real-intake-v1/adjust_real.R VECTORS RECEIPT SOURCE8 NEW_OFFICIAL_OUTPUT`

   Outputs are `real-adjusted.tsv`, `real-adjustment.RDS`,
   `real-adjustment.json`. The algorithm is the unchanged SHA-checked frozen
   `adjust_full` calling official `stats::p.adjust`; no Python/Rust correction
   formula is introduced. Result identity is bound by input/output SHA256.
3. CLI with `--rscript` connects both stages and emits driver exit/provenance,
   stdout/stderr and a `real-chain.json` hash index. The full analysis IDs, frozen
   decision rows, original result rows/RDS identities and component failure/status
   ledger in the assembly receipt remain available to the downstream DAG.

There are 276 edges plus 288 paths (564 rows), four family counts 88/188/36/252,
six correction vectors (840 rows), and the separate registry total stays 696.
`execution_status` and `primary_qualification` are separate: both components can
be technically estimated while a path is missing qualified primary components.
All component execution states are retained in `path_dependencies`, including
mixed failures. The strict frozen max-P helper operates on primary components;
any missing component gives raw NA and only adjustment vectors use 1. The current
all-missing primary vectors consequently adjust to 1; that is not biological
negative evidence or completed research family execution. Existing production
publisher receipts intentionally do not accept this candidate receipt schema.

## Exact remaining scientific inputs

- Result-before-view eligibility decisions/evidence for the 275 pending edges:
  existing fields `overlap_class`, `evidence_file`, `usual_MR_eligible`,
  `MRlap_applicability`, `diagnostics_file`, `primary_p_source`,
  `method_selected_from_p`, `status`, with the protocol owner's existing review
  and authorization identities. No success vocabulary is invented here.
- For the current O2 edge, documented resolution/identifiability and an applicable,
  diagnostic-qualified MRlap corrected result if the protocol permits O1; the
  existing exploratory IVW and input qualification do not satisfy that condition.
- A protocol-defined authenticated receipt/source-lock migration binding the
  precise edge, method, input/result object identity, eligibility review and
  pre-result decision. The current generic gate evidence has reviewer/date/reason
  fields but is not automatically a per-edge finite-primary authorization API.
- Original full-precision X01→Y05 and M06→Y05 carriers, source/RDS identities and
  history; do not recover them from rounded tables. X01→M06's existing full-
  precision carrier can enter V1 with primary still missing.
- If required for primary admission, method-specific RDS extraction/concordance
  specification and scientific review; byte SHA alone does not certify values.

`test_intake.py` uses self-cleaning toy fixtures; `validate_toy.py` is a managed
acceptance driver producing required permanent evidence and an actual official R
chain using only synthetic result observations with the real frozen source locks.
It does not execute real scientific results or manufacture a successful signature.

## Final sealed acceptance evidence (2026-10-23)

This section is a documentation-only locator added after validation. No tests or
computations were rerun for this addition. The sealed validation used synthetic
toy observations, not actual scientific result inputs, with the actual nine
frozen source locks. It recorded **10 tests, zero failures/errors, full-chain
exit 0**, worker exit 0 and launcher exit 0; the session state is **CLEANED**.
Scientific authorization and G0 remain false.

- Final session: `3fddecd8263d4166888d41f582b35dca`.
- Manifest seal (SHA256): `c555dce6ba321e9048f65b571fef841e09acfadd646e97145455fa01589fdf68`.
- Permanent archived verification file:
  `/home/zj-normal/.local/state/autonomics/validation-archives/3fddecd8263d4166888d41f582b35dca/artifacts/permanent/a-real-input-v1-toy/verification.json`.
- Verification SHA256: `275d652659276d9b245dcdb81d1c31b9a1464e805f987917d1b2e321e3a46074`.

The following tested source hashes are copied from that verification file's
`source_sha256` map. These four source files were checked read-only against the
sealed hashes when adding this locator; the README itself is a post-test
location/documentation increment and is not part of this tested source list.
Paths in the table are relative to `research-adapters/`.

| Tested source | SHA256 |
| --- | --- |
| `frozen-a-family-assembly/real-intake-v1/intake.py` | `35264b2df3320fe34f68c8ad8b858cc1e9abcd7bea3af808fa978551fa150486` |
| `frozen-a-family-assembly/real-intake-v1/test_intake.py` | `ed566a18fa9e10e16032ed14a097ede3b92ae95b470a22d1a175533e585f40f4` |
| `frozen-a-family-assembly/real-intake-v1/validate_toy.py` | `93566e48ea7b574461911e7fe436a538e30d5477ace4d1553a07f991a98ed103` |
| `frozen-a-family-adjustment/real-intake-v1/adjust_real.R` | `bc9f4c4fdb0bd07615a1afa4c89ee2a33814254f064f3f4148b17b7aea30f79a` |
