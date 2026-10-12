# Fixed family contrast adapter. No group inference or model selection.
fail <- function(message) stop(message, call. = FALSE)
require_contract <- function(ok, message) if (!isTRUE(ok)) fail(message)
read_tsv <- function(path) utils::read.delim(path, check.names = FALSE, stringsAsFactors = FALSE,
  colClasses = "character", quote = "", comment.char = "", na.strings = c("NA", ""))

contrast_frozen <- function(config_path, scores_path, map_path, universe_path) {
  for (package in c("jsonlite", "digest"))
    require_contract(requireNamespace(package, quietly = TRUE), paste("package unavailable:", package))
  config <- jsonlite::fromJSON(config_path, simplifyVector = TRUE)
  require_contract(identical(config$status, "FROZEN") && identical(config$family, "B_SPEC_ASSOC") &&
    identical(config$planned_count, 20L) && identical(config$locked_count, 20L) &&
    identical(config$family_correction, "BH") && identical(config$dependence_sensitivity, "BY"), "complete frozen family contract required")
  require_contract(identical(config$R_version, as.character(getRversion())), "R software lock mismatch")
  hashes <- list(config = digest::digest(file = config_path, algo = "sha256"),
    scores = digest::digest(file = scores_path, algo = "sha256"),
    sample_map = digest::digest(file = map_path, algo = "sha256"),
    universe = digest::digest(file = universe_path, algo = "sha256"))
  require_contract(identical(hashes$scores, config$input_sha256$scores) &&
    identical(hashes$sample_map, config$input_sha256$sample_map) &&
    identical(hashes$universe, config$input_sha256$universe), "frozen content identity mismatch")
  universe <- read_tsv(universe_path)
  require_contract(all(c("analysis_id", "family", "program_id", "contrast_id", "dataset_id", "primary_method") %in% names(universe)) &&
    nrow(universe) == 20L && !anyDuplicated(universe$analysis_id) && all(universe$family == "B_SPEC_ASSOC"), "full 20-member universe required")
  programs <- c("NP06", "NP07", "NP08", "NP09"); contrasts <- paste0("SC0", 1:5)
  expected <- as.vector(outer(programs, contrasts, function(p,c) paste0("BSPEC_",p,"_",c)))
  require_contract(setequal(universe$analysis_id, expected) &&
    all(universe$analysis_id == paste0("BSPEC_",universe$program_id,"_",universe$contrast_id)), "hypothesis identity differs")
  require_contract(setequal(names(config$contrasts), contrasts), "five frozen contrasts required")
  sample_map <- read_tsv(map_path)
  scores <- read_tsv(scores_path)
  require_contract(identical(names(sample_map), c("dataset_id", "sample_id", "donor_id")) &&
    !anyNA(sample_map) && all(nzchar(as.matrix(sample_map))) &&
    !anyDuplicated(sample_map[c("dataset_id", "sample_id")]), "sample/donor identity map invalid")
  require_contract(all(c("dataset_id", "sample_id", "program_id", "TotalScore", "status") %in% names(scores)) &&
    !anyDuplicated(scores[c("dataset_id", "sample_id", "program_id")]) &&
    all(scores$status %in% c("ESTIMATED", "NOT_ESTIMABLE")), "score universe or status invalid")
  require_contract(setequal(unique(scores$program_id), programs), "score programs differ")
  scores$TotalScore <- suppressWarnings(as.numeric(scores$TotalScore))
  require_contract(all(is.finite(scores$TotalScore[scores$status == "ESTIMATED"])) &&
    all(is.na(scores$TotalScore[scores$status == "NOT_ESTIMABLE"])), "score value/status inconsistent")
  rows <- list(); pairs <- list()
  for (contrast in contrasts) {
    frozen <- config$contrasts[[contrast]]
    paired <- identical(contrast, "SC04")
    method <- if (paired) "PAIRED_T_SCORE_DIFFERENCE_LOW_PRECISION" else "WELCH_SCORE_DIFFERENCE"
    selected <- universe[universe$contrast_id == contrast, , drop = FALSE]
    require_contract(nrow(selected) == 4L && all(selected$dataset_id == frozen$dataset_id) &&
      all(selected$primary_method == method) && identical(frozen$model, method), "dataset or primary model differs")
    case_ids <- frozen$case_sample_ids; reference_ids <- frozen$reference_sample_ids
    require_contract(is.character(case_ids) && is.character(reference_ids) && length(case_ids) > 0L && length(reference_ids) > 0L &&
      !anyDuplicated(case_ids) && !anyDuplicated(reference_ids) && !length(intersect(case_ids, reference_ids)), "case/reference sample sets invalid")
    map <- sample_map[sample_map$dataset_id == frozen$dataset_id, , drop = FALSE]
    require_contract(all(c(case_ids, reference_ids) %in% map$sample_id), "frozen donor mapping is missing")
    excluded <- frozen$excluded_samples
    require_contract(is.list(excluded) &&
      all(vapply(excluded, function(reason) is.character(reason) && length(reason) == 1L && nzchar(reason), logical(1))) &&
      !length(intersect(names(excluded), c(case_ids, reference_ids))) &&
      setequal(map$sample_id, c(case_ids, reference_ids, names(excluded))), "complete frozen inclusion/exclusion flow required")
    case_donors <- map$donor_id[match(case_ids, map$sample_id)]
    reference_donors <- map$donor_id[match(reference_ids, map$sample_id)]
    require_contract(!anyDuplicated(case_donors) && !anyDuplicated(reference_donors), "specimens cannot inflate independent donor count")
    require_contract(length(case_donors) == frozen$expected_case_donors &&
      length(reference_donors) == frozen$expected_reference_donors, "verified donor denominator differs")
    if (!paired) require_contract(!length(intersect(case_donors, reference_donors)), "Welch arms share donors")
    if (paired) require_contract(setequal(case_donors, reference_donors), "paired donor identities differ")
    for (program in programs) {
      id <- paste0("BSPEC_", program, "_", contrast)
      subset <- scores[scores$dataset_id == frozen$dataset_id & scores$program_id == program, , drop = FALSE]
      require_contract(all(c(case_ids, reference_ids) %in% subset$sample_id), "frozen sample scores are missing")
      x <- subset$TotalScore[match(case_ids, subset$sample_id)]
      y <- subset$TotalScore[match(reference_ids, subset$sample_id)]
      row <- data.frame(test_id = id, family = "B_SPEC_ASSOC", estimand_id = "E_B_SPEC",
        status = "NOT_ESTIMABLE", reason = "SCORE_OR_MODEL_NOT_ESTIMABLE", effect = NA_real_,
        ci_low = NA_real_, ci_high = NA_real_, n_case_donors = length(case_donors),
        n_reference_donors = length(reference_donors), n_case_score_eligible = sum(is.finite(x)),
        n_reference_score_eligible = sum(is.finite(y)), raw_p = NA_real_, method = method,
        low_precision_support_only = paired)
      # Complete selected donor sets, not post-score filtering, are the primary
      # model units. Missing score/pair gives NA and keeps the original row.
      if (all(is.finite(c(x,y))) && length(x) >= (if (paired) 3L else 2L) && length(y) >= 2L) {
        if (paired) {
          y <- y[match(case_donors, reference_donors)]
          pairs[[id]] <- data.frame(test_id = id, donor_id = case_donors, case_score = x,
            reference_score = y, difference = x-y)
        }
        model <- tryCatch(stats::t.test(x, y, paired = paired, var.equal = FALSE,
          alternative = "two.sided", conf.level = 0.95), error = function(e) NULL)
        if (!is.null(model) && is.finite(model$p.value) && all(is.finite(model$conf.int))) {
          row$status <- "ESTIMATED"; row$reason <- ""
          row$effect <- if (paired) mean(x-y) else mean(x) - mean(y)
          row$ci_low <- model$conf.int[1L]; row$ci_high <- model$conf.int[2L]; row$raw_p <- model$p.value
        } else row$reason <- "DEGENERATE_VARIANCE_OR_INVALID_T_MODEL"
      }
      rows[[id]] <- row
    }
  }
  table <- do.call(rbind, rows)
  table$adjustment_p <- ifelse(is.na(table$raw_p), 1, table$raw_p)
  table$q_bh <- stats::p.adjust(table$adjustment_p, method = "BH", n = 20L)
  table$q_by <- stats::p.adjust(table$adjustment_p, method = "BY", n = 20L)
  table$family_size <- 20L
  # COMPLETE describes registered row coverage and terminal estimation states;
  # it does not say all tests estimated or scientifically accepted.
  table$family_status <- "COMPLETE"
  empty_pairs <- data.frame(test_id = character(), donor_id = character(), case_score = double(),
    reference_score = double(), difference = double())
  list(table = table, pairs = if (length(pairs)) do.call(rbind, pairs) else empty_pairs,
    audit = list(scope = "TECHNICAL_CONTRASTS_NOT_G0_OR_SCIENTIFIC_SIGNOFF", input_sha256 = hashes,
      planned_count = 20L, R_version = as.character(getRversion()),
      frozen_inclusion_exclusion = config$contrasts,
      estimated_count = sum(table$status == "ESTIMATED"), not_estimable_count = sum(table$status == "NOT_ESTIMABLE")))
}

main <- function(args) {
  require_contract(length(args) == 7L, "usage: contrasts.R config scores donor-map universe table pairs audit")
  outputs <- args[5:7]
  require_contract(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) {target <- Sys.readlink(p); !is.na(target) && nzchar(target)}, logical(1))), "output already exists")
  result <- contrast_frozen(args[1L], args[2L], args[3L], args[4L])
  utils::write.table(result$table, outputs[1L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  utils::write.table(result$pairs, outputs[2L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  jsonlite::write_json(result$audit, outputs[3L], auto_unbox = TRUE, pretty = TRUE)
}
if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
