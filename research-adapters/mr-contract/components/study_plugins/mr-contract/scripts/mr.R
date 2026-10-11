# 官方 TwoSampleMR 的冻结工具输入适配器；本文件不做 clumping、不签署 G0。
# 工具选择必须由已验收的独立上游完成，不能从 outcome 的可用行反选工具。
fail <- function(message) stop(message, call. = FALSE)
check <- function(ok, message) if (!isTRUE(ok)) fail(message)
sha <- function(path) digest::digest(file = path, algo = "sha256")
is_sha <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && grepl("^[0-9a-f]{64}$", x)
exact_keys <- function(x, keys, label) check(is.list(x) && setequal(names(x), keys) &&
  !anyDuplicated(names(x)), paste(label, "schema differs"))
table_input <- function(path) {
  d <- utils::read.delim(path, colClasses = "character", check.names = FALSE,
    quote = "", comment.char = "", na.strings = c("NA", ""))
  check(identical(names(d), c("snp", "chr", "pos", "beta", "se", "effect_allele",
    "other_allele", "eaf", "pval")), "normalized SNP table schema differs")
  check(!anyNA(d$snp) && all(grepl("^[A-Za-z0-9._:+-]+$", d$snp)) &&
    !anyDuplicated(d$snp), "empty or duplicate variant identity")
  for (column in c("chr", "pos", "beta", "se", "eaf", "pval")) {
    original <- d[[column]]
    d[[column]] <- suppressWarnings(as.numeric(original))
    check(!any(!is.na(original) & !is.finite(d[[column]])), "nonnumeric SNP value")
  }
  check(all(is.finite(d$chr) & d$chr %in% 1:22) &&
    all(is.finite(d$pos) & d$pos >= 1 & d$pos == floor(d$pos)), "unqualified variant coordinates")
  check(all(is.na(d$eaf) | (d$eaf >= 0 & d$eaf <= 1)) &&
    all(is.na(d$pval) | (d$pval >= 0 & d$pval <= 1)), "invalid frequency or P")
  d
}

validate_config <- function(c) {
  exact_keys(c, c("status", "protocol_version", "analysis_id", "exposure_id", "outcome_id",
    "build", "ancestry", "instrument_class", "instrument_policy", "overlap_class",
    "overlap_evidence_sha256", "outcome_normalization_recipe_sha256", "regions", "software_lock", "seed", "input_sha256"), "configuration")
  check(identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version),
    "frozen supported-protocol configuration required; templates are not runnable")
  for (key in c("analysis_id", "exposure_id", "outcome_id"))
    check(is.character(c[[key]]) && length(c[[key]]) == 1L &&
      grepl("^[A-Za-z0-9._:-]+$", c[[key]]), "frozen analysis/phenotype identity required")
  check(c$build %in% c("GRCh37", "GRCh38") && is.character(c$ancestry) &&
    length(c$ancestry) == 1L && nzchar(c$ancestry), "build or ancestry unqualified")
  check(identical(c$instrument_class, "COMPLEX_TRAIT"), "cis/correlated instruments need a separately qualified adapter")
  exact_keys(c$instrument_policy, c("p_threshold", "clump_r2", "clump_kb", "tie_order",
    "harmonise_action", "palindrome_ambiguous_eaf", "boundaries_inclusive",
    "palindrome_max_eaf_difference", "palindrome_missing_eaf", "proxy_primary", "min_primary_iv"), "instrument policy")
  p <- c$instrument_policy
  check(identical(p$p_threshold, 5e-8) && identical(p$clump_r2, 0.001) &&
    identical(p$clump_kb, 10000L) && identical(p$tie_order, c("pval", "chr", "pos", "snp")) &&
    identical(p$harmonise_action, 2L) && identical(p$palindrome_ambiguous_eaf, c(0.42, 0.58)) &&
    identical(p$boundaries_inclusive, TRUE) && identical(p$palindrome_max_eaf_difference, 0.1) &&
    identical(p$palindrome_missing_eaf, "EXCLUDE") && identical(p$proxy_primary, FALSE) &&
    identical(p$min_primary_iv, 3L), "instrument policy differs from v4.2.1")
  check(c$overlap_class %in% c("O0", "O1", "O2", "O3") &&
    is_sha(c$overlap_evidence_sha256), "frozen overlap decision and provenance required")
  exact_keys(c$software_lock, c("R_version", "TwoSampleMR_version"), "software lock")
  check(identical(c$software_lock$R_version, as.character(getRversion())) &&
    identical(c$software_lock$TwoSampleMR_version, as.character(utils::packageVersion("TwoSampleMR"))),
    "software lock mismatch")
  check(is.numeric(c$seed) && length(c$seed) == 1L && is.finite(c$seed) &&
    c$seed == floor(c$seed) && c$seed >= 1 && c$seed <= 2147483647, "frozen integer seed required")
  check(is.list(c$regions) && length(c$regions) == 2L &&
    setequal(vapply(c$regions, function(r) r$region_id, character(1)), c("MHC", "TERT")),
    "both prespecified MHC and TERT intervals required")
  for (r in c$regions) {
    exact_keys(r, c("region_id", "chr", "start", "end", "build", "annotation_sha256"), "region")
    check(identical(r$build, c$build) && r$chr %in% 1:22 &&
      is.numeric(r$start) && is.numeric(r$end) && r$start >= 1 && r$end >= r$start &&
      r$start == floor(r$start) && r$end == floor(r$end) && is_sha(r$annotation_sha256),
      "region coordinate or annotation identity differs")
  }
  check(is_sha(c$outcome_normalization_recipe_sha256), "actual frozen outcome source recipe identity required")
  exact_keys(c$input_sha256, c("exposure", "outcome", "selection", "outcome_normalization"), "input hashes")
  check(all(vapply(c$input_sha256, is_sha, logical(1))), "complete input hashes required")
}

mr_frozen <- function(config_path, exposure_path, outcome_path, selection_path, outcome_normalization_path, outcome_normalization_recipe_path) {
  for (package in c("jsonlite", "digest", "TwoSampleMR"))
    check(requireNamespace(package, quietly = TRUE), paste("package unavailable:", package))
  c <- jsonlite::fromJSON(config_path, simplifyVector = FALSE)
  # 恢复固定向量字段，但不隐式转换整个配置或修改统计参数。
  if (!is.null(c$instrument_policy)) {
    c$instrument_policy$tie_order <- unlist(c$instrument_policy$tie_order, use.names = FALSE)
    c$instrument_policy$palindrome_ambiguous_eaf <- unlist(c$instrument_policy$palindrome_ambiguous_eaf, use.names = FALSE)
  }
  validate_config(c)
  hashes <- list(config = sha(config_path), exposure = sha(exposure_path), outcome = sha(outcome_path), selection = sha(selection_path),
    outcome_normalization = sha(outcome_normalization_path), outcome_normalization_recipe = sha(outcome_normalization_recipe_path))
  check(all(vapply(names(c$input_sha256), function(k) identical(c$input_sha256[[k]], hashes[[k]]), logical(1))),
    "input content identity mismatch")
  normal <- normalization_receipt(outcome_normalization_path, outcome_normalization_recipe_path,
    outcome_path, c$outcome_normalization_recipe_sha256, c$outcome_id, c$build, c$ancestry, c$protocol_version)
  selection <- jsonlite::fromJSON(selection_path, simplifyVector = TRUE)
  exact_keys(selection, c("type", "exposure_id", "selected_exposure_sha256", "source_exposure_sha256",
    "selected_ids", "p_threshold", "clump_r2", "clump_kb", "tie_order", "ancestry", "build",
    "panel_manifest_sha256", "normalization_evidence_sha256", "selection_execution_evidence_sha256", "outcome_used_for_selection"), "selection evidence")
  check(identical(selection$type, "EXPOSURE_ONLY_CLUMP_COMPLETION") &&
    identical(selection$exposure_id, c$exposure_id) && identical(selection$selected_exposure_sha256, hashes$exposure) &&
    is_sha(selection$source_exposure_sha256) && is_sha(selection$panel_manifest_sha256) &&
    is_sha(selection$normalization_evidence_sha256) && is_sha(selection$selection_execution_evidence_sha256) && identical(selection$outcome_used_for_selection, FALSE) &&
    identical(selection$p_threshold, 5e-8) && identical(selection$clump_r2, 0.001) &&
    identical(selection$clump_kb, 10000L) && identical(selection$tie_order, c("pval", "chr", "pos", "snp")) &&
    identical(selection$ancestry, c$ancestry) && identical(selection$build, c$build),
    "exposure-only selection provenance differs; audit alone does not qualify clumping")
  exposure <- table_input(exposure_path); outcome <- table_input(outcome_path)
  check(nrow(outcome) == normal$retained_rows, "normalized outcome source row count differs")
  check(identical(exposure$snp, as.character(selection$selected_ids)), "selected instrument universe differs")
  check(all(is.finite(exposure$pval) & exposure$pval < 5e-8) &&
    all(is.finite(exposure$beta) & is.finite(exposure$se) & exposure$se > 0), "selected exposure instruments invalid or nonsignificant")
  check(identical(order(exposure$pval, exposure$chr, exposure$pos, exposure$snp, method = "radix"), seq_len(nrow(exposure))),
    "selected instruments are not in frozen deterministic order")
  aligned_index <- match(exposure$snp, outcome$snp)
  present <- !is.na(aligned_index)
  allele_ok <- function(d) !is.na(d$effect_allele) & !is.na(d$other_allele) &
    d$effect_allele %in% c("A", "C", "G", "T") & d$other_allele %in% c("A", "C", "G", "T") &
    d$effect_allele != d$other_allele
  other <- outcome[aligned_index, , drop = FALSE]
  reason <- rep("", nrow(exposure))
  reason[!present] <- "DIRECT_OUTCOME_VARIANT_MISSING"
  reason[present & (exposure$chr != other$chr | exposure$pos != other$pos)] <- "VARIANT_COORDINATES_DIFFER"
  invalid <- !allele_ok(exposure) | !allele_ok(other) |
    !is.finite(other$beta) | !is.finite(other$se) | other$se <= 0
  reason[reason == "" & invalid] <- "INVALID_ALLELES_OR_OUTCOME_ESTIMATE"
  eligible <- reason == ""
  base <- function(d, side, label) {
    result <- d[, c("snp", "beta", "se", "effect_allele", "other_allele", "eaf", "pval"), drop = FALSE]
    names(result) <- c("SNP", paste0(c("beta", "se", "effect_allele", "other_allele", "eaf", "pval"), ".", side))
    result[[paste0("id.", side)]] <- label; result[[side]] <- label
    result
  }
  columns <- c("SNP", "beta.exposure", "se.exposure", "effect_allele.exposure", "other_allele.exposure",
    "eaf.exposure", "pval.exposure", "id.exposure", "exposure", "beta.outcome", "se.outcome",
    "effect_allele.outcome", "other_allele.outcome", "eaf.outcome", "pval.outcome", "id.outcome", "outcome", "mr_keep")
  harmonised <- as.data.frame(setNames(rep(list(rep(NA, nrow(exposure))), length(columns)), columns))
  harmonised$SNP <- exposure$snp; harmonised$mr_keep <- rep(FALSE, nrow(exposure))
  if (any(eligible)) {
    raw <- TwoSampleMR::harmonise_data(base(exposure[eligible, ], "exposure", c$exposure_id),
      base(other[eligible, ], "outcome", c$outcome_id), action = 2L)
    check(!anyDuplicated(raw$SNP) && setequal(raw$SNP, exposure$snp[eligible]), "official harmonization changed variant universe")
    raw <- raw[match(exposure$snp[eligible], raw$SNP), , drop = FALSE]
    for (column in intersect(columns, names(raw))) harmonised[eligible, column] <- raw[[column]]
    reason[eligible & !harmonised$mr_keep] <- "OFFICIAL_HARMONIZATION_REJECTED"
  }
  palindromic <- (exposure$effect_allele == "A" & exposure$other_allele == "T") |
    (exposure$effect_allele == "T" & exposure$other_allele == "A") |
    (exposure$effect_allele == "C" & exposure$other_allele == "G") |
    (exposure$effect_allele == "G" & exposure$other_allele == "C")
  palindromic[is.na(palindromic)] <- FALSE
  missing_eaf <- palindromic & present & (is.na(exposure$eaf) | is.na(other$eaf))
  ambiguous <- palindromic & present & ((exposure$eaf >= 0.42 & exposure$eaf <= 0.58) |
    (other$eaf >= 0.42 & other$eaf <= 0.58)); ambiguous[is.na(ambiguous)] <- FALSE
  # 原始频率的含边界排除先于方向校正；频差比较使用官方对齐后的频率。
  reason[eligible & missing_eaf] <- "PALINDROME_EAF_MISSING"
  reason[eligible & !missing_eaf & ambiguous] <- "PALINDROME_AMBIGUOUS_EAF_INCLUSIVE"
  difference <- abs(harmonised$eaf.exposure - harmonised$eaf.outcome)
  mismatch <- palindromic & eligible & reason == "" & is.finite(difference) &
    difference > 0.1 + 8 * .Machine$double.eps
  reason[mismatch] <- "PALINDROME_ALIGNED_EAF_DIFFERENCE"
  harmonised$mr_keep <- reason == ""
  ledger <- data.frame(snp = exposure$snp, chr = exposure$chr, pos = exposure$pos,
    status = ifelse(harmonised$mr_keep, "RETAINED", "EXCLUDED"), reason = reason,
    raw_eaf_exposure = exposure$eaf, raw_eaf_outcome = other$eaf,
    aligned_eaf_outcome = harmonised$eaf.outcome, F_approx = (exposure$beta / exposure$se)^2)
  estimate <- function(region) {
    keep <- harmonised$mr_keep
    removed <- rep(FALSE, length(keep))
    if (!is.null(region)) {
      removed <- exposure$chr == region$chr & exposure$pos >= region$start & exposure$pos <= region$end
      keep <- keep & !removed
    }
    n <- sum(keep); b <- se <- p <- Q <- Qp <- NA_real_
    method <- "NONE"; status <- "NOT_ESTIMABLE"; why <- "NO_VALID_INSTRUMENTS"
    if (c$overlap_class == "O3") why <- "FROZEN_INVALID_PRIMARY_INPUTS"
    else if (n > 0L) {
      d <- harmonised[keep, , drop = FALSE]
      if (n == 1L) {
        r <- TwoSampleMR::mr_wald_ratio(d$beta.exposure, d$beta.outcome, d$se.exposure, d$se.outcome)
        method <- "mr_wald_ratio"
      } else {
        # mr_ivw 校正 sigma<1 的欠离散，保持 SE 不低于固定效应 SE。
        r <- TwoSampleMR::mr_ivw(d$beta.exposure, d$beta.outcome, d$se.exposure, d$se.outcome)
        method <- "mr_ivw"; Q <- r$Q; Qp <- r$Q_pval
      }
      b <- r$b; se <- r$se; p <- r$pval
      if (all(is.finite(c(b, se, p))) && se > 0 && p >= 0 && p <= 1) {
        status <- "ESTIMATED"; why <- if (n < 3) "LIMITED_INSTRUMENT_SUPPORT_ONLY" else ""
      } else { b <- se <- p <- NA_real_; why <- "OFFICIAL_ESTIMATE_UNAVAILABLE" }
    }
    primary <- is.null(region) && status == "ESTIMATED" && n >= 3L && c$overlap_class == "O0"
    data.frame(analysis_id = c$analysis_id, analysis_scope = if (is.null(region)) "MAIN" else paste0("LEAVE_", region$region_id, "_OUT"),
      overlap_class = c$overlap_class, method = method, n_iv = n, n_region_removed = sum(removed & harmonised$mr_keep),
      status = status, reason = why, beta = b, se = se, p = p,
      lower_ci = b - stats::qnorm(0.975) * se, upper_ci = b + stats::qnorm(0.975) * se,
      Q = Q, Q_p = Qp, primary_p = if (primary) p else NA_real_,
      primary_p_source = if (primary) "O0_IVW" else "NOT_SUPPLIED_BY_THIS_ADAPTER")
  }
  RNGkind("Mersenne-Twister", "Inversion", "Rejection"); set.seed(c$seed)
  estimates <- do.call(rbind, c(list(estimate(NULL)), lapply(c$regions, estimate)))
  list(estimates = estimates, harmonised = harmonised, variants = ledger,
    audit = list(scope = "OFFICIAL_HARMONIZATION_AND_IVW_NOT_CLUMP_ACCEPTANCE_OR_G0",
      analysis_id = c$analysis_id, input_sha256 = hashes, software_lock = c$software_lock,
      outcome_normalization_record = normal,
      selection_evidence = selection, input_instruments = nrow(exposure), retained_instruments = sum(harmonised$mr_keep),
      instrument_policy = c$instrument_policy, overlap_class = c$overlap_class,
      overlap_evidence_sha256 = c$overlap_evidence_sha256, regions = c$regions,
      primary_method_selection_from_P = FALSE, authorization = "NONE"))
}

main <- function(args) {
  check(length(args) == 10L, "usage: mr.R config exposure outcome selection outcome-normalization-receipt outcome-normalization-recipe estimates harmonised variants audit")
  outputs <- args[7:10]
  check(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) { t <- Sys.readlink(p); !is.na(t) && nzchar(t) }, logical(1))), "output exists or duplicates another output")
  result <- mr_frozen(args[1L], args[2L], args[3L], args[4L], args[5L], args[6L])
  for (i in 1:3) utils::write.table(result[[i]], outputs[i], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  jsonlite::write_json(result$audit, outputs[4L], pretty = TRUE, auto_unbox = TRUE, null = "null", na = "null", digits = NA)
}
if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
