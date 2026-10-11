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
