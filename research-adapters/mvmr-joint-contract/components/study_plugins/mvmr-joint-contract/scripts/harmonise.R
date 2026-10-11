# Official allele harmonization of already jointly clumped tools. Does not select
# from outcome availability, infer exposure covariance, or grant direct-effect/G0.
jh_scan <- function(path, selected, receipt, work, label) {
  con <- file(path, "r"); on.exit(close(con), add = TRUE)
  ju_check(identical(readLines(con, n = 1L, warn = FALSE), paste(ju_header, collapse = "\t")), "normalized joint input schema differs")
  all_ids <- file.path(work, paste0(label, "-ids.txt")); id_out <- file(all_ids, "w")
  on.exit(close(id_out), add = TRUE); count <- 0L; found <- list()
  repeat {
    lines <- readLines(con, n = 10000L, warn = FALSE)
    if (!length(lines)) break
    ju_check(all(lengths(strsplit(lines, "\t", fixed = TRUE)) == 9L), "malformed normalized joint input row")
    d <- utils::read.delim(text = paste(c(paste(ju_header, collapse = "\t"), lines), collapse = "\n"),
      colClasses = "character", quote = "", comment.char = "", check.names = FALSE, na.strings = c("NA", ""), fill = FALSE)
    ju_check(!anyNA(d$snp) && all(grepl("^[A-Za-z0-9._:+-]+$", d$snp)), "invalid joint source variant identity")
    writeLines(d$snp, id_out); count <- count + nrow(d)
    for (col in c("chr", "pos", "beta", "se", "eaf", "pval")) {
      old <- d[[col]]; d[[col]] <- suppressWarnings(as.numeric(old))
      ju_check(!any(!is.na(old) & !is.finite(d[[col]])), "nonnumeric normalized source")
    }
    ju_check(all(is.finite(d$chr) & d$chr %in% 1:22 & is.finite(d$pos) & d$pos >= 1 & d$pos == floor(d$pos) &
      is.finite(d$beta) & is.finite(d$se) & d$se > 0 &
      (is.na(d$eaf) | (d$eaf >= 0 & d$eaf <= 1)) & (is.na(d$pval) | (d$pval >= 0 & d$pval <= 1))) &&
      all(!is.na(d$effect_allele) & !is.na(d$other_allele) & d$effect_allele %in% c("A", "C", "G", "T") &
        d$other_allele %in% c("A", "C", "G", "T") & d$effect_allele != d$other_allele), "invalid normalized joint source row")
    take <- d[d$snp %in% selected, , drop = FALSE]
    if (nrow(take)) found[[length(found) + 1L]] <- take
  }
  close(con); close(id_out); on.exit(NULL, add = FALSE)
  ju_check(count == receipt$retained_rows, "joint source row accounting differs")
  sorted <- file.path(work, paste0(label, "-sorted-ids.txt"))
  status <- system2("/usr/bin/sort", vapply(c("--buffer-size=64M", "--parallel=1", "--temporary-directory", work,
    "--output", sorted, all_ids), shQuote, character(1)), stdout = FALSE, stderr = FALSE)
  ju_check(identical(status, 0L), "joint source identity sorting failed")
  s <- file(sorted, "r"); last <- NULL
  repeat {
    b <- readLines(s, n = 10000L, warn = FALSE)
    if (!length(b)) break
    ju_check(!anyDuplicated(b) && (is.null(last) || last != b[1L]), "duplicate joint source identity including unselected rows")
    last <- tail(b, 1L)
  }
  close(s)
  if (length(found)) return(do.call(rbind, found))
  empty <- setNames(as.data.frame(rep(list(character()), 9L)), ju_header)
  for (col in c("chr", "pos", "beta", "se", "eaf", "pval")) empty[[col]] <- numeric()
  empty
}

joint_harmonise_main <- function(args) {
  ju_check(length(args) == 17L, "joint harmonise requires twelve inputs, workspace and four outputs")
  for (pkg in c("TwoSampleMR", "jsonlite", "digest")) ju_check(requireNamespace(pkg, quietly = TRUE), paste("package missing:", pkg))
  ju_check(identical(Sys.getenv("LC_ALL"), "C"), "deterministic C locale required")
  inputs <- args[1:12]; work <- args[13L]; outputs <- args[14:17]
  ju_check(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) { a <- Sys.readlink(p); !is.na(a) && nzchar(a) }, logical(1))), "joint harmonization output exists or duplicates")
  c <- jsonlite::fromJSON(inputs[1L], simplifyVector = FALSE)
  ju_keys(c, c("schema_version", "status", "protocol_version", "analysis_id", "exposure_ids", "outcome_id", "build", "ancestry",
    "instrument_class", "policy", "source_recipe_sha256_by_id", "software_lock", "input_sha256"), "joint harmonization configuration")
  ids <- unlist(c$exposure_ids, use.names = FALSE)
  ju_check(identical(c$schema_version, 1L) && identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version) &&
    is.character(c$analysis_id) && length(c$analysis_id) == 1L && grepl("^[A-Za-z0-9._:-]+$", c$analysis_id) &&
    ju_ids(ids) && is.character(c$outcome_id) && length(c$outcome_id) == 1L && grepl("^[A-Za-z0-9._:-]+$", c$outcome_id) &&
    !(c$outcome_id %in% ids) && c$build %in% c("GRCh37", "GRCh38") && is.character(c$ancestry) && length(c$ancestry) == 1L &&
    nzchar(c$ancestry) && identical(c$instrument_class, "COMPLEX_TRAIT"), "explicit frozen joint analysis/construct contract required")
  ju_keys(c$policy, c("harmonise_action", "palindrome_ambiguous_eaf", "boundaries_inclusive", "palindrome_max_eaf_difference",
    "palindrome_missing_eaf", "proxy_primary"), "joint allele policy")
  ju_check(identical(c$policy$harmonise_action, 2L) && identical(unlist(c$policy$palindrome_ambiguous_eaf, use.names = FALSE), c(.42, .58)) &&
    identical(c$policy$boundaries_inclusive, TRUE) && identical(c$policy$palindrome_max_eaf_difference, .1) &&
    identical(c$policy$palindrome_missing_eaf, "EXCLUDE") && identical(c$policy$proxy_primary, FALSE), "joint allele policy differs from v4.2.1")
  ju_keys(c$software_lock, c("R_version", "TwoSampleMR_version", "sort_binary_sha256"), "joint software lock")
  ju_check(identical(c$software_lock$R_version, as.character(getRversion())) &&
    identical(c$software_lock$TwoSampleMR_version, as.character(utils::packageVersion("TwoSampleMR"))) &&
    identical(c$software_lock$sort_binary_sha256, ju_sha("/usr/bin/sort")), "joint software lock differs")
  labels <- c("config", "selected_union", "exposure0", "exposure1", "outcome", "selection", "normalization0", "recipe0", "normalization1", "recipe1", "outcome_normalization", "outcome_recipe")
  hashes <- as.list(setNames(vapply(inputs, ju_sha, character(1)), labels))
  ju_keys(c$input_sha256, labels[-1L], "joint input hashes")
  ju_check(all(vapply(names(c$input_sha256), function(k) identical(c$input_sha256[[k]], hashes[[k]]), logical(1))), "joint input content identity mismatch")
  constructs <- c(ids, c$outcome_id); ju_keys(c$source_recipe_sha256_by_id, constructs, "joint source recipe identities")
  ju_check(all(vapply(c$source_recipe_sha256_by_id, ju_hash, logical(1))), "actual joint source recipe hashes required")
  normal <- lapply(1:3, function(i) normalization_receipt(inputs[c(7L, 9L, 11L)[i]], inputs[c(8L, 10L, 12L)[i]],
    inputs[c(3L, 4L, 5L)[i]], c$source_recipe_sha256_by_id[[constructs[i]]], constructs[i], c$build, c$ancestry, c$protocol_version))
  selected <- utils::read.delim(inputs[2L], colClasses = "character", quote = "", comment.char = "", check.names = FALSE, na.strings = c("NA", ""))
  ju_check(identical(names(selected), ju_header) && !anyNA(selected$snp) && !anyDuplicated(selected$snp), "joint selected tool schema/universe differs")
  for (col in c("chr", "pos", "beta", "se", "eaf", "pval")) selected[[col]] <- suppressWarnings(as.numeric(selected[[col]]))
  ju_check(nrow(selected) <= 4096L, "joint model exceeds qualified total IV bound; no truncation")
  ju_check(all(is.finite(selected$pval) & selected$pval >= 0 & selected$pval < 5e-8 & is.finite(selected$beta) &
    is.finite(selected$se) & selected$se > 0) && identical(order(selected$pval, selected$chr, selected$pos, selected$snp, method = "radix"), seq_len(nrow(selected))),
    "joint selected tools are invalid or not in frozen order")
  selection <- jsonlite::fromJSON(inputs[6L], simplifyVector = FALSE)
  ju_keys(selection, c("type", "exposure_id", "selected_exposure_sha256", "source_exposure_sha256", "selected_ids", "p_threshold",
    "clump_r2", "clump_kb", "tie_order", "ancestry", "build", "panel_manifest_sha256", "normalization_evidence_sha256",
    "selection_execution_evidence_sha256", "outcome_used_for_selection", "exposure_ids", "source_exposure_sha256_by_id",
    "source_recipe_sha256_by_id", "union_rule", "anchor_rule"), "joint clump selection")
  ju_check(identical(selection$type, "MVMR_EXPOSURE_UNION_CLUMP_COMPLETION") && identical(selection$exposure_id, c$analysis_id) &&
    identical(unlist(selection$exposure_ids, use.names = FALSE), ids) && identical(selection$selected_exposure_sha256, hashes$selected_union) &&
    identical(as.character(unlist(selection$selected_ids, use.names = FALSE)), selected$snp) && identical(selection$outcome_used_for_selection, FALSE) &&
    identical(selection$p_threshold, 5e-8) && identical(selection$clump_r2, .001) && identical(selection$clump_kb, 10000L) &&
    identical(unlist(selection$tie_order, use.names = FALSE), c("pval", "chr", "pos", "snp")) &&
    identical(selection$build, c$build) && identical(selection$ancestry, c$ancestry) &&
    identical(selection$union_rule, "ANY_EXPOSURE_P_STRICT_LT") && identical(selection$anchor_rule, "MIN_EXPOSURE_P_THEN_REGISTERED_EXPOSURE_ORDER"),
    "joint exposure-only selection contract differs")
  for (key in c("source_exposure_sha256", "panel_manifest_sha256", "normalization_evidence_sha256", "selection_execution_evidence_sha256"))
    ju_check(ju_hash(selection[[key]]), "joint clumping evidence hash absent")
  ju_keys(selection$source_exposure_sha256_by_id, ids, "selected joint source exposure identities")
  ju_keys(selection$source_recipe_sha256_by_id, ids, "selected joint source recipe identities")
  for (i in 1:2) ju_check(identical(selection$source_exposure_sha256_by_id[[ids[i]]], hashes[[c("exposure0", "exposure1")[i]]]) &&
    identical(selection$source_recipe_sha256_by_id[[ids[i]]], c$source_recipe_sha256_by_id[[ids[i]]]), "selected joint tools came from a different exposure source")
  ju_check(dir.create(work, mode = "0700"), "fresh joint harmonization workspace required")
  data <- lapply(1:3, function(i) jh_scan(inputs[c(3L, 4L, 5L)[i]], selected$snp, normal[[i]], work, paste0("source", i)))
  n <- nrow(selected); reasons <- matrix("", nrow = n, ncol = 3L); aligned <- vector("list", 3L)
  base <- function(d, side, id) {
    x <- d[, c("snp", "beta", "se", "effect_allele", "other_allele", "eaf", "pval"), drop = FALSE]
    names(x) <- c("SNP", paste0(c("beta", "se", "effect_allele", "other_allele", "eaf", "pval"), ".", side))
    x[[paste0("id.", side)]] <- id; x[[side]] <- id; x
  }
  pal <- (selected$effect_allele == "A" & selected$other_allele == "T") | (selected$effect_allele == "T" & selected$other_allele == "A") |
    (selected$effect_allele == "C" & selected$other_allele == "G") | (selected$effect_allele == "G" & selected$other_allele == "C")
  pal[is.na(pal)] <- FALSE; warnings <- list(); official_calls <- list()
  for (i in 1:3) {
    other <- data[[i]][match(selected$snp, data[[i]]$snp), , drop = FALSE]
    present <- !is.na(other$snp)
    reasons[!present, i] <- if (i == 3L) "DIRECT_OUTCOME_VARIANT_MISSING" else "DIRECT_EXPOSURE_VARIANT_MISSING"
    reasons[present & (selected$chr != other$chr | selected$pos != other$pos), i] <- "VARIANT_COORDINATES_DIFFER"
    eligible <- reasons[, i] == ""; a <- data.frame(beta = rep(NA_real_, n), se = rep(NA_real_, n), eaf = rep(NA_real_, n), sign = rep(NA_integer_, n))
    if (any(eligible)) {
      raw <- withCallingHandlers(TwoSampleMR::harmonise_data(base(selected[eligible, , drop = FALSE], "exposure", c$analysis_id),
        base(other[eligible, , drop = FALSE], "outcome", constructs[i]), action = 2L), warning = function(w) {
          warnings[[length(warnings)+1L]] <<- list(construct_id = constructs[i], message = conditionMessage(w)); invokeRestart("muffleWarning")
        })
      ju_check(!anyDuplicated(raw$SNP) && setequal(raw$SNP, selected$snp[eligible]), "official joint harmonization changed tool universe")
      raw <- raw[match(selected$snp[eligible], raw$SNP), , drop = FALSE]
      a$beta[eligible] <- raw$beta.outcome; a$se[eligible] <- raw$se.outcome; a$eaf[eligible] <- raw$eaf.outcome
      reasons[which(eligible)[!raw$mr_keep], i] <- "OFFICIAL_HARMONIZATION_REJECTED"
      official_calls[[length(official_calls)+1L]] <- list(function_name = "TwoSampleMR::harmonise_data", construct_id = constructs[i], action = 2L, submitted_ids = as.list(selected$snp[eligible]))
    }
    missing <- pal & present & (is.na(selected$eaf) | is.na(other$eaf))
    ambiguous <- pal & present & ((selected$eaf >= .42 & selected$eaf <= .58) | (other$eaf >= .42 & other$eaf <= .58)); ambiguous[is.na(ambiguous)] <- FALSE
    reasons[eligible & missing, i] <- "PALINDROME_EAF_MISSING"
    reasons[eligible & !missing & ambiguous, i] <- "PALINDROME_AMBIGUOUS_EAF_INCLUSIVE"
    mismatch <- pal & eligible & reasons[, i] == "" & is.finite(abs(selected$eaf - a$eaf)) & abs(selected$eaf - a$eaf) > .1 + 8*.Machine$double.eps
    reasons[mismatch, i] <- "PALINDROME_ALIGNED_EAF_DIFFERENCE"
    valid <- reasons[, i] == ""
    comp <- c(A = "T", C = "G", G = "C", T = "A")
    direct <- other$effect_allele == selected$effect_allele & other$other_allele == selected$other_allele
    complement <- unname(comp[other$effect_allele]) == selected$effect_allele & unname(comp[other$other_allele]) == selected$other_allele
    a$sign[valid & !pal] <- ifelse((direct | complement)[valid & !pal], 1L, -1L)
    # Palindromic signs use actual aligned frequencies. Inclusive ambiguous
    # frequencies are already excluded, so raw versus 1-raw cannot coincide.
    a$sign[valid & pal] <- ifelse(abs(other$eaf[valid & pal] - a$eaf[valid & pal]) <= 8*.Machine$double.eps, 1L, -1L)
    ju_check(all(is.finite(a$beta[valid]) & is.finite(a$se[valid]) & a$se[valid] > 0 &
      a$beta[valid] == a$sign[valid] * other$beta[valid] & a$se[valid] == other$se[valid]), "official joint alignment or signed source transformation differs")
    aligned[[i]] <- a
  }
  keep <- if (n) apply(reasons == "", 1L, all) else logical()
  table <- data.frame(SNP = selected$snp[keep], beta_Y = aligned[[3L]]$beta[keep], se_Y = aligned[[3L]]$se[keep],
    beta_X0 = aligned[[1L]]$beta[keep], se_X0 = aligned[[1L]]$se[keep], beta_X1 = aligned[[2L]]$beta[keep], se_X1 = aligned[[2L]]$se[keep])
  ledger <- data.frame(snp = selected$snp, chr = selected$chr, pos = selected$pos, anchor_effect_allele = selected$effect_allele,
    anchor_other_allele = selected$other_allele, status = ifelse(keep, "RETAINED", "EXCLUDED"),
    reason_exposure0 = reasons[, 1L], reason_exposure1 = reasons[, 2L], reason_outcome = reasons[, 3L],
    sign_exposure0 = aligned[[1L]]$sign, sign_exposure1 = aligned[[2L]]$sign, sign_outcome = aligned[[3L]]$sign)
  ju_check(identical(hashes, as.list(setNames(vapply(inputs, ju_sha, character(1)), labels))), "joint input changed during harmonization")
  utils::write.table(table, outputs[1L], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  utils::write.table(ledger, outputs[3L], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  identity <- list(type = "FROZEN_JOINT_INPUT_IDENTITY_NOT_SOURCE_QUALIFICATION", analysis_id = c$analysis_id,
    exposure_ids = as.list(ids), outcome_id = c$outcome_id, snp_ids = as.list(table$SNP), harmonized_sha256 = ju_sha(outputs[1L]), outcome_used_for_selection = FALSE)
  jsonlite::write_json(identity, outputs[2L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  audit <- list(scope = "OFFICIAL_JOINT_HARMONIZATION_NOT_SELECTION_OR_SCIENTIFIC_APPROVAL", analysis_id = c$analysis_id,
    exposure_ids = ids, outcome_id = c$outcome_id, input_sha256 = hashes, selection = selection,
    source_normalization_records = normal, software_lock = c$software_lock, policy = c$policy,
    selected_ids = as.list(selected$snp), retained_ids = as.list(table$SNP), ledger_sha256 = ju_sha(outputs[3L]),
    harmonized_sha256 = ju_sha(outputs[1L]), official_calls = official_calls, warnings = warnings,
    outcome_used_for_selection = FALSE, region_or_proxy_filtering_performed = FALSE,
    source_to_joint_exposure_signs_available_in_ledger = TRUE,
    covariance_orientation_not_inferred_or_transformed = TRUE, scientific_approval_verified = FALSE, formal_authorized = FALSE)
  jsonlite::write_json(audit, outputs[4L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
}
