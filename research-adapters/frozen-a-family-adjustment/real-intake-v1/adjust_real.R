options(digits = 17)
invisible(Sys.umask("0077"))

require_true <- function(value, message) {
  if (!isTRUE(value)) stop(message, call. = FALSE)
}

checksum <- function(path) {
  result <- system2("sha256sum", c("--", shQuote(path)), stdout = TRUE, stderr = TRUE)
  require_true(is.null(attr(result, "status")) && length(result) == 1L && grepl("^[0-9a-f]{64} ", result), "SHA256 unavailable")
  substr(result, 1L, 64L)
}

arguments <- commandArgs(trailingOnly = TRUE)
require_true(length(arguments) == 4L, "Expected real intake vectors, assembly receipt, frozen R methods and new output directory")
vectors_path <- normalizePath(arguments[1], mustWork = TRUE)
receipt_path <- normalizePath(arguments[2], mustWork = TRUE)
methods_path <- normalizePath(arguments[3], mustWork = TRUE)
output <- arguments[4]
require_true(!file.exists(output) && !dir.exists(output), "New isolated technical real intake output directory required")
require_true(as.character(getRversion()) == "4.6.1" && as.character(packageVersion("stats")) == "4.6.1", "Frozen official R/stats 4.6.1 required")
require_true(checksum(methods_path) == "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd", "Frozen R method source differs")
input_hashes <- c(vectors = checksum(vectors_path), receipt = checksum(receipt_path), methods = checksum(methods_path))
receipt <- jsonlite::read_json(receipt_path, simplifyVector = FALSE)
scope <- "A_REAL_INPUT_CANDIDATE_V1_QUALIFICATION_PENDING"
require_true(identical(receipt$schema, "A_REAL_INPUT_ASSEMBLY_V1") && identical(receipt$scope, scope) &&
  identical(receipt$primary_results_published, FALSE) && identical(receipt$eligibility_receipts_accepted, FALSE) &&
  identical(receipt$scientific_authorization_granted, FALSE) && identical(receipt$g0_granted, FALSE) &&
  identical(receipt$output_sha256[["real-vectors.tsv"]], unname(input_hashes[["vectors"]])), "Hash-bound non-authorizing real intake receipt required")
counts <- c(A_PRIMARY_EDGES = 88L, A_EXPANDED_EDGES = 188L, A_PRIMARY_PATHS = 36L, A_EXPANDED_PATHS = 252L)
require_true(identical(as.integer(unlist(receipt$family_counts[names(counts)])), unname(counts)), "Frozen family denominators differ")
vectors <- read.delim(vectors_path, colClasses = "character", na.strings = character(), check.names = FALSE)
require_true(identical(names(vectors), c("vector_id", "analysis_id", "family_id", "method", "p_primary", "p_for_adjustment")) && nrow(vectors) == 840L, "Complete six-vector real intake table required")
definition <- grep("^adjust_full <- function\\(", readLines(methods_path, warn = FALSE), value = TRUE)
require_true(length(definition) == 1L, "Exactly one frozen official adjustment definition required")
definition <- paste0(definition, "\n")
temporary <- tempfile(tmpdir = tempdir())
writeBin(charToRaw(definition), temporary)
require_true(checksum(temporary) == "2d110232f5f1c3097d763686df1ecec5212e3ca18b4b226ac8f5562c388813fd", "Frozen adjustment function identity differs")
unlink(temporary)
official <- new.env(parent = asNamespace("stats"))
eval(parse(text = definition), envir = official)
expected_vectors <- unlist(lapply(names(counts), function(family) paste(family, if (grepl("EDGES$", family)) c("BH", "BY") else "BY", sep = "/")))
require_true(setequal(unique(vectors$vector_id), expected_vectors), "Only six frozen correction vectors allowed")
vectors$q_primary <- NA_character_
objects <- list()
for (key in expected_vectors) {
  positions <- which(vectors$vector_id == key)
  selected <- vectors[positions, , drop = FALSE]
  family <- unique(selected$family_id)
  method <- unique(selected$method)
  require_true(length(family) == 1L && length(method) == 1L && identical(key, paste(family, method, sep = "/")) &&
    identical(selected$analysis_id, unlist(receipt$family_ids[[family]], use.names = FALSE)) &&
    length(positions) == counts[[family]], "Complete ordered frozen members required")
  raw <- suppressWarnings(as.numeric(selected$p_primary))
  require_true(all(selected$p_primary == "NA" | (is.finite(raw) & raw >= 0 & raw <= 1)), "Finite probabilities or literal NA required")
  require_true(all(is.na(raw)), "Current frozen pending decisions require missing primary values")
  adjustment <- ifelse(is.na(raw), 1, raw)
  require_true(all(suppressWarnings(as.numeric(selected$p_for_adjustment)) == adjustment), "Only missing P values receive adjustment-one placeholders")
  adjusted <- official$adjust_full(raw, method)
  require_true(length(adjusted) == length(raw) && all(is.finite(adjusted)) && all(adjusted >= 0 & adjusted <= 1), "Official real intake adjustment must be complete")
  vectors$q_primary[positions] <- sprintf("%.17g", adjusted)
  objects[[key]] <- list(analysis_id = selected$analysis_id, p_primary = raw,
    p_for_adjustment = adjustment, q_primary = adjusted, method = method, n_total = length(raw))
}
require_true(identical(input_hashes, c(vectors = checksum(vectors_path), receipt = checksum(receipt_path), methods = checksum(methods_path))), "Real intake inputs changed during adjustment")
require_true(dir.create(output, mode = "0700"), "Exclusive technical real intake output directory required")
write.table(vectors, file.path(output, "real-adjusted.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
saveRDS(list(vectors = objects, frozen_definition = definition, input_sha256 = input_hashes,
  scope = scope, R_version = "4.6.1", stats_version = "4.6.1"), file.path(output, "real-adjustment.RDS"))
roundtrip <- readRDS(file.path(output, "real-adjustment.RDS"))
require_true(identical(roundtrip$vectors, objects), "All six official RDS vectors must round-trip exactly")
jsonlite::write_json(list(schema = "A_REAL_INPUT_ADJUSTMENT_V1", scope = scope,
  input_sha256 = as.list(input_hashes), official_function = "stats::p.adjust", vectors = 6L, rows = 840L, RDS_readback_vectors = 6L, RDS_readback_values = 840L,
  output_sha256 = list(real_tsv = checksum(file.path(output, "real-adjusted.tsv")),
    real_RDS = checksum(file.path(output, "real-adjustment.RDS"))),
  primary_results_published = FALSE, scientific_family_complete = FALSE,
  independent_replication_claimed = FALSE, scientific_authorization_granted = FALSE, g0_granted = FALSE),
  file.path(output, "real-adjustment.json"), auto_unbox = TRUE, pretty = TRUE)
Sys.chmod(list.files(output, full.names = TRUE), mode = "0600")
