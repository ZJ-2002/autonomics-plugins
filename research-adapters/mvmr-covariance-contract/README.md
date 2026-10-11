# Frozen covariance receipt candidate

The node consumes actual recipe/data/matrix/evidence bytes and bundles the shared
stdlib validator. It creates one immutable-content receipt with no-clobber,
hash-before/after validation and fsync. It does not infer covariance or prove
that participants are disjoint. Supplied evidence IDs never become file paths.

UNRESOLVED is a data status: the container can succeed while retaining the
blocked covariance receipt, allowing the MVMR method to retain coefficients and
skip F/Q. The method independently rechecks the evidence and matrices.

Eight MiB per input is the current qualification bound; exceeding it blocks the
node rather than truncating variants. The cached Python image is software only.
Use `python -B scripts/build_mvmr_covariance_wrapper.py --check` to verify the
complete generated source. This candidate is not deployed or formally authorized;
joint selection/harmonization and protected producer/recovery acceptance remain.
