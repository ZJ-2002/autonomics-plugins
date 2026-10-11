#!/bin/sh
set -eu
export LC_ALL=C
exec Rscript --vanilla - "$AUTONOMICS_INPUT0" "$AUTONOMICS_INPUT1" "$AUTONOMICS_INPUT2" "$AUTONOMICS_INPUT3" "$AUTONOMICS_INPUT4" "$AUTONOMICS_INPUT5" "$AUTONOMICS_INPUT6" "$AUTONOMICS_INPUT7" "$AUTONOMICS_INPUT8" "$AUTONOMICS_INPUT9" "$AUTONOMICS_INPUT10" "$AUTONOMICS_INPUT11" /work/joint-harmonise "$AUTONOMICS_OUTPUT0" "$AUTONOMICS_OUTPUT1" "$AUTONOMICS_OUTPUT2" "$AUTONOMICS_OUTPUT3" <<'AUTONOMICS_FROZEN_JOINT_R'
local({
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

# An explicitly preregistered two-exposure union; no outcome input or LD estimate.
# Min-P anchoring is a candidate adapter policy, not an inferred plan/G0 decision.
ju_fail <- function(message) stop(message, call. = FALSE)
ju_check <- function(ok, message) if (!isTRUE(ok)) ju_fail(message)
ju_sha <- function(path) digest::digest(file = path, algo = "sha256")
ju_keys <- function(x, expected, label) ju_check(is.list(x) && setequal(names(x), expected) &&
  !anyDuplicated(names(x)), paste(label, "schema differs"))
ju_hash <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && grepl("^[0-9a-f]{64}$", x)
ju_ids <- function(x) is.character(x) && length(x) == 2L && !anyNA(x) &&
  all(grepl("^[A-Za-z0-9._:-]+$", x)) && !anyDuplicated(x)
ju_header <- c("snp", "chr", "pos", "beta", "se", "effect_allele", "other_allele", "eaf", "pval")

joint_union_config <- function(path) {
  c <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  ju_keys(c, c("schema_version", "status", "protocol_version", "analysis_id", "exposure_ids",
    "build", "ancestry", "instrument_class", "policy", "source_recipe_sha256_by_id",
    "software_lock", "input_sha256"), "union configuration")
  ju_check(identical(c$schema_version, 1L) && identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version),
    "explicit frozen supported-protocol union configuration required; no implicit MVMR selection policy")
  ids <- unlist(c$exposure_ids, use.names = FALSE)
  ju_check(ju_ids(ids) && is.character(c$analysis_id) && length(c$analysis_id) == 1L &&
    grepl("^[A-Za-z0-9._:-]+$", c$analysis_id) && c$build %in% c("GRCh37", "GRCh38") &&
    is.character(c$ancestry) && length(c$ancestry) == 1L && nzchar(c$ancestry) &&
    identical(c$instrument_class, "COMPLEX_TRAIT"), "joint construct/build/ancestry contract required")
  ju_keys(c$policy, c("p_threshold", "union_rule", "anchor_rule", "tie_order"), "union policy")
  ju_check(identical(c$policy$p_threshold, 5e-8) &&
    identical(c$policy$union_rule, "ANY_EXPOSURE_P_STRICT_LT") &&
    identical(c$policy$anchor_rule, "MIN_EXPOSURE_P_THEN_REGISTERED_EXPOSURE_ORDER") &&
    identical(unlist(c$policy$tie_order, use.names = FALSE), c("pval", "chr", "pos", "snp")),
    "supported explicit union/anchor policy required; no outcome-based selection")
  ju_keys(c$source_recipe_sha256_by_id, ids, "source recipe identities")
  ju_check(all(vapply(c$source_recipe_sha256_by_id, ju_hash, logical(1))), "actual source recipe hashes required")
  ju_keys(c$input_sha256, c("exposure0", "exposure1", "normalization0", "normalization1"), "union input hashes")
  ju_check(all(vapply(c$input_sha256, ju_hash, logical(1))), "complete actual input hashes required")
  ju_keys(c$software_lock, c("R_version", "sort_binary_sha256"), "union software lock")
  ju_check(identical(c$software_lock$R_version, as.character(getRversion())) &&
    identical(c$software_lock$sort_binary_sha256, ju_sha("/usr/bin/sort")), "union software lock mismatch")
  c
}

joint_union_frozen <- function(config, x0, x1, n0, r0, n1, r1, work, outputs) {
  for (pkg in c("jsonlite", "digest")) ju_check(requireNamespace(pkg, quietly = TRUE), paste("package missing:", pkg))
  ju_check(identical(Sys.getenv("LC_ALL"), "C"), "deterministic C locale required")
  c <- joint_union_config(config); ids <- unlist(c$exposure_ids, use.names = FALSE)
  inputs <- c(config, x0, x1, n0, r0, n1, r1)
  before <- vapply(inputs, ju_sha, character(1))
  actual <- list(exposure0 = before[2L], exposure1 = before[3L], normalization0 = before[4L], normalization1 = before[6L])
  ju_check(all(vapply(names(actual), function(k) identical(c$input_sha256[[k]], unname(actual[[k]])), logical(1))), "union input content identity mismatch")
  receipts <- list(normalization_receipt(n0, r0, x0, c$source_recipe_sha256_by_id[[ids[1L]]], ids[1L], c$build, c$ancestry, c$protocol_version),
    normalization_receipt(n1, r1, x1, c$source_recipe_sha256_by_id[[ids[2L]]], ids[2L], c$build, c$ancestry, c$protocol_version))
  ju_check(dir.create(work, mode = "0700"), "fresh union workspace required")
  candidates <- list(); counts <- integer(2L); executions <- list()
  qc <- file(file.path(work, "union-qc.tsv"), "w"); on.exit(close(qc), add = TRUE)
  writeLines("exposure_id\tsnp\tphase\tstatus\treason", qc)
  for (side in 1:2) {
    con <- file(c(x0, x1)[side], "r")
    id_path <- file.path(work, paste0("exposure", side, "-ids.txt")); ids_out <- file(id_path, "w")
    local_count <- 0L; candidate_count <- 0L
    ju_check(identical(readLines(con, n = 1L, warn = FALSE), paste(ju_header, collapse = "\t")), "normalized exposure schema differs")
    repeat {
      lines <- readLines(con, n = 10000L, warn = FALSE)
      if (!length(lines)) break
      ju_check(all(lengths(strsplit(lines, "\t", fixed = TRUE)) == 9L), "malformed normalized exposure row")
      d <- utils::read.delim(text = paste(c(paste(ju_header, collapse = "\t"), lines), collapse = "\n"),
        colClasses = "character", quote = "", comment.char = "", check.names = FALSE, na.strings = c("NA", ""), fill = FALSE)
      ju_check(!anyNA(d$snp) && all(grepl("^[A-Za-z0-9._:+-]+$", d$snp)), "invalid source variant identity")
      writeLines(d$snp, ids_out)
      num <- lapply(d[c("chr", "pos", "beta", "se", "eaf", "pval")], function(x) suppressWarnings(as.numeric(x)))
      valid <- is.finite(num$chr) & num$chr %in% 1:22 & is.finite(num$pos) & num$pos >= 1 & num$pos == floor(num$pos) &
        is.finite(num$beta) & is.finite(num$se) & num$se > 0 & is.finite(num$pval) & num$pval >= 0 & num$pval <= 1 &
        (is.na(d$eaf) | (is.finite(num$eaf) & num$eaf >= 0 & num$eaf <= 1)) &
        !is.na(d$effect_allele) & !is.na(d$other_allele) & d$effect_allele %in% c("A", "C", "G", "T") &
        d$other_allele %in% c("A", "C", "G", "T") & d$effect_allele != d$other_allele
      ju_check(all(!is.na(valid) & valid), "invalid row in normalized joint exposure source")
      significant <- num$pval < 5e-8
      writeLines(paste(ids[side], d$snp, "SOURCE_P", ifelse(significant, "CANDIDATE", "EXCLUDED"),
        ifelse(significant, "", "P_THRESHOLD_NOT_MET"), sep = "\t"), qc)
      if (any(significant)) {
        take <- d[significant, , drop = FALSE]; take$anchor_exposure_index <- side
        candidates[[length(candidates) + 1L]] <- take
        candidate_count <- candidate_count + nrow(take)
        ju_check(candidate_count <= 22L * 4096L, "union candidate source exceeds qualification bound; no truncation permitted")
      }
      local_count <- local_count + nrow(d)
    }
    close(con); close(ids_out)
    ju_check(local_count == receipts[[side]]$retained_rows, "actual normalized source row accounting differs")
    sorted <- file.path(work, paste0("exposure", side, "-sorted-ids.txt"))
    args <- c("--buffer-size=64M", "--parallel=1", "--temporary-directory", work, "--output", sorted, id_path)
    log <- file.path(work, paste0("exposure", side, "-sort.log"))
    status <- system2("/usr/bin/sort", vapply(args, shQuote, character(1)), stdout = log, stderr = log)
    ju_check(identical(status, 0L), "complete source identity sorting failed")
    s <- file(sorted, "r"); last <- NULL
    repeat {
      batch <- readLines(s, n = 10000L, warn = FALSE)
      if (!length(batch)) break
      ju_check(!anyDuplicated(batch) && (is.null(last) || last != batch[1L]), "duplicate identity in complete source, including nonsignificant rows")
      last <- tail(batch, 1L)
    }
    close(s); counts[side] <- local_count
    executions[[side]] <- list(executable = "/usr/bin/sort", argv = args, exit_code = status, log_sha256 = ju_sha(log))
  }
  if (length(candidates)) {
    all <- do.call(rbind, candidates)
    duplicate <- which(duplicated(all$snp)); first <- match(all$snp[duplicate], all$snp)
    pair <- function(a, b) ifelse(a < b, paste0(a, b), paste0(b, a))
    comp <- c(A = "T", C = "G", G = "C", T = "A")
    left <- pair(all$effect_allele[first], all$other_allele[first])
    right <- pair(all$effect_allele[duplicate], all$other_allele[duplicate])
    complement <- pair(unname(comp[all$effect_allele[duplicate]]), unname(comp[all$other_allele[duplicate]]))
    ju_check(all(all$anchor_exposure_index[first] != all$anchor_exposure_index[duplicate]) &&
      all(all$chr[first] == all$chr[duplicate] & all$pos[first] == all$pos[duplicate] &
        (left == right | left == complement)), "cross-exposure candidate coordinates or alleles differ")
    all <- all[order(as.numeric(all$pval), as.numeric(all$chr), as.numeric(all$pos), all$snp,
      all$anchor_exposure_index, method = "radix"), , drop = FALSE]
    union <- all[!duplicated(all$snp), , drop = FALSE]
    anchors <- union$anchor_exposure_index
    union <- union[, ju_header, drop = FALSE]
  } else {
    union <- setNames(as.data.frame(rep(list(character()), 9L)), ju_header); anchors <- integer()
  }
  ju_check(identical(before, vapply(inputs, ju_sha, character(1))), "union input changed during selection")
  close(qc); on.exit(NULL, add = FALSE)
  utils::write.table(union, outputs[1L], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  ju_check(file.copy(file.path(work, "union-qc.tsv"), outputs[3L], overwrite = FALSE), "union QC output publication failed")
  record <- list(schema_version = 1L, type = "MVMR_TWO_EXPOSURE_UNION_COMPLETION", authorization = "NONE",
    analysis_id = c$analysis_id, exposure_ids = ids, build = c$build, ancestry = c$ancestry,
    input_sha256 = as.list(setNames(before, c("config", "exposure0", "exposure1", "normalization0", "recipe0", "normalization1", "recipe1"))),
    source_exposure_sha256_by_id = as.list(setNames(c(ju_sha(x0), ju_sha(x1)), ids)),
    source_recipe_sha256_by_id = c$source_recipe_sha256_by_id,
    frozen_recipe = c, source_normalization_records = receipts, source_rows = counts,
    retained_rows = nrow(union), selected_ids = as.list(union$snp),
    anchor_exposure_ids = as.list(ids[anchors]), selected_exposure_sha256 = ju_sha(outputs[1L]),
    union_rule = c$policy$union_rule, anchor_rule = c$policy$anchor_rule, outcome_used_for_selection = FALSE)
  audit <- list(scope = "EXPOSURE_ONLY_TWO_SOURCE_UNION_NO_LD_OR_G0", record = record,
    full_qc_sha256 = ju_sha(outputs[3L]), sort_executions = executions, scientific_approval_verified = FALSE, formal_authorized = FALSE)
  jsonlite::write_json(audit, outputs[4L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  jsonlite::write_json(record, outputs[2L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
}

joint_union_main <- function(args) {
  ju_check(length(args) == 12L, "usage: union.R config x0 x1 norm0 recipe0 norm1 recipe1 work union receipt qc audit")
  out <- args[9:12]
  ju_check(!anyDuplicated(out) && !any(file.exists(out)) &&
    !any(vapply(out, function(p) { a <- Sys.readlink(p); !is.na(a) && nzchar(a) }, logical(1))), "joint output exists or duplicates")
  joint_union_frozen(args[1L], args[2L], args[3L], args[4L], args[5L], args[6L], args[7L], args[8L], out)
}
if (sys.nframe() == 0L) tryCatch(joint_union_main(commandArgs(TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})

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

}, envir = .GlobalEnv)
tryCatch(joint_harmonise_main(commandArgs(TRUE)), error = function(e) {message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)})
AUTONOMICS_FROZEN_JOINT_R
