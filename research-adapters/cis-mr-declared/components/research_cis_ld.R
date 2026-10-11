# Numerical admission for the declared correlated-cis official MR route.
# This does not qualify the LD panel's ancestry, dosage semantics, source
# sample overlap or any scientific gate. Never clips, reorders or repairs R.
cis_read_signed_ld <- function(path, variant_ids, numerical_policy) {
  check <- function(ok, message) if (!isTRUE(ok)) stop(message, call. = FALSE)
  check(is.character(variant_ids) && length(variant_ids) >= 2L &&
    !anyNA(variant_ids) && all(nzchar(variant_ids)) && !anyDuplicated(variant_ids),
    "Correlated cis requires the complete ordered multi-instrument identity")
  check(is.list(numerical_policy) && !anyDuplicated(names(numerical_policy)) &&
    setequal(names(numerical_policy), c("symmetry_tolerance", "minimum_rcond", "ridge_or_psd_projection")),
    "Numerical conditioning policy must be explicit")
  check(identical(numerical_policy$symmetry_tolerance, 1e-8) &&
    is.numeric(numerical_policy$minimum_rcond) && length(numerical_policy$minimum_rcond) == 1L &&
    is.finite(numerical_policy$minimum_rcond) && numerical_policy$minimum_rcond > 0 &&
    numerical_policy$minimum_rcond <= 1 && identical(numerical_policy$ridge_or_psd_projection, FALSE),
    "Invalid conditioning policy; numerical projection or ridge forbidden")
  data <- utils::read.delim(path, colClasses = "character", check.names = FALSE,
    quote = "", comment.char = "", na.strings = c("NA", ""))
  check(identical(names(data), c("snp", variant_ids)) &&
    identical(data[[1]], variant_ids), "Signed LD row/column identity or order differs")
  raw <- as.matrix(data[, -1, drop = FALSE])
  rho <- suppressWarnings(matrix(as.numeric(raw), nrow = nrow(raw), ncol = ncol(raw)))
  check(nrow(rho) == length(variant_ids) && ncol(rho) == length(variant_ids) &&
    all(is.finite(rho)) && all(abs(rho) <= 1 + 1e-8), "Complete finite signed correlation required")
  symmetry_error <- max(abs(rho - t(rho)))
  diagonal_error <- max(abs(diag(rho) - 1))
  check(symmetry_error <= numerical_policy$symmetry_tolerance && diagonal_error <= 1e-8,
    "Signed LD must be symmetric with unit diagonal")
  minimum_eigenvalue <- min(eigen(rho, symmetric = TRUE, only.values = TRUE)$values)
  check(is.finite(minimum_eigenvalue) && minimum_eigenvalue > 0,
    "Signed LD must be positive definite; singular/indefinite inputs are not repaired")
  # Explicitly exercise the same unmodified matrix's factorization. Admission
  # never substitutes the resulting factor or a reconstructed matrix as R.
  chol(rho)
  condition <- rcond(rho, norm = "O")
  check(is.finite(condition) && condition >= numerical_policy$minimum_rcond,
    "Signed LD fails the predeclared reciprocal conditioning threshold")
  dimnames(rho) <- list(variant_ids, variant_ids)
  list(matrix = rho, diagnostics = list(variants = length(variant_ids),
    minimum_eigenvalue = minimum_eigenvalue, reciprocal_condition_number = condition,
    maximum_symmetry_error = symmetry_error, maximum_diagonal_error = diagonal_error,
    matrix_reordered = FALSE, ridge_or_psd_projection = FALSE,
    scientific_LD_panel_qualification = FALSE))
}
