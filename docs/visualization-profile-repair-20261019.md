# Visualization qualified-profile migration repair

Two repairs previously verified in the study adapter had not reached the
canonical pluggable family: an `emptyenv()` parent prevented even R assignment
and namespace/operator lookup, and terminal-only behavior was documented but
not declared as execution metadata. The canonical script now uses `baseenv()`;
the manifest explicitly sets `terminal = true`.

This family now pins the previously qualified reference environment:

`ghcr.io/zj-2002/visualization@sha256:8f31b667355a7b3ab0fbabdac49e1c5c7f91ab81b560564efdddb3d7d59f94d6`

The preserved reference environment identifies R 4.5.3, Arrow 23.0.1.2 and
ggplot2 4.0.3. This is an explicit environment alignment, not certification of
the former public image
`ghcr.io/auto-nomics/autonomics/visualization@sha256:ee9592b77bc5ea0cebfafafbe39550c377204019f451d7a37e13e4ce2e884f15`.
The former image identity remains provenance and is not treated as tested by
results obtained with the different reference digest.

Two File inputs, one PNG output, five data formats, required encoding parameter,
8-by-6-inch/150-dpi defaults, numeric positivity limits, interpreter, environment
parameter bindings and CPU/memory/PID declarations are retained. The historical
reference script path was `scripts/render.R`; the canonical transport path
remains `scripts/render.R.sh`. Qualification requires the executable R bodies
to match, not merely the file names. Descriptor/documentation wording now
states that scripts are trusted and frozen rather than claiming an enforced
R-expression grammar.

## Evidence boundaries

The original complete reference proof separately checked all 506 cells of an
already-seen 46-donor/11-column table and all 46 plotted coordinates across five
encodings. Ten real three-node/two-edge graphs matched independent official PNG
references byte for byte. Eight runtime failures and nine preexecution contract
refusals produced no normal artifact. Five native terminal tests checked actual
framework enforcement. Reuse requires exact script, manifest semantics, runtime
digest and source-identity reconciliation; a visually plausible image alone is
not evidence that numeric values, labels or a statistical analysis are correct.

Small source-bound R counterexamples and metadata tests concern the migration
repair, not new research. `baseenv()` permits ordinary R evaluation; it is not a
security sandbox for arbitrary untrusted scripts. Containers and resource
declarations do not turn arbitrary R code into an enforced scientific method.

This repair does not deploy or restart the daemon, authorize a study, validate
all scripts or encodings, certify current full-engine dependencies, or grant G0.
