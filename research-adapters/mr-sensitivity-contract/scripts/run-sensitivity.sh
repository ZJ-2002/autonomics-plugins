#!/bin/sh
set -eu
SCRIPT=$(mktemp /tmp/autonomics-mr-sensitivity-XXXXXX.R)
trap 'rm -f "$SCRIPT"' EXIT HUP INT TERM
cat > "$SCRIPT" <<'AUTONOMICS_FROZEN_MR_SENSITIVITY'
# Shared, embedded in manifest-hashed wrappers. Never grants scientific admission.
frozen_protocol_supported <- function(x) {
  is.character(x) && length(x) == 1L && !is.na(x) && x %in% c("4.2.1", "4.3.2")
}
normalization_receipt <- function(path, recipe_path, normalized_path, recipe_sha256,
                                  construct_id, build, ancestry, protocol_version) {
  demand <- function(ok, message) {
    if (!isTRUE(ok)) stop(paste0("normalization provenance: ", message), call. = FALSE)
  }
  demand(frozen_protocol_supported(protocol_version), "unsupported parent protocol")
  digest_string <- function(x) is.character(x) && length(x) == 1L && !is.na(x) &&
    grepl("^[0-9a-f]{64}$", x)
  exact <- function(x, expected) demand(is.list(x) && setequal(names(x), expected) &&
    !anyDuplicated(names(x)), "schema differs")
  identity <- function(x) {
    exact(x, c("sha256", "bytes"))
    demand(digest_string(x$sha256) && is.numeric(x$bytes) && length(x$bytes) == 1L &&
      is.finite(x$bytes) && x$bytes >= 0 && x$bytes == floor(x$bytes), "invalid artifact identity")
  }
  for (p in c(path, recipe_path)) demand(file.exists(p) && !dir.exists(p) &&
    file.info(p)$size > 0 && file.info(p)$size <= 16*1024^2, "receipt/recipe absent or oversized")
  demand(digest_string(recipe_sha256) &&
    identical(digest::digest(file = recipe_path, algo = "sha256"), recipe_sha256),
    "actual source recipe differs from frozen identity")
  n <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  extra <- if (is.null(n$decoding)) character(0) else "decoding"
  exact(n, c(extra, "schema_version", "operation", "authorization", "scope", "config", "raw", "metadata",
    "frozen_recipe", "source_rows", "retained_rows", "excluded_rows", "exclusion_reasons",
    "p_numeric_underflows", "sample_size_imputed", "build_transformed", "alleles_swapped_or_complemented",
    "output", "duplicate_identity_sort", "duplicate_identity_sort_execution"))
  demand(identical(n$schema_version, 1L) && identical(n$operation, "frozen_gwas_normalize") &&
    identical(n$authorization, "NONE") &&
    identical(n$scope, "EXPLICIT_TABULAR_TRANSFORMATION_NOT_RESOURCE_OR_SCIENTIFIC_APPROVAL") &&
    identical(n$sample_size_imputed, FALSE) && identical(n$build_transformed, FALSE) &&
    identical(n$alleles_swapped_or_complemented, FALSE), "unsupported transformation or authorization")
  recipe <- jsonlite::fromJSON(recipe_path, simplifyVector = FALSE)
  # Compare parsed original recipe to receipt; never synthesize a JSON hash in
  # R whose escaping/number formatting could differ from canonical Rust bytes.
  demand(identical(recipe, n$frozen_recipe) && identical(recipe$status, "FROZEN") &&
    identical(recipe$schema_version, 1L) && identical(recipe$protocol_version, protocol_version) &&
    identical(recipe$source$construct_id, construct_id) && identical(recipe$source$build, build) &&
    identical(recipe$target_build, build) && identical(recipe$source$ancestry, ancestry),
    "source recipe/protocol/construct/build/ancestry differs")
  for (key in c("config", "raw", "metadata")) identity(n[[key]])
  demand(identical(n$config$sha256, recipe_sha256) && n$config$bytes == file.info(recipe_path)$size &&
    identical(n$raw$sha256, recipe$input_sha256$raw) &&
    identical(n$metadata$sha256, recipe$input_sha256$metadata) && n$metadata$bytes > 0,
    "receipt source identities differ from actual frozen recipe")
  exact(n$output, c("normalized.tsv", "row-qc.tsv", "sample-sizes.tsv"))
  for (key in names(n$output)) identity(n$output[[key]])
  out <- n$output[["normalized.tsv"]]
  demand(identical(out$sha256, digest::digest(file = normalized_path, algo = "sha256")) &&
    out$bytes == file.info(normalized_path)$size, "actual normalized payload differs from receipt")
  counts <- c(n$source_rows, n$retained_rows, n$excluded_rows, n$p_numeric_underflows)
  demand(is.numeric(counts) && length(counts) == 4L && all(is.finite(counts)) &&
    all(counts >= 0 & counts == floor(counts)) && n$source_rows == n$retained_rows + n$excluded_rows &&
    n$p_numeric_underflows <= n$retained_rows, "source row accounting differs")
  if (!is.null(recipe$decoding)) {
    exact(recipe$decoding, "recipe_sha256")
    exact(n$decoding, c("receipt", "recipe", "compressed", "evidence"))
    for (key in c("receipt", "recipe", "compressed")) identity(n$decoding[[key]])
    d <- n$decoding$evidence
    exact(d, c("schema_version", "operation", "status", "authorization", "scope", "config",
      "compressed", "metadata", "frozen_recipe", "decoded", "gzip_binary", "gzip_execution", "row_filtering_performed"))
    demand(digest_string(recipe$decoding$recipe_sha256) &&
      identical(n$decoding$recipe$sha256, recipe$decoding$recipe_sha256) &&
      identical(d$config, n$decoding$recipe) && identical(d$compressed, n$decoding$compressed) &&
      identical(d$decoded, n$raw) && identical(d$metadata, n$metadata) &&
      identical(d$status, "DECODED") && identical(d$schema_version, 1L) &&
      identical(d$operation, "GZIP_FULL_STREAM_DECODE") && identical(d$authorization, "NONE") &&
      identical(d$scope, "MECHANICAL_BYTES_NOT_RESOURCE_OR_SCIENTIFIC_APPROVAL") &&
      identical(d$row_filtering_performed, FALSE), "decoding provenance differs")
    for (key in c("resource_id", "construct_id", "accession", "release", "file_name")) {
      demand(identical(d$frozen_recipe$source[[key]], recipe$source[[key]]), "compressed source identity differs")
    }
    demand(identical(d$frozen_recipe$status, "FROZEN") &&
      identical(d$frozen_recipe$protocol_version, protocol_version), "decoding protocol differs")
    demand(identical(d$frozen_recipe$input_sha256$compressed, d$compressed$sha256) &&
      identical(d$frozen_recipe$input_sha256$metadata, n$metadata$sha256) &&
      identical(d$gzip_binary$sha256, d$frozen_recipe$gzip_binary_sha256) &&
      identical(d$gzip_execution$actual_child_executable_sha256, d$frozen_recipe$gzip_binary_sha256) &&
      identical(d$gzip_execution$source_bytes_fed, d$compressed) &&
      identical(d$gzip_execution$exit_code, 0L) && identical(d$gzip_execution$stderr_text, "") &&
      identical(d$frozen_recipe$codec, "GNU_GZIP_MULTI_MEMBER"), "complete decode execution differs")
  } else demand(is.null(n$decoding), "unexpected decoding evidence without frozen binding")
  identity(n$duplicate_identity_sort)
  demand(identical(n$duplicate_identity_sort$sha256, recipe$sort_binary_sha256) &&
    identical(n$duplicate_identity_sort_execution$exit_code, 0L), "duplicate identity verification failed")
  n
}

# 官方 TwoSampleMR 的冻结工具输入适配器；本文件不做 clumping、不签署 G0。
# 工具选择必须由已验收的独立上游完成，不能从 outcome 的可用行反选工具。
# Formatting only: preserve double values across a TSV parse without changing
# the input frame, scientific calculations, thresholds or missing-value rules.
write_lossless_tsv <- function(x, file, ...) {
  if (!is.data.frame(x)) stop("lossless TSV output requires a data frame", call. = FALSE)
  encoded <- x
  for (i in seq_along(encoded)) {
    value <- encoded[[i]]
    if (is.double(value) && !is.object(value)) {
      text <- sprintf("%.17g", value)
      text[is.na(value)] <- NA_character_
      encoded[[i]] <- text
    }
  }
  utils::write.table(encoded, file, sep = "\t", quote = FALSE,
    row.names = FALSE, na = "NA", ...)
}

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
  for (i in 1:3) write_lossless_tsv(result[[i]], outputs[i])
  jsonlite::write_json(result$audit, outputs[4L], pretty = TRUE, auto_unbox = TRUE, null = "null", na = "null", digits = NA)
}

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

AUTONOMICS_FROZEN_MR_SENSITIVITY
Rscript --vanilla "$SCRIPT" "$AUTONOMICS_INPUT0" "$AUTONOMICS_INPUT1" "$AUTONOMICS_INPUT2" "$AUTONOMICS_INPUT3" "$AUTONOMICS_INPUT4" "$AUTONOMICS_INPUT5" "$AUTONOMICS_INPUT6" "$AUTONOMICS_OUTPUT0" "$AUTONOMICS_OUTPUT1" "$AUTONOMICS_OUTPUT2" "$AUTONOMICS_OUTPUT3"
