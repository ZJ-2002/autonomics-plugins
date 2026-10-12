# Official singscore adapter. Inputs are already admitted gene-level expression;
# this script does not normalize counts, map probes, choose signatures or approve G0.
fail <- function(message) stop(message, call. = FALSE)
require_contract <- function(ok, message) if (!isTRUE(ok)) fail(message)

score_frozen <- function(config_path, matrix_path, signature_path) {
  for (package in c("jsonlite", "digest", "singscore"))
    require_contract(requireNamespace(package, quietly = TRUE), paste("package unavailable:", package))
  config <- jsonlite::fromJSON(config_path, simplifyVector = TRUE)
  require_contract(identical(config$status, "FROZEN"), "frozen configuration required; templates are not runnable")
  require_contract(identical(config$module, "B-SPEC") && identical(config$family, "B_SPEC_ASSOC"), "wrong scoring contract")
  require_contract(length(config$dataset_id) == 1L && is.character(config$dataset_id) &&
    grepl("^[A-Za-z0-9._-]+$", config$dataset_id), "frozen dataset identity required")
  require_contract(identical(config$primary_score, "B_SPEC_singscore"), "unregistered score method")
  require_contract(identical(config$rank_axis, "WITHIN_SAMPLE_ACROSS_GENES") &&
    identical(config$rankGenes_tiesMethod, "average") && is.null(config$rankGenes_stableGenes) &&
    identical(config$simpleScore_knownDirection, TRUE) && identical(config$simpleScore_centerScore, TRUE) &&
    identical(config$score_column, "TotalScore"), "score parameters differ from frozen protocol")
  require_contract(identical(config$coverage_min, 0.8) && identical(config$members_min, 5L) &&
    identical(config$signed_arm_coverage_min, 0.8), "coverage contract differs")
  require_contract(identical(config$input_species, "HUMAN") && identical(config$input_level, "GENE") &&
    config$input_scale %in% c("TPM", "GENE_LENGTH_ADJUSTED", "QUALIFIED_MICROARRAY"), "unqualified expression scale or units")
  require_contract(!is.null(config$normalization_evidence_sha256) &&
    grepl("^[0-9a-f]{64}$", config$normalization_evidence_sha256), "normalization provenance required")
  require_contract(!is.null(config$software_lock$R_version) && !is.null(config$software_lock$singscore_version) &&
    identical(config$software_lock$R_version, as.character(getRversion())) &&
    identical(config$software_lock$singscore_version, as.character(utils::packageVersion("singscore"))), "software lock mismatch")
  require_contract(length(config$seed) == 1L && is.numeric(config$seed) && is.finite(config$seed) &&
    config$seed == as.integer(config$seed) && config$seed >= 0, "frozen integer seed required")
  set.seed(config$seed)
  hashes <- list(config = digest::digest(file = config_path, algo = "sha256"),
                 matrix = digest::digest(file = matrix_path, algo = "sha256"),
                 signatures = digest::digest(file = signature_path, algo = "sha256"))
  require_contract(identical(hashes$matrix, config$input_sha256$matrix) &&
    identical(hashes$signatures, config$input_sha256$signatures), "input content identity mismatch")
  expression <- utils::read.delim(matrix_path, check.names = FALSE, stringsAsFactors = FALSE,
    na.strings = c("NA", ""), quote = "", comment.char = "", colClasses = "character")
  require_contract(ncol(expression) > 1L && identical(names(expression)[1L], "gene_id"), "gene matrix schema required")
  require_contract(!anyNA(expression$gene_id) && !anyDuplicated(expression$gene_id) &&
    !anyDuplicated(names(expression)) && all(nzchar(names(expression))), "empty or duplicate matrix identity")
  require_contract(identical(expression$gene_id, config$common_gene_universe) &&
    identical(names(expression)[-1L], config$sample_ids), "frozen background or sample universe differs")
  matrix <- matrix(suppressWarnings(as.numeric(as.matrix(expression[-1L]))), nrow = nrow(expression),
    dimnames = list(expression$gene_id, names(expression)[-1L]))
  # Incomplete expression backgrounds need a separately qualified QC/missingness
  # adapter. Reject here rather than silently changing ranks or filling zeroes.
  require_contract(nrow(matrix) > 5L && all(is.finite(matrix)), "expression background is incomplete or nonnumeric")
  signatures <- utils::read.delim(signature_path, check.names = FALSE, stringsAsFactors = FALSE,
    quote = "", comment.char = "", colClasses = "character")
  require_contract(identical(names(signatures), c("program_id", "gene_id", "direction")) &&
    nrow(signatures) > 0L && !anyNA(signatures) && all(nzchar(as.matrix(signatures))), "signature schema required")
  require_contract(setequal(unique(signatures$program_id), c("NP06", "NP07", "NP08", "NP09")) &&
    all(signatures$direction %in% c("UP", "DOWN")) &&
    !anyDuplicated(signatures[c("program_id", "gene_id")]), "signature identity or direction differs")
  ranks <- singscore::rankGenes(matrix, tiesMethod = "average", stableGenes = NULL)
  scores <- list(); coverage <- list()
  for (id in c("NP06", "NP07", "NP08", "NP09")) {
    program <- signatures[signatures$program_id == id, , drop = FALSE]
    up <- program$gene_id[program$direction == "UP"]
    down <- program$gene_id[program$direction == "DOWN"]
    require_contract(length(up) > 0L, "up arm required by this accepted adapter; down-only signatures need qualification")
    measured <- program$gene_id %in% rownames(matrix)
    total <- sum(measured); fraction <- total / nrow(program)
    arm_fraction <- function(genes) if (length(genes)) sum(genes %in% rownames(matrix)) / length(genes) else NA_real_
    up_fraction <- arm_fraction(up); down_fraction <- arm_fraction(down)
    eligible <- total >= 5L && fraction >= 0.8 && up_fraction >= 0.8 &&
      (!length(down) || down_fraction >= 0.8)
    missing <- program$gene_id[!measured]
    coverage[[id]] <- data.frame(dataset_id = config$dataset_id, program_id = id, original_members = nrow(program),
      measured_members = total, coverage = fraction, up_coverage = up_fraction, down_coverage = down_fraction,
      missing_members = paste(missing, collapse = ";"),
      status = if (eligible) "ESTIMATED" else "NOT_ESTIMABLE",
      reason = if (eligible) "" else "SIGNATURE_COVERAGE_OR_MEMBERS_INSUFFICIENT")
    value <- rep(NA_real_, ncol(matrix))
    if (eligible) {
      # Explicitly retain the full signature above; the measured subset is
      # justified only by the predeclared coverage contract, never by results.
      scored <- if (length(down)) {
        singscore::simpleScore(ranks, upSet = intersect(up, rownames(matrix)),
          downSet = intersect(down, rownames(matrix)), knownDirection = TRUE, centerScore = TRUE)
      } else {
        # S4 dispatch distinguishes a missing argument from explicit NULL.
        singscore::simpleScore(ranks, upSet = intersect(up, rownames(matrix)),
          knownDirection = TRUE, centerScore = TRUE)
      }
      value <- scored$TotalScore
      require_contract(length(value) == ncol(matrix) && all(is.finite(value)), "official score returned incomplete values")
    }
    scores[[id]] <- data.frame(dataset_id = config$dataset_id, sample_id = colnames(matrix), program_id = id, TotalScore = value,
      status = if (eligible) "ESTIMATED" else "NOT_ESTIMABLE")
  }
  list(scores = do.call(rbind, scores), coverage = do.call(rbind, coverage),
    audit = list(method = "B_SPEC_singscore", dataset_id = config$dataset_id, scope = "SCORING_ONLY_NOT_G0_OR_CONTRAST_ACCEPTANCE",
      input_sha256 = hashes, software_lock = config$software_lock, parameters = list(tiesMethod = "average",
        stableGenes = NULL, knownDirection = TRUE, centerScore = TRUE, score_column = "TotalScore")))
}

main <- function(args) {
  require_contract(length(args) == 6L, "usage: score.R config matrix signatures scores coverage audit")
  outputs <- args[4:6]
  require_contract(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) {
      target <- Sys.readlink(p)
      !is.na(target) && nzchar(target)
    }, logical(1))), "output exists or duplicates another output")
  result <- score_frozen(args[1L], args[2L], args[3L])
  # The engine publishes the container's declared outputs only after successful
  # exit; partial workspace files remain private diagnostics on failure.
  utils::write.table(result$scores, outputs[1L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  utils::write.table(result$coverage, outputs[2L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  jsonlite::write_json(result$audit, outputs[3L], auto_unbox = TRUE, pretty = TRUE, null = "null")
}
if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
