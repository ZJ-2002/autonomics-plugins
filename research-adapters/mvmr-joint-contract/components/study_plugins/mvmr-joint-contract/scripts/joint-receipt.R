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
