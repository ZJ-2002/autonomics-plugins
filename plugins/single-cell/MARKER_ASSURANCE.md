# Custom marker-mean annotation scope

This original canonical kind is a custom arithmetic rule, not an official
UCell, CellTypist, Seurat or calibrated biological classifier. Its original
five parameters, one H5AD input, two File outputs and resource declaration are
unchanged. The dedicated injected script bypasses the actual baked runner,
which does not implement this operation; the retained host workflow is not
the executed original image and its defects are recorded separately.

Only X is scored. With `none`, expression is not normalized. With `log_cp10k`,
the original row-total, 10000/positive-total, log1p sequence is retained;
nonnegative zero-total cells stay zero. Nonfinite totals/scales/results fail
instead of switching to a maximum-rescaling algorithm. Scoring uses Float64
with explicit finite and exact integer-domain checks; original X/raw/layers
and unrelated metadata remain in the output, including sparse layout.

Each marker-list mean includes every present repeated member. Duplicates thus
retain their original weights; they are not deduplicated or secretly mapped.
Missing members are omitted as in the retained original rule and disclosed;
an empty present list is refused. This is not study signature qualification.

Per-cell labels use the first JSON label in an exact score tie, and the chosen
score must be strictly above min_score. For groupby, cell scores are averaged
within each literal cluster, its winning label/decision margin are propagated,
and marker_score remains the cell's own score for that label; an unknown
fallback retains its own best candidate score. One-list margin is its top score.
Unknown is an arbitrary nonblank literal label, even when equal to a candidate
label. Assignment uses the index and a separate fallback mask, never a label
lookup that confuses the unknown label with a candidate. Missing/nonfinite
numeric group values are not silently turned into cluster strings.

JSON duplicate keys/constants, nonfinite scoring data, existing annotation
fields and existing output paths fail. Full outputs are staged, input identity
is rechecked after staging, and exclusive publication rolls back only owned
inodes using lstat. This is ordinary failure protection, not crash atomicity,
checkpoint recovery, cache certification or current deployment evidence.

Independent math tests use Decimal100 marker arithmetic and a separate
read-only official AnnData import prefix. Complete AnnData, literal axes,
integer metadata, scores/margins, membership and report semantics are checked.
Scores/margins are not probabilities; neither cell-level nor cluster-level
annotation provides donor-level disease inference, marker specificity or G0.

Primitive references: [NumPy mean](https://numpy.org/doc/2.2/reference/generated/numpy.mean.html),
[NumPy argmax and first-occurrence ties](https://numpy.org/doc/2.2/reference/generated/numpy.argmax.html).
No official classifier-equivalence certificate is asserted.
