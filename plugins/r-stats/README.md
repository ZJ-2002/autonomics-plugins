# Official R statistics

This candidate calls the installed official R/stats 4.6.1 package directly:
`t.test`, `cor.test`, `var.test`, `wilcox.test`, `prop.test`, and `p.adjust`.
There is no Rust numerical implementation or fallback estimator.

The measured, digest-pinned existing R image is shared with `r-stats-lm` and
`donor-composition-official`; other packages in that image are not used.
The older `research-adapters/cachexia-r-stats` R/stats 4.5.1 profile is retained
unchanged. Its numerical results are not treated as new 4.6.1 references.

Every node takes two Files: a lexical TSV with unique `row_id`, and an explicit
`key,value` TSV contract binding the input SHA256 and all method controls.
The contract retains `scope=TECHNICAL_ONLY_NOT_G0`; calculation does not grant
scientific authorization. Five outputs retain the complete scalar table,
parameter vectors, full RDS, log, and identity audit. Inputs and outputs are not
drop-in replacements for legacy native DataFrame nodes.

The supported input limit is 10,000 rows, except adjustment accepts up to 25,000
rows for complete transcriptome-sized families. `n_total` is explicit and cannot
be smaller than the input row count. Missing values follow official R semantics;
this is not a frozen-study NA-to-one adapter, donor qualification, or family
selection service. Callers must preserve the original raw statuses separately.

The wrapper retains all earlier explicit method branches, parameter validation,
and no-overwrite controls; changes are the pinned R version and adjustment row
limit. Version requalification uses independently recomputed official 4.6.1
results from the retained synthetic arguments, not copied 4.5.1 answers.
Large-family BH/BY/Holm cases and the new row-limit refusal are additional tests.
The host comparison has 168 executed cases: 127 complete official-reference
matches and 41 specific refusals. In this author version, the retained Wilcoxon
ties/zero exact-request cases now return valid exact results; their new expected
outcomes come from independent 4.6.1 calls, not from accepting wrapper output.
The old 4.5.1 outcomes and implementation remain unchanged. See
`evidence/r-stats-current-r-host-20261020.json` for the bounded proof identity.
Host, container, DAG, deployment and study qualification remain separate axes.
Do not infer a production or scientific certificate from this candidate README.
