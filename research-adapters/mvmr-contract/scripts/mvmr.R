# Official two-exposure MVMR over frozen joint inputs. No G0 or source approval.
mv_check <- function(ok, message) if (!isTRUE(ok)) stop(message, call. = FALSE)
mv_keys <- function(x, keys, label) mv_check(is.list(x) && setequal(names(x), keys) &&
  !anyDuplicated(names(x)), paste(label, "schema differs"))
mv_sha <- function(p) digest::digest(file = p, algo = "sha256")
mv_link <- function(p) { target <- Sys.readlink(p); !is.na(target) & nzchar(target) }
mv_is_sha <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && grepl("^[0-9a-f]{64}$", x)
mv_ids <- function(x, label, minimum = 1L) {
  x <- unlist(x, use.names = FALSE)
  if (length(x) == 0L) x <- character()
  mv_check(is.character(x) && length(x) >= minimum && !anyNA(x) &&
    all(nzchar(x) & trimws(x) == x) && !anyDuplicated(x), paste(label, "identities differ"))
  x
}
mv_number <- function(x, label) {
  mv_check(is.numeric(x) && length(x) == 1L && is.finite(x), paste(label, "must be finite")); x
}

mv_config <- function(c) {
  mv_keys(c, c("status", "protocol_version", "analysis_id", "exposure_ids", "outcome_id",
    "family_id", "role", "snp_column", "outcome_columns", "exposure_columns", "seed",
    "conditional_f_threshold", "allowed_warning_messages", "software_lock", "input_sha256"), "MVMR configuration")
  mv_check(identical(c$status, "FROZEN") && is.character(c$protocol_version) &&
    length(c$protocol_version) == 1L && !is.na(c$protocol_version) &&
    c$protocol_version %in% c("4.2.1", "4.3.2") &&
    identical(c$family_id, "A_SPECIFICITY_MVMR") && identical(c$role, "CONDITIONAL_EXPLORATORY"),
    "explicit frozen supported MVMR specificity recipe required")
  for (k in c("analysis_id", "outcome_id")) mv_check(is.character(c[[k]]) && length(c[[k]]) == 1L &&
    grepl("^[A-Za-z0-9._:-]+$", c[[k]]), "explicit analysis and outcome identities required")
  exposures <- mv_ids(c$exposure_ids, "exposure", 2L)
  mv_check(length(exposures) == 2L, "only preregistered two-exposure models supported; larger models require another adapter")
  mv_keys(c$outcome_columns, c("beta", "se"), "outcome columns")
  mv_keys(c$exposure_columns, exposures, "exposure columns")
  for (e in exposures) mv_keys(c$exposure_columns[[e]], c("beta", "se"), "exposure effect/SE columns")
  columns <- c(c$snp_column, unlist(c$outcome_columns[c("beta", "se")], use.names = FALSE),
    unlist(lapply(exposures, function(e) c$exposure_columns[[e]][c("beta", "se")]), use.names = FALSE))
  mv_ids(columns, "columns"); mv_check(length(columns) == 7L, "explicit unique column names required")
  mv_number(c$seed, "seed"); mv_check(c$seed == floor(c$seed) && c$seed >= 1 && c$seed <= 2147483647, "integer seed required")
  mv_check(mv_number(c$conditional_f_threshold, "conditional F threshold") > 0, "positive frozen conditional F threshold required")
  warnings <- unlist(c$allowed_warning_messages, use.names = FALSE)
  mv_check(is.list(c$allowed_warning_messages) && (length(warnings) == 0 ||
    (is.character(warnings) && !anyNA(warnings) && !anyDuplicated(warnings))), "explicit warning policy required")
  mv_keys(c$software_lock, c("R_version", "MVMR_version", "jsonlite_version", "digest_version"), "software lock")
  mv_check(identical(c$software_lock$R_version, as.character(getRversion())) &&
    identical(c$software_lock$MVMR_version, "0.4.8") &&
    identical(c$software_lock$MVMR_version, as.character(utils::packageVersion("MVMR"))) &&
    identical(c$software_lock$jsonlite_version, as.character(utils::packageVersion("jsonlite"))) &&
    identical(c$software_lock$digest_version, as.character(utils::packageVersion("digest"))), "software lock mismatch")
  mv_keys(c$input_sha256, c("harmonized", "covariance_recipe", "covariance", "covariance_receipt",
    "covariance_evidence_pack", "joint_identity"), "input hashes")
  mv_check(all(vapply(c$input_sha256, mv_is_sha, logical(1))), "full actual input SHA256 required")
  list(exposures = exposures, columns = columns)
}

mv_inputs <- function(config_path, paths) {
  for (p in c(config_path, paths)) mv_check(file.exists(p) && !dir.exists(p) && !mv_link(p), "regular input file required")
  mv_check(all(file.info(c(config_path, paths))$size <= 8 * 1024^2), "small joint method input limit exceeded")
  c <- jsonlite::fromJSON(config_path, simplifyVector = FALSE); spec <- mv_config(c)
  keys <- names(c$input_sha256); ordered <- c("harmonized", "covariance_recipe", "covariance", "covariance_receipt", "covariance_evidence_pack", "joint_identity")
  hashes <- setNames(lapply(paths, mv_sha), ordered)
  mv_check(all(vapply(keys, function(k) identical(c$input_sha256[[k]], hashes[[k]]), logical(1))), "input content identity mismatch")
  data <- utils::read.delim(paths[1L], colClasses = "character", check.names = FALSE,
    quote = "", comment.char = "", na.strings = "NA")
  mv_check(identical(names(data), spec$columns) && nrow(data) <= 4096L, "joint input schema or instrument limit differs")
  snps <- mv_ids(data[[c$snp_column]], "joint SNP", 0L)
  for (column in spec$columns[-1L]) {
    data[[column]] <- suppressWarnings(as.numeric(data[[column]]))
    mv_check(all(is.finite(data[[column]])), "joint effect or SE nonfinite; no variant may be silently dropped")
  }
  se_columns <- c(c$outcome_columns$se, vapply(spec$exposures, function(e) c$exposure_columns[[e]]$se, character(1)))
  mv_check(all(as.matrix(data[, se_columns, drop = FALSE]) > 0), "positive joint standard errors required")
  recipe <- jsonlite::fromJSON(paths[2L], simplifyVector = FALSE)
  mv_keys(recipe, c("schema_version", "protocol_version", "status", "analysis_id", "purpose",
    "exposure_ids", "snp_column", "standard_error_columns", "input_sha256", "relative_tolerance"), "covariance recipe")
  mv_check(identical(recipe$schema_version, 1L) && identical(recipe$status, "FROZEN") &&
    identical(recipe$protocol_version, c$protocol_version) && identical(recipe$analysis_id, c$analysis_id) &&
    identical(recipe$purpose, "SNP_EXPOSURE_ESTIMATE_COVARIANCE") &&
    identical(mv_ids(recipe$exposure_ids, "covariance exposure", 2L), spec$exposures) &&
    identical(recipe$snp_column, c$snp_column), "covariance purpose, analysis or exposure axis differs")
  mv_keys(recipe$standard_error_columns, spec$exposures, "covariance SE columns")
  for (e in spec$exposures) mv_check(identical(recipe$standard_error_columns[[e]], c$exposure_columns[[e]]$se), "actual covariance SE column differs")
  mv_keys(recipe$input_sha256, c("harmonized_data", "covariance"), "covariance input hashes")
  mv_check(identical(recipe$input_sha256$harmonized_data, hashes$harmonized) &&
    identical(recipe$input_sha256$covariance, hashes$covariance), "actual covariance recipe hashes differ")
  tol <- mv_number(recipe$relative_tolerance, "covariance tolerance")
  mv_check(tol > 0 && tol <= 1e-8, "covariance tolerance must be within (0,1e-8]")
  supplied <- jsonlite::fromJSON(paths[3L], simplifyVector = FALSE)
  mv_keys(supplied, c("schema_version", "analysis_id", "purpose", "exposure_ids", "snp_ids", "matrices", "pair_provenance"), "supplied covariance")
  mv_check(identical(supplied$schema_version, 1L) && identical(supplied$analysis_id, c$analysis_id) &&
    identical(supplied$purpose, recipe$purpose) && identical(mv_ids(supplied$exposure_ids, "supplied exposure", 2L), spec$exposures) &&
    identical(mv_ids(supplied$snp_ids, "supplied SNP", 0L), snps) && is.list(supplied$matrices) &&
    length(supplied$matrices) == length(snps), "supplied covariance axes or matrix count differs")
  ses <- as.matrix(data[, vapply(spec$exposures, function(e) c$exposure_columns[[e]]$se, character(1)), drop = FALSE])
  matrices <- lapply(seq_along(snps), function(i) {
    a <- supplied$matrices[[i]]
    mv_check(is.list(a) && length(a) == 2L && all(vapply(a, function(r) is.list(r) && length(r) == 2L &&
      all(vapply(r, function(v) is.numeric(v) && length(v) == 1L && is.finite(v), logical(1))), logical(1))), "finite 2x2 SNP covariance matrix required")
    matrix <- matrix(unlist(a, use.names = FALSE), 2L, 2L, byrow = TRUE)
    corr <- matrix / outer(ses[i, ], ses[i, ])
    mv_check(all(is.finite(corr)) && max(abs(diag(corr) - 1)) <= tol &&
      max(abs(corr - t(corr))) <= tol, "actual SE diagonal or covariance symmetry differs")
    mv_check(min(eigen(corr, symmetric = TRUE, only.values = TRUE)$values) >= -tol, "SNP covariance not positive semidefinite")
    matrix
  })
  mv_check(is.list(supplied$pair_provenance) && length(supplied$pair_provenance) == 1L, "complete two-exposure covariance provenance required")
  pair <- supplied$pair_provenance[[1L]]
  mv_keys(pair, c("exposure_pair", "method", "sample_relationship", "evidence_id", "evidence_sha256", "justification", "status"), "pair provenance")
  mv_check(identical(mv_ids(pair$exposure_pair, "provenance exposure", 2L), spec$exposures) &&
    pair$method %in% c("SOURCE_DATA", "PROVIDER_MATRIX", "JUSTIFIED_CORRELATION_AND_OVERLAP_MODEL", "VALIDATED_SUMMARY_ESTIMATE", "JUSTIFIED_ZERO") &&
    pair$sample_relationship %in% c("DISJOINT", "FULL_OVERLAP", "KNOWN_PARTIAL_OVERLAP", "UNKNOWN_PARTIAL_OVERLAP") &&
    pair$status %in% c("RECORD_AVAILABLE_NOT_SCIENTIFICALLY_APPROVED", "UNRESOLVED"), "explicit covariance provenance required, not a scientific approval")
  mv_ids(list(pair$justification), "covariance justification"); mv_ids(list(pair$evidence_id), "covariance evidence identity")
  mv_check(!(pair$method == "JUSTIFIED_CORRELATION_AND_OVERLAP_MODEL" && pair$sample_relationship == "UNKNOWN_PARTIAL_OVERLAP"), "unknown partial overlap cannot use a fully specified overlap formula")
  if (pair$method == "JUSTIFIED_ZERO") mv_check(pair$sample_relationship == "DISJOINT" &&
    all(vapply(matrices, function(a) a[1L, 2L] == 0 && a[2L, 1L] == 0, logical(1))), "documented disjoint zero covariance required")
  pack <- jsonlite::fromJSON(paths[5L], simplifyVector = FALSE)
  mv_keys(pack, c("schema_version", "evidence"), "evidence pack")
  mv_check(identical(pack$schema_version, 1L), "evidence pack schema differs")
  mv_keys(pack$evidence, pair$evidence_id, "exact evidence artifact set")
  artifact <- pack$evidence[[pair$evidence_id]]
  mv_keys(artifact, c("sha256", "content_hex"), "source evidence artifact")
  mv_check(mv_is_sha(artifact$sha256) && identical(artifact$sha256, pair$evidence_sha256) &&
    is.character(artifact$content_hex) && length(artifact$content_hex) == 1L &&
    nchar(artifact$content_hex) %% 2 == 0 && grepl("^[0-9a-f]*$", artifact$content_hex), "actual evidence bytes or hash absent")
  hex <- artifact$content_hex; starts <- if (nzchar(hex)) seq.int(1L, nchar(hex), 2L) else integer()
  bytes <- as.raw(strtoi(substring(hex, starts, starts + 1L), base = 16L))
  mv_check(identical(digest::digest(bytes, algo = "sha256", serialize = FALSE), artifact$sha256), "source evidence artifact SHA256 mismatch")
  receipt <- jsonlite::fromJSON(paths[4L], simplifyVector = FALSE)
  mv_keys(receipt, c("schema_version", "scope", "status", "analysis_id", "exposure_ids", "snp_count", "pair_count", "input_sha256",
    "evidence_sha256", "unresolved_pairs", "scientific_approval_verified", "g0_pass", "formal_authorized", "mvmr_executed",
    "single_variable_mr_blocked", "implicit_zero_covariance"), "covariance preparation receipt")
  expected_status <- if (pair$status == "UNRESOLVED") "BLOCKED_UNRESOLVED_PROVENANCE" else "TECHNICAL_BYTES_VALIDATED"
  mv_check(identical(receipt$schema_version, 1L) && receipt$scope == "MVMR_COVARIANCE_PREPARATION_ONLY" &&
    identical(receipt$status, expected_status) && identical(receipt$analysis_id, c$analysis_id) &&
    identical(mv_ids(receipt$exposure_ids, "receipt exposure", 2L), spec$exposures) &&
    receipt$snp_count == length(snps) && identical(receipt$pair_count, 1L), "covariance receipt identity or status differs")
  mv_keys(receipt$input_sha256, c("recipe", "harmonized_data", "covariance"), "receipt inputs")
  mv_check(identical(receipt$input_sha256$recipe, hashes$covariance_recipe) &&
    identical(receipt$input_sha256$harmonized_data, hashes$harmonized) &&
    identical(receipt$input_sha256$covariance, hashes$covariance), "covariance receipt input hashes differ")
  mv_keys(receipt$evidence_sha256, pair$evidence_id, "receipt evidence")
  mv_check(identical(receipt$evidence_sha256[[pair$evidence_id]], artifact$sha256), "receipt evidence identity differs")
  for (flag in c("scientific_approval_verified", "g0_pass", "formal_authorized", "mvmr_executed", "single_variable_mr_blocked", "implicit_zero_covariance"))
    mv_check(identical(receipt[[flag]], FALSE), "covariance receipt must not assert authority or implicit zero")
  expected_unresolved <- if (pair$status == "UNRESOLVED") list(as.list(spec$exposures)) else list()
  mv_check(identical(receipt$unresolved_pairs, expected_unresolved), "receipt unresolved exposure pairs differ")
  joint <- jsonlite::fromJSON(paths[6L], simplifyVector = FALSE)
  mv_keys(joint, c("type", "analysis_id", "exposure_ids", "outcome_id", "snp_ids", "harmonized_sha256", "outcome_used_for_selection"), "joint identity")
  mv_check(identical(joint$type, "FROZEN_JOINT_INPUT_IDENTITY_NOT_SOURCE_QUALIFICATION") &&
    identical(joint$analysis_id, c$analysis_id) && identical(mv_ids(joint$exposure_ids, "joint exposure", 2L), spec$exposures) &&
    identical(joint$outcome_id, c$outcome_id) && identical(mv_ids(joint$snp_ids, "joint identity SNP", 0L), snps) &&
    identical(joint$harmonized_sha256, hashes$harmonized) && identical(joint$outcome_used_for_selection, FALSE), "joint input identity differs; selection claim still needs actual producer acceptance")
  list(config = c, config_sha256 = mv_sha(config_path), hashes = hashes, data = data,
    exposures = spec$exposures, snps = snps, covariance_recipe = recipe, supplied = supplied,
    matrices = matrices, covariance_receipt = receipt, joint_identity = joint,
    covariance_resolved = pair$status != "UNRESOLVED")
}

mv_compute <- function(x) {
  c <- x$config; n <- length(x$snps); p <- 2L
  RNGkind("Mersenne-Twister", "Inversion", "Rejection"); set.seed(c$seed)
  beta <- as.matrix(x$data[, vapply(x$exposures, function(e) c$exposure_columns[[e]]$beta, character(1)), drop = FALSE])
  se <- as.matrix(x$data[, vapply(x$exposures, function(e) c$exposure_columns[[e]]$se, character(1)), drop = FALSE])
  calls <- list(); raw <- list()
  invoke <- function(key, reason, fun) {
    warnings <- character(); error <- NULL; value <- NULL
    if (!nzchar(reason)) value <- tryCatch(withCallingHandlers(fun(), warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w)); invokeRestart("muffleWarning")
    }), error = function(e) { error <<- conditionMessage(e); NULL })
    raw[[key]] <<- value
    if (!is.null(error)) reason <- "OFFICIAL_METHOD_ERROR"
    if (length(setdiff(warnings, unlist(c$allowed_warning_messages, use.names = FALSE)))) reason <- "DISALLOWED_OFFICIAL_WARNING"
    calls[[key]] <<- list(attempted = !nzchar(if (key == "ivw") base_reason else diagnostic_reason),
      reason = reason, warnings = as.list(warnings), error = error)
    if (nzchar(reason)) return(NULL)
    value
  }
  base_reason <- if (n <= p) "INSUFFICIENT_INSTRUMENTS" else if (qr(beta)$rank < p) "JOINT_DESIGN_RANK_DEFICIENT" else ""
  diagnostic_reason <- if (nzchar(base_reason)) base_reason else if (!x$covariance_resolved) "COVARIANCE_PROVENANCE_UNRESOLVED" else ""
  formatted <- if (!nzchar(base_reason)) MVMR::format_mvmr(BXGs = beta, BYG = x$data[[c$outcome_columns$beta]],
    seBXGs = se, seBYG = x$data[[c$outcome_columns$se]], RSID = x$snps) else NULL
  # Pinned 0.4.8 ivw_mvmr does not use this argument. Explicit NULL neither
  # estimates missing covariance nor supplies a numeric zero assumption.
  ivw <- invoke("ivw", base_reason, function() MVMR::ivw_mvmr(formatted, gencov = NULL))
  strength <- invoke("strength", diagnostic_reason, function() MVMR::strength_mvmr(formatted, gencov = x$matrices))
  pleio_reason <- if (nzchar(diagnostic_reason)) diagnostic_reason else if (n <= p + 1L) "INSUFFICIENT_PLEIOTROPY_DF" else ""
  pleio <- invoke("pleiotropy", pleio_reason, function() MVMR::pleiotropy_mvmr(formatted, gencov = x$matrices))
  # Correct attempted independently of why an official invocation failed.
  calls$ivw$attempted <- !nzchar(base_reason)
  calls$strength$attempted <- !nzchar(diagnostic_reason)
  calls$pleiotropy$attempted <- !nzchar(pleio_reason)
  estimate_rows <- lapply(seq_len(p), function(i) {
    usable <- is.matrix(ivw) && nrow(ivw) == p && ncol(ivw) == 4L && all(is.finite(ivw[i, ])) && ivw[i, 2L] > 0 && ivw[i, 4L] >= 0 && ivw[i, 4L] <= 1
    reason <- calls$ivw$reason
    if (!usable && !nzchar(reason)) reason <- "OFFICIAL_ESTIMATE_UNAVAILABLE"
    b <- s <- prob <- low <- high <- NA_real_
    if (usable) { b <- ivw[i, 1L]; s <- ivw[i, 2L]; prob <- ivw[i, 4L]; q <- stats::qt(.975, n - p); low <- b - q * s; high <- b + q * s }
    data.frame(analysis_id = c$analysis_id, exposure_id = x$exposures[i], outcome_id = c$outcome_id,
      family_id = c$family_id, role = c$role, method = "IVW_MVMR_FIRST_ORDER", n_iv = n,
      status = if (usable) "ESTIMATED" else "NOT_ESTIMABLE", reason = reason, beta = b, se = s, p = prob,
      lower_ci = low, upper_ci = high, ci_distribution = "T", ci_df = if (usable) n - p else NA_integer_,
      covariance_status = if (x$covariance_resolved) "RECORD_AVAILABLE_NOT_SCIENTIFICALLY_APPROVED" else "UNRESOLVED",
      primary_p = NA_real_, direct_effect_scientifically_qualified = FALSE, stringsAsFactors = FALSE)
  })
  diagnostics <- lapply(seq_len(p), function(i) {
    usable <- is.data.frame(strength) && nrow(strength) == 1L && ncol(strength) == p &&
      is.finite(strength[1L, i]) && strength[1L, i] >= 0
    reason <- calls$strength$reason
    if (!usable && !nzchar(reason)) reason <- "OFFICIAL_STRENGTH_UNAVAILABLE"
    f <- if (usable) strength[1L, i] else NA_real_
    data.frame(analysis_id = c$analysis_id, diagnostic = "CONDITIONAL_F", exposure_id = x$exposures[i],
      n_iv = n, status = if (usable) "ESTIMATED" else if (reason == "COVARIANCE_PROVENANCE_UNRESOLVED") "NOT_RUN" else "NOT_ESTIMABLE",
      reason = reason, value = f, df = NA_integer_, p = NA_real_, threshold = c$conditional_f_threshold,
      strength_status = if (!usable) "UNRESOLVED" else if (f < c$conditional_f_threshold) "WEAK" else "NOT_WEAK_UNDER_FROZEN_THRESHOLD",
      direct_effect_scientifically_qualified = FALSE, stringsAsFactors = FALSE)
  })
  usable <- is.list(pleio) && is.numeric(pleio$Qstat) && length(pleio$Qstat) == 1L && is.finite(pleio$Qstat) &&
    pleio$Qstat >= 0 && is.numeric(pleio$Qpval) && length(pleio$Qpval) == 1L && is.finite(pleio$Qpval) && pleio$Qpval >= 0 && pleio$Qpval <= 1
  reason <- calls$pleiotropy$reason; if (!usable && !nzchar(reason)) reason <- "OFFICIAL_PLEIOTROPY_UNAVAILABLE"
  diagnostics[[3L]] <- data.frame(analysis_id = c$analysis_id, diagnostic = "PLEIOTROPY_Q", exposure_id = "ALL_EXPOSURES", n_iv = n,
    status = if (usable) "ESTIMATED" else if (reason == "COVARIANCE_PROVENANCE_UNRESOLVED") "NOT_RUN" else "NOT_ESTIMABLE",
    reason = reason, value = if (usable) pleio$Qstat else NA_real_, df = if (usable) n - p - 1L else NA_integer_,
    p = if (usable) pleio$Qpval else NA_real_, threshold = NA_real_, strength_status = "NOT_APPLICABLE",
    direct_effect_scientifically_qualified = FALSE, stringsAsFactors = FALSE)
  list(estimates = do.call(rbind, estimate_rows), diagnostics = do.call(rbind, diagnostics),
    calls = calls, original_official_results = raw, formatted = formatted)
}

main <- function(args) {
  mv_check(length(args) == 11L, "seven inputs and four outputs required")
  for (package in c("MVMR", "jsonlite", "digest")) mv_check(requireNamespace(package, quietly = TRUE), paste("package unavailable:", package))
  paths <- args[2:7]; outputs <- args[8:11]
  mv_check(!anyDuplicated(outputs) && all(!file.exists(outputs) & !mv_link(outputs)) &&
    length(unique(dirname(outputs))) == 1L, "output paths must be new and share a directory")
  x <- mv_inputs(args[1L], paths); value <- mv_compute(x)
  mv_check(identical(mv_sha(args[1L]), x$config_sha256) && all(vapply(seq_along(paths), function(i)
    identical(mv_sha(paths[i]), x$hashes[[i]]), logical(1))), "method input changed during execution")
  audit <- list(scope = "OFFICIAL_TWO_EXPOSURE_MVMR_NOT_JOINT_SOURCE_ACCEPTANCE_OR_G0", authorization = "NONE",
    analysis_id = x$config$analysis_id, config_sha256 = x$config_sha256, input_sha256 = x$hashes,
    frozen_recipe = x$config, software_lock = x$config$software_lock, covariance_recipe = x$covariance_recipe,
    covariance_receipt = x$covariance_receipt, joint_identity = x$joint_identity, retained_ids = as.list(x$snps),
    calls = value$calls, covariance_supplied_per_snp = TRUE, covariance_estimated_or_assumed_zero = FALSE,
    ivw_gencov_argument = "EXPLICIT_NULL_UNUSED_BY_PINNED_FUNCTION", recomputed_harmonization = FALSE,
    changed_instrument_selection = FALSE, primary_method_selection_from_P = FALSE, primary_p_supplied = FALSE,
    scientific_approval_verified = FALSE, direct_effect_scientifically_qualified = FALSE)
  stage <- tempfile(".mvmr-stage-", tmpdir = dirname(outputs[1L]))
  mv_check(dir.create(stage, mode = "0700", showWarnings = FALSE), "cannot establish owned output staging directory")
  on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  targets <- file.path(stage, c("estimates.tsv", "diagnostics.tsv", "audit.json", "result.rds"))
  options(digits = 17)
  utils::write.table(value$estimates, targets[1L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  utils::write.table(value$diagnostics, targets[2L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  jsonlite::write_json(audit, targets[3L], auto_unbox = TRUE, pretty = TRUE, digits = NA, na = "null", null = "null")
  saveRDS(list(official = value$original_official_results, formatted = value$formatted,
    actual_covariance = x$matrices, estimates = value$estimates, diagnostics = value$diagnostics, audit = audit),
    targets[4L], compress = FALSE, version = 3L)
  for (i in seq_along(outputs)) mv_check(file.link(targets[i], outputs[i]), "no-clobber output publication failed; container must not publish normal artifacts")
  cat("TECHNICAL_MVMR_METHOD_OUTPUTS_NOT_SCIENTIFIC_AUTHORIZATION\n")
}

if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
