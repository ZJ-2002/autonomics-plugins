options(warn = 1, digits = 17)
outputs <- vapply(0:5, function(port) Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)), character(1))
analytic <- outputs[c(1, 2, 4, 6)]
unlink(analytic)
writeLines("status\tRUNNING\nscope\tTECHNICAL_ONLY_NOT_G0", outputs[3])
audit <- list(status = "RUNNING", scientific_G0_granted = "false", PP_H4_result = "false", three_trait_bridge_qualified = "false")
require_true <- function(condition, message) if (!isTRUE(condition)) stop(message, call. = FALSE)
record <- function(...) cat(..., "\n", file = outputs[3], append = TRUE)
write_tsv <- function(value, filename) write.table(value, filename, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
save_audit <- function(value = audit) write_tsv(data.frame(key = names(value), value = vapply(value, as.character, character(1))), outputs[5])
read_text <- function(filename) read.delim(filename, colClasses = "character", check.names = FALSE, quote = "", comment.char = "", na.strings = character())
hash <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_true(is.null(attr(result, "status")) && length(result) == 1 && grepl("^[a-f0-9]{64} ", result), "Content hash unavailable")
  substr(result, 1, 64)
}
identities <- function(values) all(nzchar(values)) && !anyDuplicated(values) && !any(grepl('["/,;\t\r\n]', values)) && all(trimws(values) == values)
numbers <- function(raw) {
  values <- suppressWarnings(as.numeric(raw))
  require_true(all(is.finite(values)), "Missing/nonfinite numeric input")
  zero_text <- grepl("^[+-]?(0+(\\.0*)?|\\.0+)([eE][+-]?[0-9]+)?$", raw)
  require_true(all(values != 0 | zero_text), "Nonzero numeric input underflowed")
  values
}
integer_value <- function(raw, maximum) {
  require_true(grepl("^(0|[1-9][0-9]*)$", raw) && nchar(raw) <= nchar(as.character(maximum)), "Canonical nonnegative integer required")
  value <- as.numeric(raw)
  require_true(is.finite(value) && value <= maximum, "Integer outside accepted domain")
  as.integer(value)
}
boolean_value <- function(raw) {
  require_true(raw %in% c("true", "false"), "Canonical boolean required")
  raw == "true"
}
probability <- function(raw) {
  value <- numbers(raw)
  require_true(length(value) == 1 && value > 0 && value < 1, "Probability must be strictly within (0,1)")
  value
}
matrix_input <- function(filename, ids, overlap = FALSE) {
  data <- read_text(filename)
  require_true(identical(names(data), c("id", ids)) && identical(data$id, ids), "Matrix row/column identities or ordering differ")
  result <- matrix(numbers(unlist(data[-1], use.names = FALSE)), nrow = length(ids))
  require_true(max(abs(result - t(result))) <= 1e-12 && all(diag(result) == 1), "Matrix must be symmetric with unit diagonal")
  require_true(all(abs(result) <= 1) && (!overlap || all(result >= 0)), "Matrix entries outside accepted correlation/overlap domain")
  require_true(min(eigen(result, symmetric = TRUE, only.values = TRUE)$values) >= -1e-10, "Correlation/overlap/LD matrix is not positive semidefinite")
  result
}
flatten <- function(object, prefix = "result") {
  records <- list()
  walk <- function(value, path) {
    if (is.data.frame(value)) {
      for (column in names(value)) for (index in seq_len(nrow(value))) walk(value[[column]][index], paste(path, column, index, sep = "/"))
    } else if (is.list(value)) {
      for (index in seq_along(value)) walk(value[[index]], paste(path, if (is.null(names(value))) index else names(value)[index], sep = "/"))
    } else {
      for (index in seq_along(value)) {
        item <- value[index]
        field <- if (length(value) == 1) path else paste(path, index, sep = "/")
        kind <- if (is.na(item)) "MISSING_OFFICIAL" else if (is.numeric(item)) "NUMERIC" else "TEXT"
        require_true(is.na(item) || !is.numeric(item) || is.finite(item), "Nonfinite official result; no technical pass")
        numeric_value <- if (kind == "NUMERIC") sprintf("%.17g", item) else "NA"
        records[[length(records) + 1L]] <<- data.frame(field = field, value_type = kind, numeric_value = numeric_value, text_value = if (is.na(item)) "NA" else as.character(item))
      }
    }
  }
  walk(object, prefix)
  result <- do.call(rbind, records)
  require_true(!is.null(result) && !anyDuplicated(result$field), "Official result fields empty or ambiguous")
  result
}

tryCatch({
  require_true(Sys.getenv("AUTONOMICS_INPUT_COUNT") == "6", "Exactly six inputs required")
  inputs <- vapply(0:5, function(port) Sys.getenv(paste0("AUTONOMICS_INPUT", port)), character(1))
  request <- read_text(inputs[3])
  keys <- c("schema_version", "scope", "test_id", "input_role", "effect_scale", "alignment", "missing_policy", "matrix_qualification",
            "input0_sha256", "input1_sha256", "input3_sha256", "input4_sha256", "input5_sha256", "trait_subset",
            "bb_alg", "bb_selection", "reg_steps", "reg_thresh", "align_thresh", "prior_1", "prior_c", "prior_12",
            "sensitivity", "sense_1", "sense_2", "uniform_priors", "ind_traits", "snpscores")
  require_true(identical(names(request), c("key", "value")) && !anyDuplicated(request$key) && setequal(request$key, keys), "Frozen contract key set differs")
  contract <- setNames(as.list(request$value), request$key)
  require_true(contract$schema_version == "1" && contract$scope == "TECHNICAL_ONLY_NOT_G0", "Invalid schema/scientific scope")
  require_true(identities(contract$test_id), "Invalid test identity")
  require_true(contract$input_role %in% c("SYNTHETIC_TECHNICAL_INPUT", "OFFICIAL_AUTHOR_EXAMPLE", "LEGACY_SEEN"), "New scientific evidence is not authorized")
  require_true(contract$effect_scale == "CONVENTIONAL_BETA_NOT_MRLAP_Z" && contract$alignment == "PREHARMONISED_REQUIRED" && contract$missing_policy == "reject", "Effect-scale/alignment/missing contract differs")
  require_true(contract$matrix_qualification %in% c("SYNTHETIC_TECHNICAL_ONLY", "EXTERNALLY_QUALIFIED_ATTESTATION"), "Unknown matrix qualification; no implicit independence")
  require_true(contract$input_role != "LEGACY_SEEN" || contract$matrix_qualification == "EXTERNALLY_QUALIFIED_ATTESTATION", "Real data require external matrix qualification")
  audit$test_id <- contract$test_id
  for (port in c(0, 1, 3, 4, 5)) {
    key <- paste0("input", port, "_sha256")
    require_true(grepl("^[a-f0-9]{64}$", contract[[key]]) && hash(inputs[port + 1]) == contract[[key]], "Frozen input content identity differs")
    audit[[key]] <- hash(inputs[port + 1])
  }
  audit$contract_sha256 <- hash(inputs[3])
  audit$external_alignment_and_matrix_qualification_not_independently_proven <- "true"
  require_true(as.character(packageVersion("hyprcoloc")) == "0.0.2" && as.character(getRversion()) == "4.5.1", "Official method/runtime version differs")
  traits <- read_text(inputs[2])
  require_true(identical(names(traits), c("trait", "beta", "se", "binary_outcome")) && nrow(traits) >= 2 && nrow(traits) <= 12, "Trait schema or budget differs")
  require_true(identities(traits$trait) && !anyDuplicated(tolower(traits$trait)) && !"all" %in% tolower(traits$trait), "Trait identities ambiguous or reserved")
  columns <- c(traits$beta, traits$se)
  require_true(identities(columns) && !"SNP" %in% columns && all(grepl("^[A-Za-z][A-Za-z0-9_]*$", columns)), "Trait effect columns ambiguous")
  require_true(all(traits$binary_outcome %in% c("0", "1")), "Binary outcome must be canonical 0/1")
  selected <- if (contract$trait_subset == "ALL") traits$trait else strsplit(contract$trait_subset, ",", fixed = TRUE)[[1]]
  require_true(length(selected) >= 2 && identities(selected) && !anyDuplicated(tolower(selected)) && all(tolower(selected) %in% tolower(traits$trait)), "Explicit subset must contain at least two distinct known traits")
  data <- read_text(inputs[1])
  require_true(!anyDuplicated(names(data)) && setequal(names(data), c("SNP", columns)) && nrow(data) >= 2 && nrow(data) <= 1200, "SNP/effect schema or budget differs")
  require_true(identities(data$SNP), "Unique lexical SNP identities required")
  beta <- matrix(numbers(unlist(data[traits$beta], use.names = FALSE)), nrow = nrow(data))
  se <- matrix(numbers(unlist(data[traits$se], use.names = FALSE)), nrow = nrow(data))
  require_true(all(se > 0), "SE must be strictly positive")
  require_true(all(is.finite(beta / se)), "Effect/SE ratio overflow")
  trait_cor <- matrix_input(inputs[4], traits$trait)
  overlap <- matrix_input(inputs[5], traits$trait, overlap = TRUE)
  ld <- matrix_input(inputs[6], data$SNP)
  bb <- boolean_value(contract$bb_alg)
  uniform <- boolean_value(contract$uniform_priors)
  independent <- boolean_value(contract$ind_traits)
  sensitivity <- boolean_value(contract$sensitivity)
  snpscores <- boolean_value(contract$snpscores)
  require_true(contract$bb_selection %in% c("regional", "align", "reg.only"), "Official bb.selection must be regional, align or reg.only")
  steps <- integer_value(contract$reg_steps, nrow(traits))
  sense1 <- integer_value(contract$sense_1, nrow(traits))
  sense2 <- integer_value(contract$sense_2, nrow(traits))
  require_true(sense2 > sense1, "sense.2 must exceed sense.1")
  threshold <- function(raw) if (raw == "default") "default" else probability(raw)
  reg <- threshold(contract$reg_thresh)
  align <- threshold(contract$align_thresh)
  effective_reg <- if (identical(reg, "default")) if (uniform) 0.7 else 0.5 else reg
  effective_align <- if (identical(align, "default")) if (uniform) 0.7 else 0.5 else align
  require_true(!bb || min(effective_reg, effective_align) >= if (uniform) 0.6 else 0.5, "Official branch-and-bound threshold floor violated")
  prior1 <- probability(contract$prior_1)
  priorc <- probability(contract$prior_c)
  prior12 <- if (contract$prior_12 == "NULL") NULL else probability(contract$prior_12)
  rapid <- (independent || all(trait_cor[lower.tri(trait_cor)] == 0)) && steps == 1
  require_true(!sensitivity || !rapid, "Official 0.0.2 rapid sensitivity branch lacks snps.clc; no silent reg_steps replacement")
  require_true(rapid || (nrow(data) <= 50 && nrow(traits) <= 4 && steps <= 2 && sense2 <= 2), "Nonrapid computation exceeds frozen technical budget")
  audit$method_version <- "0.0.2"
  audit$selected_traits <- paste(traits$trait[tolower(traits$trait) %in% tolower(selected)], collapse = ",")
  audit$effective_reg_threshold <- effective_reg
  audit$effective_align_threshold <- effective_align
  audit$effective_prior_c <- if (is.null(prior12)) priorc else prior12 / (prior1 + prior12)
  audit$prior_c_overridden_by_prior12 <- tolower(as.character(!is.null(prior12)))
  audit$rapid_branch <- tolower(as.character(rapid))
  audit$correlation_assumed_independent <- tolower(as.character(independent || all(trait_cor[lower.tri(trait_cor)] == 0)))
  audit$result_semantics <- if (sensitivity) "REGIONAL_SENSITIVITY_NOT_COLOCALIZATION" else if (bb && contract$bb_selection == "reg.only") "REGIONAL_ONLY_NOT_COLOCALIZATION" else "OFFICIAL_MULTI_TRAIT_COLOCALIZATION_NOT_PPH4"
  record("METHOD", "hyprcoloc", "0.0.2", "SEMANTICS", audit$result_semantics)
  record("CALL", paste(request$key, request$value, sep = "=", collapse = " "))
  result <- withCallingHandlers(hyprcoloc::hyprcoloc(effect.est = beta, effect.se = se, binary.outcomes = as.integer(traits$binary_outcome),
    trait.subset = selected, trait.names = traits$trait, snp.id = data$SNP, ld.matrix = ld, trait.cor = trait_cor,
    sample.overlap = overlap, bb.alg = bb, bb.selection = contract$bb_selection, reg.steps = steps,
    reg.thresh = reg, align.thresh = align, prior.1 = prior1, prior.c = priorc, prior.12 = prior12,
    sensitivity = sensitivity, sense.1 = sense1, sense.2 = sense2, uniform.priors = uniform, ind.traits = independent, snpscores = snpscores),
    warning = function(warning) { record("WARNING", conditionMessage(warning)); invokeRestart("muffleWarning") })
  write_tsv(flatten(result), outputs[1])
  saveRDS(result, outputs[2])
  record(paste(capture.output(print(result)), collapse = "\n"))
  write_tsv(data.frame(SNP = data$SNP, input_order = seq_len(nrow(data)), retained = TRUE), outputs[4])
  traits$input_order <- seq_len(nrow(traits))
  traits$selected <- tolower(traits$trait) %in% tolower(selected)
  write_tsv(traits, outputs[6])
  audit$status <- "TECHNICAL_METHOD_PASS_NOT_SCIENTIFIC_RELEASE"
  audit$official_probability_summary_rounding <- if (sensitivity) "NOT_APPLIED_TO_REGIONAL_SENSITIVITY" else "FOUR_DECIMALS_IN_OFFICIAL_RESULTS"
  audit$official_SNP_scores_not_wrapper_rounded <- "true"
  audit$requested_snps <- nrow(data)
  audit$requested_traits <- nrow(traits)
  for (port in c(0, 1, 3, 5)) audit[[paste0("output", port, "_sha256")]] <- hash(outputs[port + 1])
  save_audit()
  record("status\tPASS")
}, error = function(error) {
  unlink(analytic)
  audit$status <- "BLOCKED"
  audit$error <- conditionMessage(error)
  save_audit(audit)
  record("status\tBLOCKED", conditionMessage(error))
  message(conditionMessage(error))
  quit(status = 2)
})
