# Official R linear regression

`r_stats_lm` calls the installed, unmodified `stats::lm` (QR), `summary.lm`,
`confint.lm` and `vcov.lm`. It is not a Rust translation, a mixed model or
limma empirical Bayes. No native statistical fallback is permitted.

The existing digest-pinned image supplies measured R/stats 4.6.1 and the required
jsonlite/digest dependencies. An initial candidate image with R 4.5.1 lacked
jsonlite: that managed attempt failed and is not counted as method evidence.
Other packages in the selected
image are not used as alternative estimators. The entry rejects a different
R/stats version. Image availability and actual daemon loading require separate
deployment evidence; a manifest alone proves neither.

## Contract

Input 0 is unquoted rectangular TSV, `row_id` first, followed by columns in the
exact JSON declaration order. Identities remain literal (`0001`, `1e03`, `NA`
are legitimate row IDs). Values are explicitly numeric or categorical; no
automatic type conversion or row deletion is allowed.

Input 1 is JSON with these required fields, and no additional keys:

```json
{
  "schema_version": 1,
  "scope": "TECHNICAL_ONLY_NOT_G0",
  "analysis_id": "toy_lm",
  "input_sha256": "<SHA256 of input 0>",
  "response": "y",
  "columns": {
    "y": {"type": "numeric"},
    "age": {"type": "numeric"},
    "condition": {"type": "factor", "levels": ["control", "case"]}
  },
  "terms": [["age"], ["condition"], ["age", "condition"]],
  "intercept": true,
  "weights": null,
  "offset": null,
  "qr_tolerance": 1e-7,
  "conf_level": 0.95
}
```

Terms contain only declared predictor symbols. Interactions are explicit,
and do not silently add main effects. Formula ordering follows R. Factor levels
and treatment reference (first level) are explicit. Numeric weight/offset
columns must also be declared; zero weights follow official R semantics and
are retained in the observation audit. Empty terms with an intercept specify
an intercept-only model. Arbitrary R expressions, automatic selection and
implicit environment lookup are not exposed.

Outputs 0–4 are coefficients TSV, observations TSV, complete model RDS,
nonempty log and hash audit JSON. Coefficient names are official R names, not
renamed native conventions. The RDS retains QR, model frame, model matrix,
response, covariance, warnings and contract. Paired numeric-kind columns
distinguish finite values, missing values, NaN and infinities. A downstream
Arrow reader must explicitly apply those semantics, not guess from TSV text.

## Safety and evidence boundaries

The technical contract explicitly uses `na.fail` and `singular.ok=FALSE`;
these are stricter than the usual R defaults, not claims about those defaults.
Missing/nonfinite model values, unknown factors, unused columns, singular
designs and nonpositive residual df are blocked. This does not qualify donor
independence, scientific estimands, replication weights or study eligibility.

Outputs must be new, distinct paths in one existing non-symlink directory.
Hard-link publication cannot clobber an existing output; ordinary-error rollback
only removes outputs whose recorded inode identity is still owned by this run.
There is no claim of crash-atomic publication or persistent restart recovery.

Limits: 64 MiB per input, 10,000 observations, 100 declared model columns.
This is a new opt-in technical route, not a replacement of frozen study files
or production configuration, and not certification of every `lm` API branch.

Official definitions:
- https://stat.ethz.ch/R-manual/R-devel/library/stats/html/lm.html
- https://stat.ethz.ch/R-manual/R-devel/library/stats/html/summary.lm.html
- https://github.com/wch/r-source/blob/1d95a4c60b0be6766490b1a621610b98a4bf5765/src/library/stats/R/lm.R
