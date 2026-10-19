# Direct official donor-composition GLM

Status: implementation prepared; container/SDK qualification and publication pending.
No frozen study, native node alias, method choice or scientific approval is changed.

The family reuses an existing pinned R 4.6.1 image containing stats/jsonlite.
Its embedded 4,093-byte method core is byte-identical to the separately retained
`donor_composition_reference.R` (SHA256
`53c3bd5d1ffaa254ad1161a3d325f722f99c7816753c7ebdb4bc02e5416e7001`).
The independent reference is not changed or generated from adapter results.

`donor_composition_official` accepts two Files: request JSON and literal cell TSV.
The request has exactly these fields:

```json
{
  "schema_version": 1,
  "scope": "TECHNICAL_ONLY_NOT_G0",
  "analysis_id": "toy",
  "input_sha256": "EXACT_CELL_TSV_SHA256",
  "columns": ["cell_id", "donor", "cell_type", "condition"],
  "spec": {
    "donor_col": "donor",
    "cell_type_col": "cell_type",
    "condition_col": "condition",
    "cell_id_col": "cell_id",
    "reference": "reference",
    "test": "test",
    "cell_types": ["T", "B", "absent"],
    "min_donor_cells": 1,
    "min_donors_per_condition": 1,
    "correction": "BH"
  }
}
```

All identities remain strings, including `NA` and leading-zero donor IDs. The
ordered four-column list must equal the actual TSV header and use exactly the
four distinct bindings. Cell IDs are globally unique and mandatory. Complete
families and thresholds are explicit; the native optional-cell-ID and
automatically inferred family branches are intentionally not exposed.

Outputs, in order: `tests.tsv`, `composition.tsv`, complete official `models.RDS`,
`audit.json`, `donor_composition.log`. Numeric missing TSV fields are empty;
literal `NA` IDs are not missing. Use an explicit reader schema or the RDS rather
than a broad lexical NA coercion. The RDS retains raw input, full configurations,
all models, tests, donor compositions and runtime. Entirely nonestimable families
remain successful technical results with full missing rows and explicit statuses.
Fatal errors publish no normal tables/RDS/audit, with a newly owned BLOCKED log
retained when possible. Existing files/symlinks are never overwritten.

The model is `stats::glm(cbind(count, donor_total-count) ~ condition,
family=binomial())`, followed by full-family `stats::p.adjust`. It reproduces the
same grouped-binomial estimand, **not donor-robust inference**. Descriptive mean
proportions give donors equal weight; fitted log odds pool binomial counts and
therefore give donors with more captured cells more binomial information.
No overdispersion, covariates, random effects or donor permutations are added.
Formal use still requires the study's reviewed denominator, dispersion, batch
and repeated-measures contract.

Fixed engineering bounds reject, never truncate: 64 MiB inputs, one million cell
rows, ten thousand donors, one thousand family entries and one million complete
donor-by-type rows. Output publication is a staged no-clobber ordinary-error
rollback, not a crash-atomic transaction or hostile namespace security boundary.

Self-cleaning non-statistical controls:

```sh
python3 -B -m unittest tests.test_donor_composition_official
```
