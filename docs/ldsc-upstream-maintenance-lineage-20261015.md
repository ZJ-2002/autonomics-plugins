# LDSC maintenance lineage: what the original project actually links

The original `bulik/ldsc` project explicitly directs readers to `CBIIT/ldsc` for
a more recent Python 3 implementation. This is independently verified from its
[immutable README](https://raw.githubusercontent.com/bulik/ldsc/2fdeeb3b44379408794154993dbd6101b8946b7e/README.md),
not inferred from a similar repository or image name.

- Original README commit: `2fdeeb3b44379408794154993dbd6101b8946b7e`.
- README SHA256: `f53daa5fdd1ee6ca5ec4c3b75eafe83b9c858a5698cc02e8cf9441fcb6a4cf7e`.
- Fixed CBIIT method source used here: `6c673952cee74bd5c57aef1555a03b1c015399a0`.
- Source capture: session `935a6d5de4be429a811ea769b536379b`, exit 0/CLEANED;
  manifest `e330f12314248eff66718b4341e0eeba4d47160e3f38e493cc9531d864e5d1e6`.

Thus the selected Python 3 lineage is explicitly linked by the original project.
It is still a **versioned continuation**, not a claim that every old Python 2
branch, every newer CBIIT commit or every inference convention is interchangeable.
Only the recorded fixed-source cases have numerical/engineering evidence.
The legacy broken PATH aliases in the current image remain excluded; source
presence or a version banner does not override actual script dispatch.

## Method recommendation is not an automatic reference selection

The plan's S14 source is the original
[heritability/genetic-correlation tutorial](https://github.com/bulik/ldsc/wiki/Heritability-and-Genetic-Correlation).
It recommends matching population and currently recommends using the same LD
scores for unpartitioned reference and regression weights. The canonical plugin
instead declares distinct Phase 3 basic-reference and no-MHC weight packages.
Their resource inventory and unequal SNP axes are explicitly audited separately.

This is a **research-method/reference selection review item**, not permission
for the adapter or agent to replace a frozen panel, silently intersect SNPs or
declare either recipe universally wrong. Using an author-linked implementation
does not settle reference selection, phenotype scale, prevalence or model
eligibility. No scientific configuration or production binding changes here.

Machine-readable scope: `evidence/ldsc-upstream-maintenance-link-20261015.json`.
This source-lineage observation grants neither full-version equivalence, current
DAG/deployment acceptance nor G0.
