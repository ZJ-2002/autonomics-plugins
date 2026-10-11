# susie plugin

The original `susie_rss` kind calls author `susieR::susie_rss` 0.16.6,
source commit `ef213feed2cb82419677661a8c986e1504df2c73`, in
`ghcr.io/zj-2002/susie@sha256:b1df377e428e6166cd8ac65ac3e131c46c3bb68f172969c0e0f910751792d87e`.
The live script is `scripts/run_susie_rss.R.sh`, staged and executed by
Rscript. `run_susie_rss.R` is an archived baked runner, not the repaired
execution path. The image's Python query helper and libbgmg remain pinned.

## Input and signed LD

One literal, rectangular TSV contains unique `snp`, `chrom`, finite `z`,
and optional constant `n > 1`, `a1`, `a2`. IDs use GRCh37
`chr:position:allele1:allele2` on a single autosome. Both allele columns
must be present together. `a1` is the effect allele of `z`; absent columns
mean the ID's first allele is the effect allele. Exact reversals are
supported; strand guessing, rsID conversion and silent variant filtering
are not. A supplied sample-size override must agree with input `n`.

The signed-LD bundle `wjixiang/catalog-mixer-g1000-eur` is mounted at
`/panels/mixer_ref`. Its actual BIM allele order can be the reverse of its
ID allele order. The runner reads BIM columns 5/6 and applies
`R_effect = D R_BIM D`, preserving the supplied z-score orientation.
The query is explicitly normalized to the BIM allele orientation.

**The current MiXeR panel is sparse. Missing pairs are not known zeros.**
Every selected off-diagonal pair must be explicitly present, and the
assembled matrix must pass the declared float32-tolerant PSD check
(`minimum eigenvalue >= -1e-6 * variant_count`). No PSD repair, allele
repair or automatic dropping occurs. The committed 50-SNP fixture has
missing pairs and a minimum eigenvalue near -0.223 when absent entries
are incorrectly zero-filled: it now fails instead of publishing results.
This repair does not make the sparse panel suitable for general regional
fine mapping. The original 50-SNP fixture remains rejected; the separate
complete-matrix fixture is not a replacement study input.

For the default external-reference route, residual-variance estimation is
rejected. The
wrapper fixes the R seed immediately before the official call and rejects
nonconverged or invalid fit summaries. These are runtime safeguards, not
proof of the scientific validity of a locus or reference population.

## Complete signed-LD input route

With `ld_source="input"`, the same single TSV additionally contains
`ld_a1`, `ld_a2`, constant integer `ld_n > 1`, and one `ld:<SNP>` column
for every SNP row, in exactly the same order. Rows and matrix columns are
not intersected, dropped or reordered. The matrix describes signed
correlation of the declared counting alleles, not r-squared. Orientation
to the effect alleles is explicit. Finite correlations, range [-1,1],
symmetry and unit diagonal (absolute tolerance `1e-10`), and positive
semidefiniteness (`minimum eigenvalue >= -1e-10 * SNP count`) are checked.
No missing-pair zero filling, matrix repair or normalization occurs.
`r2_min` must be zero. Explicit LD supplied to the default mixer route is
rejected rather than ignored.

This opt-in route requires the engine's conditional `panels.when` support.
It declares no mixer bundle requirement, mount or fallback. Existing
engines that reject this field need a coordinated source upgrade; these
source changes do not update or restart any deployed daemon.

`ld_role` defaults to `external`. `in_sample` requires the input route
and known GWAS sample size equal to `ld_n`; only then can
`estimate_residual_variance=true` reach the author implementation. Equal
counts are not proof of identical participants, covariate adjustment,
ancestry or genome build. These remain research qualification duties.

`fixtures/complete_ld_50.tsv` uses the first 50 QC variants in a fixed
chr21 interval, complete signed PLINK LD from 489 reference founders,
and synthetic z scores. Its provenance records file hashes and an
independent BED-decoding correlation check. It is a technical test,
not real GWAS evidence or approval to change a study reference.

## Outputs

The declared ports remain TSV (0), untouched official fit RDS (1), and log
(2). Validation/runtime failures go to the log before result publication.
Existing output paths are never overwritten. Result publication uses
success-only temporary files and hard links, not a multi-file transaction
or crash-recovery protocol.

TSV retains `snp,pip,cs,alpha,mu,mu2,lbf` and adds `cs_all`. `cs` is the
last credible-set list index containing a SNP; `cs_all` contains every
such index separated by semicolons. These indices are not effect IDs.
`alpha` is the maximum single-effect assignment probability, and the
reported `mu/mu2/lbf` belong to that effect; they are not total posterior
coefficients. Negative-infinite log Bayes factors can be legitimate.
Use the RDS for full effect arrays and named credible sets.

## Actual wrapper tests

Tests require Podman, the exact cached image, the real cached chr21 panel,
and a separately installed author package from the pinned source archive.
Missing dependencies are failures, not skipped successes. Each test uses
only the declared three output ports. Nothing builds, pushes images,
reads production credentials, or alters deployment configuration.

```sh
SUSIE_TEST_EVIDENCE=/absolute/new/evidence-directory \
SUSIE_REFERENCE_LIBRARY=/absolute/fresh-author-R-library \
./test_susie_rss.sh
```

`tests/official_reference.R` independently calls the fresh author package,
compares the entire fit with attributes and every TSV column at a fixed
`1e-12` tolerance. This shares the pinned container and LD query results;
it is not an independent LD-provider validation or separate-OS test.
The original tests cover small complete-pair subsets and failure guards.
`tests/test_dense_contract.py` also exercises complete 50-variant matrices,
nonempty credible sets, coherent permutations and allele reversals,
multiple author parameter branches, and a known synthetic same-cohort
case with residual-variance estimation. `tests/dense_reference.R` compares
the whole author object and every TSV column, preserving `cs_all` strings
when reading the table. Dense wrapper tests do not mount the MiXeR panel.
Malformed matrices and declarations must fail without result publication.
The strong 50-variant L=20 EM case does not converge within the default
100 iterations: both the fresh author package and wrapper confirm that
failure, and no fit is published. A separately explicit 1000-iteration
case converges in 310 iterations and is compared at the unchanged numeric
tolerance. There is no automatic retry or iteration-budget increase.
None of these tests grants general statistical calibration, production
daemon deployment, population suitability or study approval.
