inputs <- vapply(0:3, function(port) Sys.getenv(paste0("AUTONOMICS_INPUT", port)), character(1))
outputs <- vapply(0:5, function(port) Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)), character(1))
if (any(!nzchar(outputs)) || anyDuplicated(outputs)) stop("Six distinct declared output ports are required")
for (output in outputs) dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
writeLines("Frozen MRlap preflight started", outputs[[4]])
audit <- c(status = "STARTED", scientific_G0_granted = "false")
warnings_seen <- character()
write_audit <- function() {
  write.table(data.frame(key = names(audit), value = unname(audit)), outputs[[5]],
              sep = "\t", quote = FALSE, row.names = FALSE)
}
file_hash <- function(filename) {
  if (!file.exists(filename) || dir.exists(filename)) stop("Input identity cannot be established")
  value <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  if ((!is.null(attr(value, "status")) && attr(value, "status") != 0L) ||
      length(value) != 1L || !grepl("^[a-f0-9]{64} ", value)) stop("Content hashing failed")
  substr(value, 1L, 64L)
}
integer_value <- function(value, name) {
  if (length(value) != 1L || !grepl("^[1-9][0-9]*$", value)) stop(paste(name, "must be a canonical positive integer"))
  parsed <- suppressWarnings(as.numeric(value))
  if (!is.finite(parsed) || parsed > .Machine$integer.max) stop(paste(name, "exceeds the integer bound"))
  as.integer(parsed)
}
numeric_scalar <- function(value) {
  if (is.null(value) || length(value) == 0L) return(NA_real_)
  if (length(value) != 1L || !is.numeric(value) || (!is.na(value) && !is.finite(value))) {
    stop("Unexpected official numeric result shape or infinity")
  }
  as.numeric(value)
}
execute <- function() {
  if (any(!nzchar(inputs)) || anyDuplicated(inputs)) stop("Four distinct declared input files are required")
  contract <- read.delim(inputs[[4]], colClasses = "character", na.strings = NULL,
                         check.names = FALSE, quote = "", comment.char = "", fill = FALSE)
  required <- c("scope", "result_exposure", "edge_id", "exposure_sha256", "outcome_sha256", "iv_sha256",
                "panel_manifest_sha256", "seed", "requested_iv_n", "n_exposure", "n_outcome",
                "do_pruning", "mr_threshold", "mr_reverse", "mr_pruning_dist", "mr_pruning_ld", "effect_scale")
  if (!identical(names(contract), c("key", "value")) || nrow(contract) != length(required) ||
      anyNA(contract) || anyDuplicated(contract$key) || !setequal(contract$key, required) ||
      any(!nzchar(contract$value))) stop("Frozen contract keys are incomplete, duplicate or unknown")
  parameters <- setNames(as.list(contract$value), contract$key)
  if (parameters$scope != "TECHNICAL_ONLY_NOT_G0" || parameters$result_exposure != "LEGACY_SEEN" ||
      !parameters$edge_id %in% c("XM", "XY", "MY") || parameters$do_pruning != "false" ||
      parameters$effect_scale != "MRLAP_Z_OVER_SQRT_N_NOT_CONVENTIONAL_BETA") stop("Scope, edge or method-scale contract is invalid")
  seed <- integer_value(parameters$seed, "seed")
  requested_n <- integer_value(parameters$requested_iv_n, "requested_iv_n")
  exposure_n <- integer_value(parameters$n_exposure, "n_exposure")
  outcome_n <- integer_value(parameters$n_outcome, "n_outcome")
  if (!identical(parameters$mr_threshold, "5e-8") || !identical(parameters$mr_reverse, "0.001") ||
      !identical(parameters$mr_pruning_dist, "500") || !identical(parameters$mr_pruning_ld, "0")) {
    stop("Method parameters differ from the frozen canonical MRlap protocol")
  }
  expected_hashes <- c(parameters$exposure_sha256, parameters$outcome_sha256, parameters$iv_sha256,
                       parameters$panel_manifest_sha256)
  if (any(!grepl("^[a-f0-9]{64}$", expected_hashes))) stop("Expected content hash is malformed")
  observed_hashes <- vapply(inputs[1:3], file_hash, character(1))
  if (!identical(unname(observed_hashes), unname(expected_hashes[1:3]))) stop("GWAS or requested-IV content identity mismatch")
  audit <<- c(audit, edge_id = parameters$edge_id, result_exposure = parameters$result_exposure,
              effect_scale = parameters$effect_scale, seed = parameters$seed,
              input0_sha256 = observed_hashes[[1]], input1_sha256 = observed_hashes[[2]],
              input2_sha256 = observed_hashes[[3]], input3_sha256 = file_hash(inputs[[4]]))
  variants <- readLines(inputs[[3]], warn = FALSE)
  if (length(variants) != requested_n || anyDuplicated(variants) ||
      any(!grepl("^rs[0-9]+$", variants))) stop("Requested IVs must be unique rsIDs with the frozen count and no blank lines")
  panel <- "/panels/ldsc_assets"
  manifest_path <- file.path(panel, "manifest.json")
  if (file_hash(manifest_path) != expected_hashes[[4]]) stop("LD-panel manifest identity mismatch")
  panel_manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
  expected_files <- c("w_hm3.noMHC.snplist",
                      unlist(lapply(1:22, function(chromosome) paste0("eur_w_ld_chr/", chromosome, c(".l2.ldscore.gz", ".l2.M_5_50")))))
  paths <- vapply(panel_manifest$files, function(record) record$path, character(1))
  if (length(paths) != 49L || anyDuplicated(paths) || !all(expected_files %in% paths) ||
      any(grepl("(^/|(^|/)\\.\\.(/|$))", paths))) stop("LD-panel file set is incomplete or unexpected")
  for (record in panel_manifest$files) {
    if (file_hash(file.path(panel, record$path)) != sub("^sha256:", "", record$sha256)) stop("LD-panel file content identity mismatch")
  }
  audit <<- c(audit, panel_manifest_sha256 = expected_hashes[[4]], panel_files_verified = "49", required_LD_files = "45")
  expected_versions <- c(MRlap = "0.0.3.3", GenomicSEM = "0.0.5", TwoSampleMR = "0.7.11")
  for (package in names(expected_versions)) {
    if (as.character(utils::packageVersion(package)) != expected_versions[[package]]) stop("Official method package version mismatch")
  }
  data.table::setDTthreads(2L)
  for (index in 1:2) {
    schema <- names(data.table::fread(inputs[[index]], nrows = 0L, showProgress = FALSE))
    if (anyDuplicated(schema) || !all(c("rsid", "chr", "pos", "a1", "a2", "beta", "se", "N") %in% schema)) {
      stop("MRlap GWAS schema is incomplete or ambiguous")
    }
    sample_sizes <- data.table::fread(inputs[[index]], select = "N", showProgress = FALSE)$N
    expected_n <- if (index == 1L) exposure_n else outcome_n
    if (!length(sample_sizes) || anyNA(sample_sizes) || any(!is.finite(sample_sizes)) || any(sample_sizes != expected_n)) {
      stop("GWAS sample sizes differ from the frozen constant N")
    }
  }
  connection <- file(outputs[[4]], open = "at")
  sink(connection, split = TRUE)
  on.exit({sink(); close(connection)}, add = TRUE)
  cat("Input and panel identities verified; no input deduplication or IVW fallback\n")
  print(expected_versions)
  print(sessionInfo())
  RNGkind("Mersenne-Twister", "Inversion", "Rejection")
  set.seed(seed)
  result <- MRlap::MRlap(exposure = inputs[[1]], outcome = inputs[[2]],
                         ld = file.path(panel, "eur_w_ld_chr"), hm3 = file.path(panel, "w_hm3.noMHC.snplist"),
                         do_pruning = FALSE, user_SNPsToKeep = variants,
                         MR_threshold = 5e-8, MR_reverse = .001, MR_pruning_dist = 500,
                         MR_pruning_LD = 0, verbose = FALSE)
  correction <- result$MRcorrection
  linkage <- result$LDSC
  retained <- correction$IVs
  if (anyDuplicated(retained) || !all(retained %in% variants) || length(retained) != correction$m_IVs) {
    stop("Official retained IV identity or count is inconsistent")
  }
  summary <- data.frame(edge = parameters$edge_id,
    m_IVs = numeric_scalar(correction$m_IVs),
    h2_exp = numeric_scalar(linkage$h2_exp), h2_exp_se = numeric_scalar(linkage$h2_exp_se),
    h2_out = numeric_scalar(linkage$h2_out), h2_out_se = numeric_scalar(linkage$h2_out_se),
    rg = numeric_scalar(linkage$rg), rg_se = numeric_scalar(linkage$rg_se),
    gcov = numeric_scalar(linkage$gcov), gcov_se = numeric_scalar(linkage$gcov_se),
    int_crosstrait = numeric_scalar(linkage$int_crosstrait), int_crosstrait_se = numeric_scalar(linkage$int_crosstrait_se),
    mr_naive = numeric_scalar(correction$observed_effect), mr_naive_se = numeric_scalar(correction$observed_effect_se),
    mr_corrected = numeric_scalar(correction$corrected_effect), mr_corrected_se = numeric_scalar(correction$corrected_effect_se),
    mr_corrected_p = numeric_scalar(correction$corrected_effect_p), egger_intercept_p = numeric_scalar(correction$egger_intercept_p))
  write.table(summary, outputs[[1]], sep = "\t", quote = FALSE, row.names = FALSE)
  saveRDS(result, outputs[[2]])
  writeLines(capture.output(print(result)), outputs[[3]])
  selected <- variants %in% retained
  retention <- data.frame(rsid = variants, requested = TRUE, retained = selected,
                         status = ifelse(selected, "RETAINED", "NOT_RETAINED_BY_OFFICIAL_PIPELINE_NOT_DIAGNOSED"))
  write.table(retention, outputs[[6]], sep = "\t", quote = FALSE, row.names = FALSE)
  audit[["status"]] <<- if (is.na(summary$mr_corrected_p)) "NOT_ESTIMABLE" else "ESTIMABLE"
  audit <<- c(audit, requested_iv_n = as.character(length(variants)), retained_iv_n = as.character(length(retained)),
              warning_count = as.character(length(warnings_seen)))
  for (port in c(0L, 1L, 2L, 5L)) audit[[paste0("output", port, "_sha256")]] <<- file_hash(outputs[[port + 1L]])
}
tryCatch(withCallingHandlers(execute(), warning = function(condition) {
  warnings_seen <<- c(warnings_seen, conditionMessage(condition))
  cat("WARNING:", conditionMessage(condition), "\n", file = outputs[[4]], append = TRUE)
}), error = function(condition) {
  unlink(outputs[c(1L, 2L, 3L, 6L)])
  audit[["status"]] <<- "BLOCKED"
  audit[["error"]] <<- gsub("[\t\r\n]", " ", conditionMessage(condition))
  cat("BLOCKED:", conditionMessage(condition), "\n", file = outputs[[4]], append = TRUE)
  write_audit()
  quit(status = 1L)
})
write_audit()
