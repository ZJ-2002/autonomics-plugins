# Strict HyPrColoc technical adapter

Staged only: `cachexia_hyprcoloc_official` does not replace the original node or
register itself in the resident daemon. It calls unmodified HyPrColoc **0.0.2**,
fixed source `0348bbdd977be731d82e4efda115a9bed63cd44f`, in the pinned image
declared in `manifest.toml`. The proof compares installed R functions/formals
and uses a separately rebuilt official C++ library in a separate R process.

## Inputs

Six files are required in this order:

| Port | Schema |
| --- | --- |
| 0 | SNP-ordered TSV: `SNP` and exactly the beta/SE columns declared in port 1 |
| 1 | `trait, beta, se, binary_outcome`; unique trait names, distinct effect columns, binary flag `0` or `1` |
| 2 | `key, value` frozen contract; exactly the 28 keys listed below |
| 3 | Trait correlation: `id` plus trait-named columns; exact row and column order of port 1 |
| 4 | Pairwise sample overlap: same ordered format, symmetric PSD, unit diagonal, entries in [0,1] |
| 5 | Signed SNP LD correlation: `id` plus SNP-named columns; exact row and column order of port 0 |

All numeric matrices must be finite, symmetric within 1e-12 and PSD within
1e-10. They are passed without reordering, symmetrizing or PSD repair. Effects
must be finite with strictly positive SE; missing/underflow/ratio-overflow,
duplicate/empty/ambiguous identities and unknown columns are blocked, not dropped.
The wrapper does not estimate these matrices or establish their scientific
eligibility. Hash/shape checks are not allele or overlap qualification.

Contract keys:

```text
schema_version scope test_id input_role effect_scale alignment missing_policy
matrix_qualification input0_sha256 input1_sha256 input3_sha256 input4_sha256
input5_sha256 trait_subset bb_alg bb_selection reg_steps reg_thresh align_thresh
prior_1 prior_c prior_12 sensitivity sense_1 sense_2 uniform_priors ind_traits snpscores
```

There are no inferred method defaults. Use `trait_subset=ALL` explicitly, or a
comma-separated subset of at least two unique known names. The official
case-insensitive matching preserves **original trait order**, not requested order.
Use `default` explicitly for official thresholds and `NULL` explicitly for
`prior_12`; booleans are literal `true/false` and integers canonical decimal.
`bb_selection` uses the actual official values `regional`, `align`, `reg.only`.
The old wrapper's `alignment` value is not the official `align` branch.

`prior_12` overrides `prior_c` according to the official formula
`prior_12 / (prior_1 + prior_12)`, recorded in the audit. It is not an inferred
v4.1 pairwise coloc prior contract. Threshold floors follow the official package.
The wrapper restricts probabilities to (0,1), 2–12 traits and 2–1200 SNPs. The
nonrapid path is limited to 4 traits/50 SNPs, `reg_steps <= 2`, `sense_2 <= 2`.
This deliberately bounded interface is not certification of the full API domain.

`scope=TECHNICAL_ONLY_NOT_G0`, `schema_version=1`,
`effect_scale=CONVENTIONAL_BETA_NOT_MRLAP_Z`,
`alignment=PREHARMONISED_REQUIRED` and `missing_policy=reject` are mandatory.
Roles are synthetic technical input, official author example or `LEGACY_SEEN`;
real data additionally require `EXTERNALLY_QUALIFIED_ATTESTATION`. These are source
attestations, not independently verified scientific qualifications or permissions.

## Outputs and failure semantics

| Port | Output |
| --- | --- |
| 0 | Full official object's typed long summary; unique field paths, numeric/text/missing columns; numeric precision 17 significant digits |
| 1 | Unmodified complete official RDS including class, all attributes and available SNP scores |
| 2 | Nonempty log with frozen call, warnings and success/failure |
| 3 | Every requested SNP with lexical identity and original position |
| 4 | Method/input/contract/output hashes, actual branches, effective thresholds/prior and scientific boundary audit |
| 5 | Every requested trait, column roles, original position and actual subset membership |

Official colocalization summary probabilities are already rounded to four decimals
by the package. Sensitivity fields are not covered by that rounding; SNP scores
are not rounded by this wrapper. All missing fields remain missing; explicit
nullable casts are required in the proved read/SQL/materialization chain.
Failures remove all four analytical ports and retain `BLOCKED` audit and log.

## Explicit nonclaims

- `reg.only` is regional-only evidence; `sensitivity=TRUE` assesses regional
  probabilities, **not** the posterior probability of colocalization.
- Official 0.0.2 fails with `object 'snps.clc' not found` for rapid sensitivity
  (`reg_steps=1` and independent traits/identity correlation). That combination
  is explicitly blocked. No source mutation or silent step replacement is made.
  The nonrapid sensitivity fixture explicitly freezes `reg_steps=0`.
- HyPrColoc's posterior is not pairwise coloc `PP.H4`, `coloc.susie`, or a
  signal-qualified three-trait bridge. Successful clustering is not causality.
- No source/build/ancestry/allele/effect-scale/matrix eligibility, complete
  research family, persistent recovery, global resource, production daemon or
  G0 certification is granted. The image limits one container, not all processes.

[Fixed official source](https://github.com/jrs95/hyprcoloc/blob/0348bbdd977be731d82e4efda115a9bed63cd44f/R/hyprcoloc.R)
and proof protocol: `docs/audits/cachexia-v4.1-2026-10-07/HYPRCOLOC_NODE_PROOF.md`.
