# Ordinary regression: official-package route

The user requested official scientific packages rather than native Rust
statistical rewrites. `plugins/r-stats-lm` now provides the ordinary-regression
route through R Core `stats::lm`, with no native estimator fallback. Rust remains
the execution/I/O/provenance layer. Frozen study and daemon configuration are
not changed by this opt-in source addition.

## Actual evidence

The digest-bound R/stats 4.6.1 image was executed, not inferred from a manifest.
17 positive and 29 refusal cases passed direct wrapper/independent official-call
comparison. The oracle uses separately declared literal formulas and never
calls the wrapper's formula-building helper. 39 coefficient rows, full model
RDS, covariance, model matrices, fitted values, residuals, factor references,
zero-weight rows, warnings, special numeric kinds and input/output identities
were examined. Each positive case also refused a second invocation without
changing any existing output hash.

The same 46 cases ran as real five-node/four-edge isolated DAGs: two file sources,
official-package plugin, TSV reader and materializing writer. All five declared
plugin output ports and content hashes were checked; all 17 positive terminal
files were independently re-read, and rejected cases did not publish analytical
outputs. This reused a hash-bound historical harness (`d8659cdf1ebf`), not current
main or the resident daemon. No large new Rust build or numbered vault was made.

The complete mandatory packet is approximately 1.69 MiB/959 files in one managed
permanent archive. Its temporary workspace and owned consumers were cleaned.
`evidence/r-stats-lm-20261014.json` records exact code/image/archive identities,
the four independent assurance layers and exclusions. It is not a signed
scientific certificate or whole-original-node acceptance.

The initial R 4.5.1 image lacked `jsonlite` and failed before any method cases.
That failure is retained. A managed probe established that the selected existing
MRlap image supplies R/stats 4.6.1, jsonlite and digest. No MRlap, LDSC or LD panel
is used by this linear-regression plugin; an image name does not select a method.

Six source/interface unit tests include real R parsing and eight publication
counterexamples. The latter isolate actual publication code using a toy model
and independent host SHA256 transport; they do not claim to exercise the pinned
method-version gate or replace the actual container method proof.

All 125 required catalog/source tests then ran without failures, errors or skips.
An earlier run correctly rejected the new family because the historical
governance checker did not account for it. The integration now records this
explicit new official-method addition separately from LEGACY additions; the
original 31-family/62-kind transport scope is unchanged. That failed run remains
in the evidence index rather than being relabeled as a PASS.
The method, manifest and proof-driver identity guard refuses stale evidence
after a source change and does not permit technical proof to grant production
or scientific authorization.

## Remaining boundaries

This technical-only contract is stricter than R's usual defaults: missing rows,
unobserved factor levels, singularity and nonpositive residual df are blocked.
Parameters, confidence level, weights/offset and reference levels are explicit.
Arbitrary formula expressions, automatic selection, all lm API branches,
statistical simulations, real-donor design qualification, current-daemon loading,
full-scale resource budgets and signed formal-study authorization remain outside
this evidence. Installed function bodies are captured, but an independently
verified official R 4.6.1 source/build provenance chain is not claimed.

This strengthens the existing `FUNC_linear_regression` slot; adding an alias
does not increase the research denominator or declare the native node certified.
Old native drafts/failed builds remain historical, not the selected scientific
backend. Nothing grants G0 or changes the 276/288/696 design families.

## Reproduce

From the plugin repository, with the engine and an independently hash-bound
harness available:

```sh
python3 -B "$ENGINE_ROOT/scripts/research_validation_session.py" run -- \
  python3 -B tools/prove_r_lm.py --runner "$RUNNER" --runner-build "$RUNNER_BUILD"
```

Omitting the runner verifies only direct method contracts and explicitly records
that the DAG has not been checked. Output is always in the managed permanent
archive; the driver refuses unmanaged acceptance execution.

Official R definitions: [lm](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/lm.html)
and [summary.lm](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/summary.lm.html).
Documentation version labels are not substituted for the measured image lock.
