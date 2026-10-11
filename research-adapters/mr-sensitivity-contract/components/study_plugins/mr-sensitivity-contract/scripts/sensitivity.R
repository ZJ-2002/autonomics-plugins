# Supporting methods over one actual frozen MR producer. No primary P selection.
sensitivity_config <- function(c) {
  exact_keys(c, c("status", "protocol_version", "analysis_id", "exposure_id", "outcome_id",
    "role", "seed", "nboot", "applicability", "allowed_warning_messages", "software_lock", "input_sha256"), "sensitivity configuration")
  check(identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version) &&
    identical(c$role, "SUPPORTING_ONLY"), "frozen supporting registered-protocol recipe required")
  for (k in c("analysis_id", "exposure_id", "outcome_id"))
    check(is.character(c[[k]]) && length(c[[k]]) == 1L && grepl("^[A-Za-z0-9._:-]+$", c[[k]]), "explicit analysis identities required")
  check(is.numeric(c$seed) && length(c$seed) == 1L && is.finite(c$seed) &&
    c$seed == floor(c$seed) && c$seed >= 1 && c$seed <= 2147483647, "frozen integer seed required")
  # A pinned computational profile, not a method chosen from observed P values.
  check(identical(c$nboot, 1000L), "this qualified candidate requires explicit nboot=1000")
  exact_keys(c$software_lock, c("R_version", "TwoSampleMR_version"), "software lock")
  check(identical(c$software_lock$R_version, as.character(getRversion())) &&
    identical(c$software_lock$TwoSampleMR_version, as.character(utils::packageVersion("TwoSampleMR"))), "software lock mismatch")
  exact_keys(c$applicability, c("weighted_median", "egger", "ivw_heterogeneity", "leave_one_out"), "applicability")
  check(all(vapply(c$applicability, function(x) is.character(x) && length(x) == 1L &&
    x %in% c("QUALIFIED", "NOT_QUALIFIED", "UNRESOLVED"), logical(1))), "explicit applicability decisions required")
  check((is.character(c$allowed_warning_messages) || identical(c$allowed_warning_messages, list())) && !anyNA(c$allowed_warning_messages) &&
    !anyDuplicated(c$allowed_warning_messages), "explicit warning policy required")
  exact_keys(c$input_sha256, c("parent_config", "harmonised", "variants", "parent_estimates", "parent_audit", "applicability_evidence"), "input identities")
  check(all(vapply(c$input_sha256, is_sha, logical(1))), "complete actual input SHA256 required")
}

sensitivity_inputs <- function(c, paths) {
  sensitivity_config(c)
  keys <- c("parent_config", "harmonised", "variants", "parent_estimates", "parent_audit", "applicability_evidence")
  hashes <- setNames(lapply(paths, sha), keys)
  check(all(vapply(keys, function(k) identical(c$input_sha256[[k]], hashes[[k]]), logical(1))), "sensitivity input content identity mismatch")
  parent <- jsonlite::fromJSON(paths[1L], simplifyVector = FALSE)
  parent$instrument_policy$tie_order <- unlist(parent$instrument_policy$tie_order, use.names = FALSE)
  parent$instrument_policy$palindrome_ambiguous_eaf <- unlist(parent$instrument_policy$palindrome_ambiguous_eaf, use.names = FALSE)
  validate_config(parent)
  check(identical(c$protocol_version, parent$protocol_version), "parent protocol differs")
  audit <- jsonlite::fromJSON(paths[5L], simplifyVector = FALSE)
  exact_keys(audit, c("scope", "analysis_id", "input_sha256", "software_lock", "outcome_normalization_record",
    "selection_evidence", "input_instruments", "retained_instruments", "instrument_policy", "overlap_class",
    "overlap_evidence_sha256", "regions", "primary_method_selection_from_P", "authorization"), "parent audit")
  check(identical(audit$scope, "OFFICIAL_HARMONIZATION_AND_IVW_NOT_CLUMP_ACCEPTANCE_OR_G0") &&
    identical(audit$authorization, "NONE") && identical(audit$primary_method_selection_from_P, FALSE), "parent audit scope differs")
  check(identical(audit$outcome_normalization_record$frozen_recipe$protocol_version, parent$protocol_version),
    "parent normalization protocol differs")
  audit$instrument_policy$tie_order <- unlist(audit$instrument_policy$tie_order, use.names = FALSE)
  audit$instrument_policy$palindrome_ambiguous_eaf <- unlist(audit$instrument_policy$palindrome_ambiguous_eaf, use.names = FALSE)
  for (k in c("analysis_id", "exposure_id", "outcome_id")) check(identical(c[[k]], parent[[k]]), "parent analysis identity mismatch")
  check(identical(audit$analysis_id, parent$analysis_id) && identical(audit$software_lock, parent$software_lock) &&
    identical(c$software_lock, parent$software_lock) && identical(audit$instrument_policy, parent$instrument_policy) &&
    identical(audit$regions, parent$regions) && identical(audit$overlap_class, parent$overlap_class) &&
    identical(audit$overlap_evidence_sha256, parent$overlap_evidence_sha256) &&
    identical(audit$input_sha256$config, hashes$parent_config), "parent frozen configuration/audit differs")
  for (k in names(parent$input_sha256)) check(identical(parent$input_sha256[[k]], audit$input_sha256[[k]]), "parent input identity differs")
  tab <- function(path) utils::read.delim(path, colClasses = "character", check.names = FALSE,
    quote = "", comment.char = "", na.strings = "NA")
  h <- tab(paths[2L]); v <- tab(paths[3L]); main <- tab(paths[4L])
  cols <- c("SNP", "beta.exposure", "se.exposure", "effect_allele.exposure", "other_allele.exposure",
    "eaf.exposure", "pval.exposure", "id.exposure", "exposure", "beta.outcome", "se.outcome",
    "effect_allele.outcome", "other_allele.outcome", "eaf.outcome", "pval.outcome", "id.outcome", "outcome", "mr_keep")
  check(identical(names(h), cols) && identical(names(v), c("snp", "chr", "pos", "status", "reason",
    "raw_eaf_exposure", "raw_eaf_outcome", "aligned_eaf_outcome", "F_approx")), "parent instrument output schema differs")
  check(!anyNA(h$SNP) && !anyDuplicated(h$SNP) && identical(h$SNP, v$snp) &&
    identical(h$SNP, as.character(audit$selection_evidence$selected_ids)) &&
    nrow(h) == audit$input_instruments && nrow(h) <= 4096, "complete parent instrument universe differs")
  check(all(h$mr_keep %in% c("TRUE", "FALSE")), "parent mr_keep is malformed")
  keep <- h$mr_keep == "TRUE"
  # ifelse(logical(0), ...) returns logical(0), unlike an empty character ledger.
  expected_status <- rep("EXCLUDED", length(keep)); expected_status[keep] <- "RETAINED"
  check(identical(v$status, expected_status) &&
    all(!is.na(v$reason)) && all(v$reason[keep] == "") && all(nzchar(v$reason[!keep])) &&
    sum(keep) == audit$retained_instruments, "parent keep/exclusion ledger differs")
  for (k in c("beta.exposure", "se.exposure", "beta.outcome", "se.outcome")) {
    original <- h[[k]]; h[[k]] <- suppressWarnings(as.numeric(original))
    check(all(is.finite(h[[k]][keep])), "kept estimates are nonfinite")
  }
  check(all(h$se.exposure[keep] > 0 & h$se.outcome[keep] > 0), "kept estimates have invalid SE")
  for (k in c("id.exposure", "exposure")) check(all(h[[k]][keep] == c$exposure_id), "parent exposure label differs")
  for (k in c("id.outcome", "outcome")) check(all(h[[k]][keep] == c$outcome_id), "parent outcome label differs")
  check(identical(names(main), c("analysis_id", "analysis_scope", "overlap_class", "method", "n_iv", "n_region_removed",
    "status", "reason", "beta", "se", "p", "lower_ci", "upper_ci", "Q", "Q_p", "primary_p", "primary_p_source")) &&
    nrow(main) == 3L && identical(main$analysis_scope, c("MAIN", paste0("LEAVE_", vapply(parent$regions, `[[`, character(1), "region_id"), "_OUT"))) &&
    all(main$analysis_id == c$analysis_id) && all(main$overlap_class == parent$overlap_class) &&
    suppressWarnings(as.integer(main$n_iv[1L])) == sum(keep), "complete parent estimates identity differs")
  h$mr_keep <- keep
  list(parent = parent, audit = audit, hashes = hashes, harmonised = h, variants = v, parent_estimates = main)
}

supporting_sensitivity <- function(config_path, paths) {
  c <- jsonlite::fromJSON(config_path, simplifyVector = TRUE)
  x <- sensitivity_inputs(c, paths); h <- x$harmonised[x$harmonised$mr_keep, , drop = FALSE]; n <- nrow(h)
  parameters <- TwoSampleMR::default_parameters(); parameters$nboot <- c$nboot
  RNGkind("Mersenne-Twister", "Inversion", "Rejection"); set.seed(c$seed)
  calls <- list()
  applicability <- function(key, minimum) {
    if (x$parent$overlap_class == "O3") return("PARENT_INPUTS_FROZEN_INVALID")
    if (c$applicability[[key]] != "QUALIFIED") return(paste0("APPLICABILITY_", c$applicability[[key]]))
    if (n < minimum) return("INSUFFICIENT_INSTRUMENTS")
    ""
  }
  invoke <- function(key, minimum, fun) {
    reason <- applicability(key, minimum); warnings <- character(); error <- NULL; value <- NULL
    if (!nzchar(reason)) value <- tryCatch(withCallingHandlers(fun(), warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w)); invokeRestart("muffleWarning")
    }), error = function(e) { error <<- conditionMessage(e); NULL })
    if (!is.null(error)) reason <- "OFFICIAL_METHOD_ERROR"
    if (length(setdiff(warnings, c$allowed_warning_messages))) reason <- "DISALLOWED_OFFICIAL_WARNING"
    calls[[key]] <<- list(attempted = !nzchar(applicability(key, minimum)), reason = reason,
      warnings = as.list(warnings), error = error)
    list(value = if (!nzchar(reason)) value else NULL, reason = reason)
  }
  wm <- invoke("weighted_median", 3L, function() TwoSampleMR::mr_weighted_median(h$beta.exposure, h$beta.outcome, h$se.exposure, h$se.outcome, parameters))
  eg <- invoke("egger", 3L, function() TwoSampleMR::mr_egger_regression(h$beta.exposure, h$beta.outcome, h$se.exposure, h$se.outcome, parameters))
  iv <- invoke("ivw_heterogeneity", 2L, function() TwoSampleMR::mr_ivw(h$beta.exposure, h$beta.outcome, h$se.exposure, h$se.outcome, parameters))
  lo <- invoke("leave_one_out", 3L, function() TwoSampleMR::mr_leaveoneout(h, parameters = parameters, method = TwoSampleMR::mr_ivw))
  status <- function(reason, usable) if (grepl("^APPLICABILITY_", reason)) "NOT_RUN" else if (!nzchar(reason) && usable) "ESTIMATED" else "NOT_ESTIMABLE"
  estimate <- function(method, call, keys, distribution, df = NA_integer_) {
    values <- if (is.null(call$value)) rep(NA_real_, 3) else vapply(keys, function(k) {
      y <- call$value[[k]]; if (is.numeric(y) && length(y) == 1L) y else NA_real_
    }, numeric(1))
    usable <- all(is.finite(values)) && values[2L] > 0 && values[3L] >= 0 && values[3L] <= 1
    reason <- call$reason
    if (!usable && !nzchar(reason)) reason <- "OFFICIAL_ESTIMATE_UNAVAILABLE"
    if (!usable) values[] <- NA_real_
    critical <- if (distribution == "T") stats::qt(.975, df) else stats::qnorm(.975)
    data.frame(analysis_id = c$analysis_id, method = method, role = "SUPPORTING_ONLY", n_iv = n,
      status = status(reason, usable), reason = reason, beta = values[1L], se = values[2L], p = values[3L],
      lower_ci = values[1L] - critical * values[2L], upper_ci = values[1L] + critical * values[2L],
      ci_distribution = distribution, ci_df = df, primary_p = NA_real_)
  }
  estimates <- rbind(estimate("WEIGHTED_MEDIAN", wm, c("b", "se", "pval"), "NORMAL"),
    estimate("MR_EGGER_SLOPE", eg, c("b", "se", "pval"), "T", if (n >= 3) n - 2L else NA_integer_),
    estimate("MR_EGGER_INTERCEPT", eg, c("b_i", "se_i", "pval_i"), "T", if (n >= 3) n - 2L else NA_integer_))
  heterogeneity <- function(method, call) {
    values <- if (is.null(call$value)) rep(NA_real_, 3) else vapply(c("Q", "Q_df", "Q_pval"), function(k) {
      y <- call$value[[k]]; if (is.numeric(y) && length(y) == 1L) y else NA_real_
    }, numeric(1))
    usable <- all(is.finite(values)) && values[1L] >= 0 && values[2L] > 0 && values[3L] >= 0 && values[3L] <= 1
    reason <- call$reason; if (!usable && !nzchar(reason)) reason <- "OFFICIAL_DIAGNOSTIC_UNAVAILABLE"
    if (!usable) values[] <- NA_real_
    data.frame(analysis_id = c$analysis_id, method = method, role = "SUPPORTING_ONLY", n_iv = n,
      status = status(reason, usable), reason = reason, Q = values[1L], Q_df = values[2L], Q_p = values[3L], primary_p = NA_real_)
  }
  heterogeneity <- rbind(heterogeneity("IVW", iv), heterogeneity("MR_EGGER", eg))
  # Row type disambiguates a legitimate variant named 'All' from the summary.
  ids <- c(h$SNP, NA_character_); types <- c(rep("LEAVE_ONE_OUT", n), "ALL_INSTRUMENTS")
  beta <- se <- p <- rep(NA_real_, n + 1L); reasons <- rep(lo$reason, n + 1L)
  if (!is.null(lo$value)) {
    d <- lo$value
    check(nrow(d) == n + 1L && identical(as.character(d$SNP), c(h$SNP, "All")), "official leave-one-out universe/order differs")
    beta <- d$b; se <- d$se; p <- d$p
  }
  usable <- is.finite(beta) & is.finite(se) & se > 0 & is.finite(p) & p >= 0 & p <= 1
  reasons[!usable & reasons == ""] <- "OFFICIAL_ESTIMATE_UNAVAILABLE"
  beta[!usable] <- se[!usable] <- p[!usable] <- NA_real_
  leave_one_out <- data.frame(analysis_id = c$analysis_id, row_type = types, omitted_snp = ids,
    role = "SUPPORTING_ONLY", n_iv = c(rep(max(0L, n - 1L), n), n),
    status = vapply(seq_along(reasons), function(i) status(reasons[i], usable[i]), character(1)), reason = reasons,
    beta = beta, se = se, p = p, lower_ci = beta - stats::qnorm(.975) * se,
    upper_ci = beta + stats::qnorm(.975) * se, primary_p = NA_real_)
  # Publication must never validate a prefix while source inputs drift.
  check(identical(x$hashes, setNames(lapply(paths, sha), names(x$hashes))), "sensitivity input changed during computation")
  list(estimates = estimates, heterogeneity = heterogeneity, leave_one_out = leave_one_out,
    audit = list(scope = "OFFICIAL_SUPPORTING_SENSITIVITIES_NOT_PRIMARY_SELECTION_OR_G0", authorization = "NONE",
      analysis_id = c$analysis_id, frozen_recipe = c, config_sha256 = sha(config_path), input_sha256 = x$hashes,
      parent_audit = x$audit, parent_estimates_sha256 = x$hashes$parent_estimates,
      complete_parent_ids = as.list(x$harmonised$SNP), retained_ids = as.list(h$SNP), calls = calls,
      parameters = parameters, minimum_instruments = list(weighted_median = 3L, egger = 3L, ivw_heterogeneity = 2L, leave_one_out = 3L),
      recomputed_harmonization = FALSE, primary_method_selection_from_P = FALSE, primary_p_supplied = FALSE))
}

main <- function(args) {
  check(length(args) == 11L, "usage: sensitivity.R config parent-config harmonised variants parent-estimates parent-audit applicability-evidence estimates heterogeneity leave-one-out audit")
  outputs <- args[8:11]
  check(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) { t <- Sys.readlink(p); !is.na(t) && nzchar(t) }, logical(1))), "output exists or duplicates another output")
  before <- sha(args[1L]); result <- supporting_sensitivity(args[1L], args[2:7])
  check(identical(before, sha(args[1L])) && identical(before, result$audit$config_sha256), "frozen sensitivity recipe changed")
  for (i in 1:3) utils::write.table(result[[i]], outputs[i], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  jsonlite::write_json(result$audit, outputs[4L], pretty = TRUE, auto_unbox = TRUE, null = "null", na = "null", digits = NA)
}
if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
