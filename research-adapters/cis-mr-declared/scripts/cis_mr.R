# Generated from individually qualified component bytes; see component-source.json.

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

# Byte-bound official cis MR method component. Scientific authorization is
# external: this function cannot freeze a family, approve overlap, or sign G0.
# Load research_cis_ld.R from the same qualified source before calling.
cis_fit_declared <- function(config_path, data_path, ld_path, ledger_path) {
  check <- function(ok, message) if (!isTRUE(ok)) stop(message, call. = FALSE)
  exact <- function(x, keys, label) check(is.list(x) && !anyDuplicated(names(x)) &&
    setequal(names(x), keys), paste(label, "schema differs"))
  sha <- function(path) digest::digest(file = path, algo = "sha256")
  check(as.character(getRversion()) == "4.5.1" &&
    as.character(utils::packageVersion("MendelianRandomization")) == "0.10.0" &&
    as.character(utils::packageVersion("TwoSampleMR")) == "0.7.9", "Actual official software lock differs")
  config <- jsonlite::fromJSON(config_path, simplifyVector = FALSE)
  exact(config, c("schema_version", "status", "protocol_version", "source_archive_sha256",
    "analysis_id", "family_id", "estimand_id", "method_input_status", "mr_route", "settings",
    "original_instrument_ids", "retained_instrument_ids", "files", "software", "container_image_id",
    "numerical_policy", "alignment_identity", "sample_models",
    "source_overlap_assumptions_scientifically_verified", "scientific_authorization_granted_by_adapter"), "Configuration")
  check(is.numeric(config$schema_version) && length(config$schema_version) == 1L &&
    config$schema_version == 1 && identical(config$status, "CIS_METHOD_PARAMETERS_DECLARED") &&
    config$protocol_version %in% c("4.2.1", "4.3.2") && identical(config$family_id, "A_CIS_TARGETS") &&
    identical(config$source_overlap_assumptions_scientifically_verified, FALSE) &&
    identical(config$scientific_authorization_granted_by_adapter, FALSE), "Declared original cis component required")
  exact(config$software, c("R", "MendelianRandomization", "TwoSampleMR"), "Software declaration")
  check(identical(config$software$R, "4.5.1") && identical(config$software$MendelianRandomization, "0.10.0") &&
    identical(config$software$TwoSampleMR, "0.7.9"), "Declared official software lock differs")
  files <- c(data = data_path, signed_ld = ld_path, ledger = ledger_path)
  exact(config$files, names(files), "Input files")
  hashes <- list(config = sha(config_path))
  for (key in names(files)) {
    ref <- config$files[[key]]
    exact(ref, c("path", "bytes", "sha256"), paste(key, "identity"))
    actual <- sha(files[[key]])
    check(is.character(ref$sha256) && identical(actual, ref$sha256) &&
      is.numeric(ref$bytes) && ref$bytes == floor(ref$bytes) && ref$bytes > 0 &&
      file.info(files[[key]])$size == ref$bytes, "Actual input content identity differs")
    hashes[[key]] <- actual
  }
  original <- unlist(config$original_instrument_ids, use.names = FALSE)
  retained <- unlist(config$retained_instrument_ids, use.names = FALSE)
  check(is.character(original) && !anyNA(original) && !anyDuplicated(original) && all(nzchar(original)),
    "Original complete eligible instrument identity required")
  check(length(retained) == 0L || (is.character(retained) && !anyNA(retained) &&
    !anyDuplicated(retained) && all(retained %in% original)), "Retained instrument identity differs")
  data <- utils::read.delim(data_path, colClasses = "character", check.names = FALSE,
    quote = "", comment.char = "", na.strings = c("NA", ""))
  check(identical(names(data), c("SNP", "beta_X", "se_X", "beta_Y", "se_Y", "effect_allele", "other_allele", "F_approx")) &&
    identical(data$SNP, if (length(retained)) retained else character()), "Complete method variant order differs")
  for (key in c("beta_X", "se_X", "beta_Y", "se_Y", "F_approx")) {
    data[[key]] <- suppressWarnings(as.numeric(data[[key]]))
    check(all(is.finite(data[[key]])), "Nonfinite method data")
  }
  check(all(data$se_X > 0 & data$se_Y > 0) && all(data$F_approx >= 0) &&
    all(abs(data$F_approx - (data$beta_X / data$se_X)^2) <= 1e-10 * pmax(1, data$F_approx)),
    "Source standard errors or instrument strength identity differs")
  ledger <- utils::read.delim(ledger_path, colClasses = "character", check.names = FALSE,
    quote = "", comment.char = "", na.strings = c("NA", ""))
  check(!anyDuplicated(names(ledger)) && all(c("analysis_id", "variant_id", "exposure_tool", "mr_status") %in% names(ledger)) &&
    !anyNA(ledger$variant_id) && all(nzchar(ledger$variant_id)) && !anyDuplicated(ledger$variant_id) &&
    all(ledger$analysis_id == config$analysis_id) &&
    setequal(ledger$variant_id[ledger$exposure_tool == "YES"], original) &&
    setequal(ledger$variant_id[ledger$exposure_tool == "YES" & ledger$mr_status == "SOURCE_ALIGNED"], retained),
    "Original tool ledger lost or changed an instrument")
  exact(config$settings, c("analysis_id", "model", "overlap_basis", "overlap_evidence"), "Method settings")
  check(identical(config$settings$analysis_id, config$analysis_id), "Method-setting analysis identity differs")
  blocked <- c("BLOCKED_SOURCE_MISSING", "BLOCKED_NO_QUALIFIED_OVERLAP_CORRECTION",
    "BLOCKED_INDEPENDENT_SIGNAL_ESTIMATE_CONTRACT_REQUIRED", "BLOCKED_RETAINED_TOOL_COUNT_NO_WALD_FALLBACK",
    "BLOCKED_ZERO_EXPOSURE_BETA")
  ready <- c("READY_REQUIRES_NUMERICAL_LD_VALIDATION", "READY_FOR_DECLARED_METHOD_COMPONENT")
  check(config$method_input_status %in% c(ready, blocked), "Unregistered method-input state")
  result <- data.frame(analysis_id = config$analysis_id, family_id = config$family_id,
    mr_route = config$mr_route, model = config$settings$model, n_instruments = nrow(data),
    status = "NOT_RUN", estimate = NA_real_, se = NA_real_, p_raw = NA_real_, reason = config$method_input_status)
  fit <- NULL; ld_diagnostics <- NULL
  if (config$method_input_status %in% ready) {
    check(identical(config$settings$overlap_basis, "NON_OVERLAP_DECLARED"),
      "Unknown overlap cannot be substituted with zero correlation")
    if (config$mr_route == "SINGLE_CIS_WALD") {
      check(length(original) == 1L && nrow(data) == 1L && identical(config$settings$model, "WALD_FIRST_ORDER") &&
        data$beta_X != 0, "Original single cis Wald input required; no multi-tool fallback")
      fit <- TwoSampleMR::mr_wald_ratio(b_exp = data$beta_X, b_out = data$beta_Y,
        se_exp = data$se_X, se_out = data$se_Y, parameters = list())
      result$estimate <- fit$b; result$se <- fit$se; result$p_raw <- fit$pval
    } else {
      check(identical(config$mr_route, "MATCHED_LD_GLS") && length(original) >= 2L && nrow(data) >= 2L &&
        config$settings$model %in% c("FIXED", "MULTIPLICATIVE_RANDOM") && all(data$beta_X != 0),
        "Complete correlated multi-cis route and explicit model required")
      qualified <- cis_read_signed_ld(ld_path, retained, config$numerical_policy)
      ld_diagnostics <- qualified$diagnostics
      input <- MendelianRandomization::mr_input(bx = data$beta_X, bxse = data$se_X,
        by = data$beta_Y, byse = data$se_Y, corr = qualified$matrix, snps = retained)
      model <- if (config$settings$model == "FIXED") "fixed" else "random"
      fit <- MendelianRandomization::mr_ivw(input, model = model, robust = FALSE,
        penalized = FALSE, weights = "simple", psi = 0, correl = TRUE, distribution = "normal", alpha = 0.05)
      check(fit@SNPs == nrow(data) && identical(fit@Model, model), "Official method changed model or instrument count")
      result$estimate <- fit@Estimate; result$se <- fit@StdError; result$p_raw <- fit@Pvalue
    }
    check(is.finite(result$estimate) && is.finite(result$se) && result$se > 0 &&
      is.finite(result$p_raw) && result$p_raw >= 0 && result$p_raw <= 1, "Official estimator output invalid")
    result$status <- "ESTIMATED_TECHNICAL_COMPONENT"; result$reason <- "SCIENTIFIC_ACCEPTANCE_EXTERNAL"
  }
  check(identical(sha(config_path), hashes$config) &&
    all(vapply(names(files), function(key) identical(sha(files[[key]]), hashes[[key]]), logical(1))),
    "Method input mutated during official fitting")
  list(estimate = result, fit = fit, audit = list(protocol_version = config$protocol_version,
    analysis_id = config$analysis_id, input_sha256 = hashes, alignment_identity = config$alignment_identity,
    source_archive_sha256 = config$source_archive_sha256, software = config$software,
    declared_container_image_id = config$container_image_id, original_instrument_ids = original,
    retained_instrument_ids = retained, numerical_LD_diagnostics = ld_diagnostics,
    sample_overlap_scientifically_verified = FALSE, scientific_authorization_granted_by_adapter = FALSE,
    actual_estimator_run = config$method_input_status %in% ready,
    method_role = "OFFICIAL_NUMERICAL_COMPONENT_NOT_SCIENTIFICALLY_ACCEPTED", session = capture.output(sessionInfo())))
}

# Plugin entry. Every output is a technical component artifact; neither the
# node nor a parameter may grant scientific acceptance or formal execution.
input_paths <- vapply(0:3, function(i) Sys.getenv(paste0("AUTONOMICS_INPUT", i)), character(1))
output_paths <- vapply(0:2, function(i) Sys.getenv(paste0("AUTONOMICS_OUTPUT", i)), character(1))
if (any(!nzchar(input_paths)) || any(!file.exists(input_paths)) ||
    any(!nzchar(output_paths)) || anyDuplicated(output_paths) || any(file.exists(output_paths)))
  stop("Four actual inputs and three fresh distinct outputs required", call. = FALSE)
answer <- cis_fit_declared(input_paths[[1]], input_paths[[2]], input_paths[[3]], input_paths[[4]])
answer$audit$artifact_scope <- "OFFICIAL_CIS_TECHNICAL_COMPONENT_NOT_FORMAL_AUTHORIZATION"
script <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE))
if (length(script) != 1L || !file.exists(script)) stop("Actual adapter script identity unavailable")
answer$audit$adapter_script_sha256 <- digest::digest(file = script, algo = "sha256")
for (path in output_paths) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
write.table(answer$estimate, output_paths[[1]], quote = FALSE, row.names = FALSE, sep = "\t", na = "NA")
jsonlite::write_json(answer$audit, output_paths[[2]], auto_unbox = TRUE, digits = 17, null = "null", na = "null")
saveRDS(answer, output_paths[[3]], version = 3)
