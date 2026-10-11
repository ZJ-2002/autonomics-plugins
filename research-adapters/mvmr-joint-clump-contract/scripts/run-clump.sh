#!/bin/sh
set -eu
export LC_ALL=C
exec Rscript --vanilla - "$AUTONOMICS_INPUT0" "$AUTONOMICS_INPUT1" "$AUTONOMICS_INPUT2" "$AUTONOMICS_INPUT3" "$AUTONOMICS_INPUT4" /panels/plink_ref /work/joint-clump "$AUTONOMICS_OUTPUT0" "$AUTONOMICS_OUTPUT1" "$AUTONOMICS_OUTPUT2" "$AUTONOMICS_OUTPUT3" "$AUTONOMICS_OUTPUT4" <<'AUTONOMICS_FROZEN_JOINT_R'
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

# 仅按 exposure 选择工具：流式读取合格输入，再调用官方 PLINK2。
# 本层不接收 outcome，不生成科学签署；正式面板仍须引擎内容准入。
fail <- function(message) stop(message, call. = FALSE)
check <- function(ok, message) if (!isTRUE(ok)) fail(message)
sha <- function(path) digest::digest(file = path, algo = "sha256")
is_sha <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && grepl("^[0-9a-f]{64}$", x)
keys <- function(x, expected, label) check(is.list(x) && setequal(names(x), expected) &&
  !anyDuplicated(names(x)), paste(label, "schema differs"))
header <- c("snp", "chr", "pos", "beta", "se", "effect_allele", "other_allele", "eaf", "pval")
read_rows <- function(lines) {
  check(all(lengths(strsplit(lines, "\t", fixed = TRUE)) == length(header)), "malformed normalized SNP row")
  utils::read.delim(text = paste(c(paste(header, collapse = "\t"), lines), collapse = "\n"),
    colClasses = "character", check.names = FALSE, quote = "", comment.char = "", na.strings = c("NA", ""), fill = FALSE)
}

clump_frozen <- function(config_path, exposure_path, panel_path, normalization_path, normalization_recipe_path, panel_root, work, outputs,
                         source_receipt_validator = normalization_receipt, source_mode = "SINGLE_EXPOSURE") {
  for (package in c("jsonlite", "digest")) check(requireNamespace(package, quietly = TRUE), paste("package unavailable:", package))
  check(identical(Sys.getenv("LC_ALL"), "C"), "deterministic C locale required")
  c <- jsonlite::fromJSON(config_path, simplifyVector = FALSE)
  keys(c, c("status", "protocol_version", "exposure_id", "build", "ancestry", "instrument_class",
    "normalization_recipe_sha256", "policy", "panel_prefixes", "software_lock", "input_sha256"), "configuration")
  check(identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version), "frozen supported-protocol configuration required; templates are not runnable")
  check(is.character(c$exposure_id) && length(c$exposure_id) == 1L && grepl("^[A-Za-z0-9._:-]+$", c$exposure_id) &&
    c$build %in% c("GRCh37", "GRCh38") && is.character(c$ancestry) && length(c$ancestry) == 1L && nzchar(c$ancestry) &&
    identical(c$instrument_class, "COMPLEX_TRAIT") && is_sha(c$normalization_recipe_sha256), "source normalization/build/ancestry contract required")
  keys(c$policy, c("p_threshold", "clump_r2", "r2_comparison", "clump_kb", "tie_order", "ld_mode", "threads", "memory_mib"), "policy")
  tie <- unlist(c$policy$tie_order, use.names = FALSE)
  check(identical(c$policy$p_threshold, 5e-8) && identical(c$policy$clump_r2, 0.001) &&
    identical(c$policy$r2_comparison, "STRICT_LT") && identical(c$policy$clump_kb, 10000L) &&
    identical(tie, c("pval", "chr", "pos", "snp")) &&
    identical(c$policy$ld_mode, "HAPLOTYPE_MLE") && identical(c$policy$threads, 1L) &&
    identical(c$policy$memory_mib, 640L), "clumping policy differs from accepted implementation")
  keys(c$panel_prefixes, as.character(1:22), "panel chromosome prefixes")
  check(all(vapply(c$panel_prefixes, function(p) is.character(p) && length(p) == 1L &&
    grepl("^[A-Za-z0-9_-][A-Za-z0-9._-]*$", p) && !grepl("\\.\\.", p), logical(1))) &&
    !anyDuplicated(unlist(c$panel_prefixes)), "unsafe or duplicate panel prefix")
  keys(c$input_sha256, c("exposure", "panel_manifest", "normalization"), "input hashes")
  check(all(vapply(c$input_sha256, is_sha, logical(1))), "complete input hashes required")
  hashes <- list(config = sha(config_path), exposure = sha(exposure_path), panel_manifest = sha(panel_path),
    normalization = sha(normalization_path), normalization_recipe = sha(normalization_recipe_path))
  check(all(vapply(names(c$input_sha256), function(k) identical(hashes[[k]], c$input_sha256[[k]]), logical(1))), "input content identity mismatch")
  check(source_mode %in% c("SINGLE_EXPOSURE", "JOINT_TWO_EXPOSURE_UNION"), "unsupported clump source mode")
  normal <- source_receipt_validator(normalization_path, normalization_recipe_path, exposure_path,
    c$normalization_recipe_sha256, c$exposure_id, c$build, c$ancestry, c$protocol_version)
  keys(c$software_lock, c("R_version", "plink_version", "plink_binary_sha256"), "software lock")
  plink <- Sys.which("plink2")
  check(nzchar(plink) && identical(c$software_lock$R_version, as.character(getRversion())) &&
    is_sha(c$software_lock$plink_binary_sha256) && identical(sha(plink), c$software_lock$plink_binary_sha256), "software lock mismatch")
  version <- system2(plink, "--version", stdout = TRUE, stderr = TRUE)
  check(is.null(attr(version, "status")) && length(version) == 1L && identical(version, c$software_lock$plink_version), "PLINK version mismatch")
  panel <- jsonlite::fromJSON(panel_path, simplifyVector = FALSE)
  check(panel$schema_version %in% c(1L, 2L) && is.character(panel$digest) &&
    grepl("^sha256:[0-9a-f]{64}$", panel$digest) && identical(panel$metadata$genome_build, c$build) &&
    identical(panel$metadata$population, c$ancestry), "panel build/ancestry or digest differs")
  expected <- unlist(lapply(c$panel_prefixes, function(p) paste0(p, c(".bed", ".bim", ".fam"))), use.names = FALSE)
  paths <- vapply(panel$files, function(f) f$path, character(1))
  check(length(paths) == 66L && !anyDuplicated(paths) && setequal(paths, expected), "complete panel file universe differs")
  for (f in panel$files) {
    keys(f, c("path", "size", "sha256"), "panel file")
    path <- file.path(panel_root, f$path)
    check(!nzchar(Sys.readlink(path)) && file.exists(path) && !dir.exists(path) &&
      is.numeric(f$size) && f$size >= 0 && f$size == floor(f$size) && file.info(path)$size == f$size &&
      is.character(f$sha256) && grepl("^sha256:[0-9a-f]{64}$", f$sha256) &&
      identical(paste0("sha256:", sha(path)), f$sha256), paste("panel payload identity mismatch:", f$path))
  }
  check(dir.create(work, mode = "0700"), "fresh clumping workspace required")
  # 官方 clump 只作为诊断；临界值实测证明其快速路径与官方 LD 矩阵不一致。
  # 选择依据为官方 phased LD 双精度矩阵，再按冻结顺序进行严格比较。
  # 资源上限导致整节点拒绝，不截断候选集，不放宽科学阈值。
  matrix_variant_limit <- 4096L
  effective_r2 <- "0.0009999999999999998"
  check(as.numeric(effective_r2) < 0.001 && 0.001 - as.numeric(effective_r2) == 2^-62, "IEEE threshold adapter mismatch")
  calls <- list()
  invoke <- function(binary, args, label) {
    stdout <- file.path(work, paste0(label, ".stdout")); stderr <- file.path(work, paste0(label, ".stderr"))
    status <- system2(binary, args = vapply(args, shQuote, character(1)), stdout = stdout, stderr = stderr)
    check(file.info(stdout)$size <= 16*1024^2 && file.info(stderr)$size <= 16*1024^2, "execution log exceeded evidence bound")
    calls[[length(calls)+1L]] <<- list(executable = binary, argv = args, exit_code = status,
      stdout = paste(readLines(stdout, warn = FALSE), collapse = "\n"), stderr = paste(readLines(stderr, warn = FALSE), collapse = "\n"),
      stdout_sha256 = sha(stdout), stderr_sha256 = sha(stderr))
    check(identical(status, 0L), paste("upstream execution failed:", label))
  }
  con <- file(exposure_path, open = "r"); on.exit(close(con), add = TRUE)
  check(identical(readLines(con, n = 1L, warn = FALSE), paste(header, collapse = "\t")), "normalized exposure schema differs")
  id_path <- file.path(work, "all_ids.txt"); id_con <- file(id_path, open = "w"); on.exit(close(id_con), add = TRUE)
  qc_path <- file.path(work, "qc.tsv"); qc <- file(qc_path, open = "w"); on.exit(close(qc), add = TRUE)
  writeLines("snp\tphase\tstatus\treason", qc)
  candidates <- list(); total <- invalid <- nonsignificant <- 0L
  repeat {
    lines <- readLines(con, n = 10000L, warn = FALSE)
    if (!length(lines)) break
    d <- read_rows(lines)
    check(!anyNA(d$snp) && all(grepl("^[A-Za-z0-9._:+-]+$", d$snp)), "empty or malformed variant identity")
    writeLines(d$snp, id_con)
    num <- lapply(d[c("chr", "pos", "beta", "se", "eaf", "pval")], function(x) suppressWarnings(as.numeric(x)))
    valid <- is.finite(num$chr) & num$chr %in% 1:22 & is.finite(num$pos) & num$pos >= 1 & num$pos == floor(num$pos) &
      is.finite(num$beta) & is.finite(num$se) & num$se > 0 & is.finite(num$pval) & num$pval >= 0 & num$pval <= 1 &
      (is.na(d$eaf) | (is.finite(num$eaf) & num$eaf >= 0 & num$eaf <= 1)) &
      !is.na(d$effect_allele) & !is.na(d$other_allele) & d$effect_allele %in% c("A", "C", "G", "T") &
      d$other_allele %in% c("A", "C", "G", "T") & d$effect_allele != d$other_allele
    valid[is.na(valid)] <- FALSE
    significant <- valid & num$pval < 5e-8; significant[is.na(significant)] <- FALSE
    reason <- ifelse(!valid, "INVALID_NORMALIZED_EXPOSURE_ROW", ifelse(significant, "", "P_THRESHOLD_NOT_MET"))
    writeLines(paste(d$snp, "SOURCE_QC", ifelse(significant, "CANDIDATE", "EXCLUDED"), reason, sep = "\t"), qc)
    if (any(significant)) candidates[[length(candidates)+1L]] <- d[significant, , drop = FALSE]
    total <- total + nrow(d); invalid <- invalid + sum(!valid); nonsignificant <- nonsignificant + sum(valid & !significant)
  }
  close(id_con); on.exit(NULL, add = FALSE); close(qc); close(con)
  check(total == normal$retained_rows && invalid == 0L, "normalized source row count or validity differs from verified transformation")
  # 所有 ID 的重复检查用外排序；不会为几百万非候选行建立内存哈希表。
  sorted_ids <- file.path(work, "sorted_ids.txt")
  invoke("/usr/bin/sort", c("--buffer-size=64M", "--parallel=1", "--temporary-directory", work,
    "--output", sorted_ids, id_path), "identity_sort")
  sorted <- file(sorted_ids, open = "r"); last <- NULL
  repeat {
    ids <- readLines(sorted, n = 10000L, warn = FALSE)
    if (!length(ids)) break
    check(!anyDuplicated(ids) && (is.null(last) || last != ids[1L]), "duplicate variant identity in complete exposure source")
    last <- tail(ids, 1L)
  }
  close(sorted)
  if (length(candidates)) {
    candidate <- do.call(rbind, candidates)
    index <- order(as.numeric(candidate$pval), as.numeric(candidate$chr), as.numeric(candidate$pos), candidate$snp, method = "radix")
    candidate <- candidate[index, , drop = FALSE]
  } else candidate <- setNames(as.data.frame(rep(list(character()), 9L)), header)
  kept <- character(); excluded <- list(); ld_matrices <- list()
  for (chr in sort(unique(as.integer(candidate$chr)))) {
    sub <- candidate[as.integer(candidate$chr) == chr, , drop = FALSE]
    prefix <- file.path(panel_root, c$panel_prefixes[[as.character(chr)]])
    # 先核对 BIM 的 ID/坐标/等位基因；缺面板变异逐条登记，不降阈值补数。
    b <- file(paste0(prefix, ".bim"), "r"); found <- list()
    repeat {
      lines <- readLines(b, n = 10000L, warn = FALSE)
      if (!length(lines)) break
      d <- utils::read.table(text = paste(lines, collapse = "\n"), colClasses = "character", quote = "", comment.char = "", fill = FALSE)
      check(ncol(d) == 6L, "invalid panel BIM schema")
      match_rows <- which(d[[2L]] %in% sub$snp)
      if (length(match_rows)) found[[length(found)+1L]] <- d[match_rows, , drop = FALSE]
    }
    close(b)
    ref <- if (length(found)) do.call(rbind, found) else as.data.frame(rep(list(character()), 6L))
    check(!anyDuplicated(ref[[2L]]), "duplicate candidate identity in reference panel")
    lookup <- match(sub$snp, ref[[2L]])
    available <- !is.na(lookup)
    for (i in which(available)) {
      r <- ref[lookup[i], ]
      alleles <- c(sub$effect_allele[i], sub$other_allele[i])
      complement <- unname(c(A = "T", C = "G", G = "C", T = "A")[alleles])
      check(as.integer(r[[1L]]) == chr && as.numeric(r[[4L]]) == as.numeric(sub$pos[i]) &&
        (setequal(c(r[[5L]], r[[6L]]), alleles) || setequal(c(r[[5L]], r[[6L]]), complement)),
        "reference coordinates or alleles differ")
    }
    absent <- sub$snp[!available]
    if (length(absent)) excluded[[length(excluded)+1L]] <- data.frame(snp = absent, status = "EXCLUDED", reason = "REFERENCE_VARIANT_MISSING")
    sub <- sub[available, , drop = FALSE]
    if (!nrow(sub)) next
    check(nrow(sub) <= matrix_variant_limit, "official LD matrix exceeds qualified resource bound; no candidate truncation permitted")
    ids <- file.path(work, paste0("chr", chr, ".extract")); writeLines(sub$snp, ids)
    pfile <- file.path(work, paste0("chr", chr, ".sorted"))
    invoke(plink, c("--bfile", prefix, "--extract", ids, "--make-pgen", "--sort-vars", "ascii",
      "--threads", "1", "--memory", "640", "require", "--out", pfile), paste0("chr", chr, "_sort"))
    pvar <- utils::read.delim(paste0(pfile, ".pvar"), comment.char = "", check.names = FALSE, stringsAsFactors = FALSE)
    check(all(c("#CHROM", "POS", "ID") %in% names(pvar)) && setequal(pvar$ID, sub$snp) &&
      identical(order(as.integer(pvar[["#CHROM"]]), pvar$POS, pvar$ID, method = "radix"), seq_len(nrow(pvar))), "sorted reference variant order differs")
    association <- file.path(work, paste0("chr", chr, ".assoc"))
    utils::write.table(data.frame(SNP = sub$snp, P = sub$pval), association, sep = "\t", row.names = FALSE, quote = FALSE)
    result <- file.path(work, paste0("chr", chr, ".clump"))
    invoke(plink, c("--pfile", pfile, "--clump", association, "--clump-id-field", "SNP", "--clump-p-field", "P",
      "--clump-p1", "5e-8", "--clump-p2", "5e-8", "--clump-r2", effective_r2, "--clump-kb", "10000",
      "--threads", "1", "--memory", "640", "require", "--out", result), paste0("chr", chr, "_clump"))
    report <- utils::read.delim(paste0(result, ".clumps"), check.names = FALSE, stringsAsFactors = FALSE)
    check("ID" %in% names(report) && !anyDuplicated(report$ID) && all(report$ID %in% sub$snp), "PLINK clump report identity differs")
    ld_prefix <- file.path(work, paste0("chr", chr, ".ld"))
    invoke(plink, c("--pfile", pfile, "--r2-phased", "square", "bin", "--threads", "1",
      "--memory", "640", "require", "--out", ld_prefix), paste0("chr", chr, "_ld"))
    ld_path <- paste0(ld_prefix, ".phased.vcor2.bin")
    ld_ids <- readLines(paste0(ld_path, ".vars"), warn = FALSE)
    check(identical(ld_ids, as.character(pvar$ID)) && !anyDuplicated(ld_ids) &&
      file.info(ld_path)$size == 8 * length(ld_ids)^2, "official LD matrix identity or size differs")
    ld_connection <- file(ld_path, "rb")
    ld_values <- readBin(ld_connection, "double", n = length(ld_ids)^2, size = 8L, endian = .Platform$endian)
    close(ld_connection)
    ld <- matrix(ld_values, nrow = length(ld_ids), byrow = TRUE)
    check(length(ld_values) == length(ld_ids)^2 && all(is.finite(ld_values)) &&
      all(ld_values >= 0 & ld_values <= 1 + 1e-12) &&
      all(abs(diag(ld) - 1) <= 1e-12) && identical(ld, t(ld)),
      "official LD is undefined or invalid; no independence may be inferred")
    positions <- as.numeric(sub$pos)
    indices <- match(sub$snp, ld_ids)
    blocked <- rep(FALSE, nrow(sub)); chosen <- character()
    for (i in seq_len(nrow(sub))) {
      if (blocked[i]) next
      chosen <- c(chosen, sub$snp[i])
      nearby <- abs(positions - positions[i]) <= 10000000
      blocked[nearby & ld[indices[i], indices] >= 0.001] <- TRUE
      blocked[i] <- TRUE
    }
    calls[[length(calls)]]$ld_matrix_sha256 <- sha(ld_path)
    calls[[length(calls)]]$ld_order_sha256 <- sha(paste0(ld_path, ".vars"))
    calls[[length(calls)]]$selected_ids <- chosen
    calls[[length(calls)]]$diagnostic_clump_ids <- as.character(report$ID)
    calls[[length(calls)]]$diagnostic_agrees <- setequal(chosen, report$ID)
    ld_matrices[[length(ld_matrices)+1L]] <- list(chromosome = chr, variant_count = length(ld_ids),
      matrix_path = basename(ld_path), matrix_sha256 = sha(ld_path), matrix_bytes = file.info(ld_path)$size,
      order_path = basename(paste0(ld_path, ".vars")), order_sha256 = sha(paste0(ld_path, ".vars")),
      double_bytes = 8L, endian = .Platform$endian)
    kept <- c(kept, chosen)
    removed <- setdiff(sub$snp, chosen)
    if (length(removed)) excluded[[length(excluded)+1L]] <- data.frame(snp = removed, status = "EXCLUDED", reason = "LD_CLUMPED")
    rm(ld, ld_values); gc(verbose = FALSE)
  }
  selected <- candidate[candidate$snp %in% kept, , drop = FALSE]
  check(!anyDuplicated(kept) && setequal(selected$snp, kept), "selected instrument universe differs")
  utils::write.table(selected, outputs[1L], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  # 完整原始 QC 保留；候选的最后状态是独立追加账本，不覆盖原始行。
  final <- data.frame(snp = candidate$snp, phase = rep("CLUMP_FINAL", nrow(candidate)),
    status = ifelse(candidate$snp %in% kept, "RETAINED", "EXCLUDED"), reason = rep("", nrow(candidate)))
  if (length(excluded)) {
    e <- do.call(rbind, excluded); check(setequal(e$snp, candidate$snp[!candidate$snp %in% kept]) && !anyDuplicated(e$snp), "candidate exclusion universe differs")
    final$reason[match(e$snp, final$snp)] <- e$reason
  }
  check(file.copy(qc_path, outputs[3L], overwrite = FALSE), "cannot publish complete variant QC")
  utils::write.table(final, outputs[3L], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA", col.names = FALSE, append = TRUE)
  # 原始官方矩阵和顺序表也是发布产物，供检查点恢复后独立重推。
  ld_manifest <- file.path(work, "ld-evidence.json")
  jsonlite::write_json(list(schema_version = 1L, input_sha256 = hashes,
    policy = c$policy, selection_algorithm = "FROZEN_GREEDY_ORDER_OFFICIAL_PHASED_LD_MATRIX_STRICT_LT",
    matrices = ld_matrices), ld_manifest, auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  ld_files <- c("ld-evidence.json", unlist(lapply(ld_matrices, function(m) c(m$matrix_path, m$order_path)), use.names = FALSE))
  invoke("/bin/tar", c("--format=ustar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
    "--numeric-owner", "-cf", outputs[5L], "-C", work, "--", ld_files), "ld_evidence_archive")
  audit <- list(scope = if (source_mode == "SINGLE_EXPOSURE") "OFFICIAL_EXPOSURE_ONLY_CLUMPING_NOT_NORMALIZATION_OR_G0" else
      "OFFICIAL_JOINT_EXPOSURE_UNION_CLUMPING_NOT_SOURCE_OR_G0", exposure_id = c$exposure_id,
    input_sha256 = hashes, normalization_evidence_sha256 = hashes$normalization,
    normalization_record = normal,
    panel_digest = panel$digest, software_lock = c$software_lock, policy = c$policy,
    diagnostic_cli_r2_cutoff = effective_r2,
    selection_algorithm = "FROZEN_GREEDY_ORDER_OFFICIAL_PHASED_LD_MATRIX_STRICT_LT",
    matrix_variant_limit = matrix_variant_limit,
    source_rows = total, invalid_rows = invalid, nonsignificant_rows = nonsignificant, candidate_count = nrow(candidate),
    selected_count = nrow(selected), selected_ids = selected$snp, selected_exposure_sha256 = sha(outputs[1L]),
    ld_evidence_archive_sha256 = sha(outputs[5L]),
    qc_ledger_sha256 = sha(outputs[3L]), execution_calls = calls, authorization = "NONE")
  jsonlite::write_json(audit, outputs[4L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  selection <- list(type = "EXPOSURE_ONLY_CLUMP_COMPLETION", exposure_id = c$exposure_id,
    selected_exposure_sha256 = sha(outputs[1L]), source_exposure_sha256 = hashes$exposure, selected_ids = selected$snp,
    p_threshold = 5e-8, clump_r2 = 0.001, clump_kb = 10000L, tie_order = tie, ancestry = c$ancestry, build = c$build,
    panel_manifest_sha256 = hashes$panel_manifest, normalization_evidence_sha256 = hashes$normalization,
    selection_execution_evidence_sha256 = sha(outputs[4L]), outcome_used_for_selection = FALSE)
  if (source_mode == "JOINT_TWO_EXPOSURE_UNION") {
    selection$type <- "MVMR_EXPOSURE_UNION_CLUMP_COMPLETION"
    selection$exposure_ids <- normal$exposure_ids
    selection$source_exposure_sha256_by_id <- normal$source_exposure_sha256_by_id
    selection$source_recipe_sha256_by_id <- normal$source_recipe_sha256_by_id
    selection$union_rule <- normal$union_rule
    selection$anchor_rule <- normal$anchor_rule
  }
  jsonlite::write_json(selection, outputs[2L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
}

main <- function(args) {
  check(length(args) == 12L, "usage: clump.R config exposure panel-manifest normalization-receipt normalization-recipe panel-root work selected selection qc audit ld-evidence-tar")
  outputs <- args[8:12]
  check(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) { t <- Sys.readlink(p); !is.na(t) && nzchar(t) }, logical(1))), "output exists or duplicates another output")
  clump_frozen(args[1L], args[2L], args[3L], args[4L], args[5L], args[6L], args[7L], outputs)
}
if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})

# Typed union completion, distinct from a single GWAS normalization receipt.
joint_union_receipt <- function(path, recipe_path, union_path, recipe_sha256, analysis_id, build, ancestry, protocol_version) {
  need <- function(ok, message) if (!isTRUE(ok)) stop(paste("joint union provenance:", message), call. = FALSE)
  need(frozen_protocol_supported(protocol_version), "unsupported parent protocol")
  for (p in c(path, recipe_path)) need(file.exists(p) && !dir.exists(p) && file.info(p)$size <= 16*1024^2,
    "receipt/recipe absent or oversized")
  c <- joint_union_config(recipe_path)
  need(identical(ju_sha(recipe_path), recipe_sha256) && identical(c$analysis_id, analysis_id) &&
    identical(c$protocol_version, protocol_version) && identical(c$build, build) && identical(c$ancestry, ancestry), "actual frozen union recipe/protocol/analysis/build/ancestry differs")
  n <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  ju_keys(n, c("schema_version", "type", "authorization", "analysis_id", "exposure_ids", "build", "ancestry",
    "input_sha256", "source_exposure_sha256_by_id", "source_recipe_sha256_by_id", "frozen_recipe",
    "source_normalization_records", "source_rows", "retained_rows", "selected_ids", "anchor_exposure_ids",
    "selected_exposure_sha256", "union_rule", "anchor_rule", "outcome_used_for_selection"), "union receipt")
  ids <- unlist(c$exposure_ids, use.names = FALSE)
  need(identical(n$schema_version, 1L) && identical(n$type, "MVMR_TWO_EXPOSURE_UNION_COMPLETION") &&
    identical(n$authorization, "NONE") && identical(n$analysis_id, analysis_id) &&
    identical(unlist(n$exposure_ids, use.names = FALSE), ids) && identical(n$build, build) &&
    identical(n$ancestry, ancestry) && identical(n$frozen_recipe, c) &&
    identical(n$outcome_used_for_selection, FALSE) && identical(n$selected_exposure_sha256, ju_sha(union_path)),
    "union payload/recipe identity or authorization differs")
  ju_keys(n$input_sha256, c("config", "exposure0", "exposure1", "normalization0", "recipe0", "normalization1", "recipe1"), "union receipt inputs")
  need(all(vapply(n$input_sha256, ju_hash, logical(1))) && identical(n$input_sha256$config, recipe_sha256), "complete union source hashes required")
  need(all(vapply(names(c$input_sha256), function(k) identical(c$input_sha256[[k]], n$input_sha256[[k]]), logical(1))), "union source inputs differ from frozen recipe")
  ju_keys(n$source_exposure_sha256_by_id, ids, "union source exposure identities")
  ju_keys(n$source_recipe_sha256_by_id, ids, "union source recipe identities")
  need(identical(n$source_recipe_sha256_by_id, c$source_recipe_sha256_by_id) &&
    identical(n$source_exposure_sha256_by_id[[ids[1L]]], n$input_sha256$exposure0) &&
    identical(n$source_exposure_sha256_by_id[[ids[2L]]], n$input_sha256$exposure1) &&
    identical(n$source_recipe_sha256_by_id[[ids[1L]]], n$input_sha256$recipe0) &&
    identical(n$source_recipe_sha256_by_id[[ids[2L]]], n$input_sha256$recipe1), "union source exposure/recipe binding differs")
  count <- n$retained_rows; snps <- unlist(n$selected_ids, use.names = FALSE); anchors <- unlist(n$anchor_exposure_ids, use.names = FALSE)
  need(is.numeric(count) && length(count) == 1L && is.finite(count) && count >= 0 && count == floor(count) &&
    length(snps) == count && !anyDuplicated(snps) && length(anchors) == count && all(anchors %in% ids), "union row/anchor universe differs")
  need(identical(n$union_rule, c$policy$union_rule) && identical(n$anchor_rule, c$policy$anchor_rule), "union/anchor policy differs")
  n
}

joint_clump_main <- function(args) {
  ju_check(length(args) == 12L, "joint clump requires config union panel union-receipt union-recipe panel-root work five outputs")
  out <- args[8:12]
  ju_check(!anyDuplicated(out) && !any(file.exists(out)) &&
    !any(vapply(out, function(p) { a <- Sys.readlink(p); !is.na(a) && nzchar(a) }, logical(1))), "joint clump output exists or duplicates")
  clump_frozen(args[1L], args[2L], args[3L], args[4L], args[5L], args[6L], args[7L], out,
    source_receipt_validator = joint_union_receipt, source_mode = "JOINT_TWO_EXPOSURE_UNION")
}

}, envir = .GlobalEnv)
tryCatch(joint_clump_main(commandArgs(TRUE)), error = function(e) {message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)})
AUTONOMICS_FROZEN_JOINT_R
