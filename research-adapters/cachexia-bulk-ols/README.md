# v4.1 normalized bulk OLS input contract

This is a study-specific input adapter, not a statistical algorithm or a deployed
daemon plugin. It accepts a gene-by-sample matrix, donor metadata, and a request
JSON containing the original contrast-lock row, expression scale, arm identities,
independent-unit column and explicit matrix gene IDs.

Only `log2_normalized`, unpaired/unpooled independent donors, and
`expression ~ condition` are supported. Samples are joined by ID, not column
position. Matrix samples must match all metadata samples exactly. Repeated units,
changed arm counts, missing selected genes and missing/nonfinite selected values
are blocked. Covariates, weights, scoring and ortholog mapping require separate
contracts; the adapter does not invent them. Unique IDs do not independently prove
biological independence or contrast eligibility.

Outputs are a long TSV (`gene/sample/condition/expression`), audit JSON and log.
`condition=0` is control and `condition=1` is case. SQL can select one explicit gene
before `linear_regression`. The model is ordinary unweighted OLS, not moderated
limma, Welch, Mann–Whitney, singscore or DESeq2. No gene-set or testing-family
denominator is inferred from the selected demonstration genes.

On failure, the prepared TSV is absent and a `BLOCKED` audit/log is retained in
the failed container workspace. Failed ports are not automatically published.
`LEGACY_SEEN` is retained; technical reproduction and a new exploratory gene-model
layer do not create independent validation or grant G0.
