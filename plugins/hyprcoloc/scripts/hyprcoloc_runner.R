#!/usr/bin/env Rscript
# HyPrColoc contract: one SNP-aligned table with per-trait beta / se columns
# in, official result table + RDS + log out.
#
# This script replaces the legacy Rust-side script template. Every parameter
# travels through HYPRCOLOC_* environment variables and the conditionals the
# v0 manifest DSL cannot express (optional official arguments, cross-field
# trait validation, branch-and-bound threshold floors) live here, so the
# failure point moves from registry build to container start — the same
# trade the deseq2/mrpresso/mvmr migrations made.

options(stringsAsFactors = FALSE, digits = 15)

required_env <- function(name) {
  value <- Sys.getenv(name)
  if (!nzchar(value)) {
    stop(sprintf("missing required environment variable: %s", name), call. = FALSE)
  }
  value
}

split_csv <- function(value) {
  if (!nzchar(value)) return(character())
  values <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  values[nzchar(values)]
}

to_bool <- function(value) {
  if (!value %in% c("true", "false")) {
    stop(sprintf("boolean environment value must be true or false, got `%s`", value), call. = FALSE)
  }
  identical(value, "true")
}

required_number <- function(name, label) {
  parsed <- suppressWarnings(as.numeric(required_env(name)))
  if (is.na(parsed) || !is.finite(parsed) || parsed <= 0 || parsed > 1) {
    stop(sprintf("%s must be in (0, 1]", label), call. = FALSE)
  }
  parsed
}

optional_number <- function(name, label) {
  value <- Sys.getenv(name)
  if (!nzchar(value)) return(NULL)
  parsed <- suppressWarnings(as.numeric(value))
  if (is.na(parsed) || !is.finite(parsed) || parsed <= 0 || parsed > 1) {
    stop(sprintf("%s must be in (0, 1] when provided", label), call. = FALSE)
  }
  parsed
}

input <- required_env("AUTONOMICS_INPUT0")
table_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
rds_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT2")

snp_column <- trimws(required_env("HYPRCOLOC_SNP_COLUMN"))

# HYPRCOLOC_TRAITS is the per-trait column mapping, one `name,beta,se,binary`
# row per trait in the official matrix column order, rows joined by `;`.
# Trait names and column names must not contain `,` or `;`.
traits_spec <- required_env("HYPRCOLOC_TRAITS")
trait_rows <- trimws(strsplit(traits_spec, ";", fixed = TRUE)[[1]])
trait_rows <- trait_rows[nzchar(trait_rows)]
if (length(trait_rows) < 2) {
  stop("hyprcoloc requires at least two traits", call. = FALSE)
}
trait_fields <- strsplit(trait_rows, ",", fixed = TRUE)
if (any(vapply(trait_fields, length, integer(1)) != 4L)) {
  stop("each trait must be name,beta,se,binary_outcome", call. = FALSE)
}
trait_names <- unname(trimws(vapply(trait_fields, `[`, character(1), 1L)))
beta_columns <- unname(trimws(vapply(trait_fields, `[`, character(1), 2L)))
se_columns <- unname(trimws(vapply(trait_fields, `[`, character(1), 3L)))
binary_outcomes <- unname(trimws(vapply(trait_fields, `[`, character(1), 4L)))
if (any(!nzchar(trait_names))) {
  stop("trait name cannot be empty", call. = FALSE)
}
if (any(!nzchar(beta_columns)) || any(!nzchar(se_columns))) {
  stop("every trait must supply non-empty beta and se columns", call. = FALSE)
}
if (!all(binary_outcomes %in% c("0", "1"))) {
  stop("binary_outcome must be 0 (continuous) or 1 (binary)", call. = FALSE)
}
if (anyDuplicated(trait_names)) {
  stop("trait names must be unique", call. = FALSE)
}
all_columns <- c(snp_column, beta_columns, se_columns)
if (anyDuplicated(all_columns)) {
  stop("snp, beta, and se columns must be unique", call. = FALSE)
}

trait_subset <- split_csv(Sys.getenv("HYPRCOLOC_TRAIT_SUBSET"))
if (length(trait_subset) && any(!trait_subset %in% trait_names)) {
  stop("unknown trait_subset entry", call. = FALSE)
}

prior_1 <- required_number("HYPRCOLOC_PRIOR_1", "prior_1")
prior_c <- required_number("HYPRCOLOC_PRIOR_C", "prior_c")
prior_12 <- optional_number("HYPRCOLOC_PRIOR_12", "prior_12")
reg_thresh <- optional_number("HYPRCOLOC_REG_THRESH", "reg_thresh")
align_thresh <- optional_number("HYPRCOLOC_ALIGN_THRESH", "align_thresh")

uniform_priors <- to_bool(required_env("HYPRCOLOC_UNIFORM_PRIORS"))
bb_alg <- to_bool(required_env("HYPRCOLOC_BB_ALG"))
bb_selection <- required_env("HYPRCOLOC_BB_SELECTION")
if (!bb_selection %in% c("regional", "alignment")) {
  stop("bb_selection must be regional or alignment", call. = FALSE)
}
reg_steps <- suppressWarnings(as.integer(required_env("HYPRCOLOC_REG_STEPS")))
if (is.na(reg_steps) || reg_steps < 1) {
  stop("reg_steps must be greater than zero", call. = FALSE)
}
snpscores <- to_bool(required_env("HYPRCOLOC_SNPSCORES"))

if (bb_alg) {
  minimum <- if (uniform_priors) 0.6 else 0.5
  floor_check <- function(value) {
    !is.null(value) && value < minimum
  }
  if (floor_check(reg_thresh) || floor_check(align_thresh)) {
    stop(sprintf("bb_alg thresholds must be at least %s for this prior mode", minimum), call. = FALSE)
  }
}

data <- read.delim(input, check.names = FALSE, stringsAsFactors = FALSE)
required_columns <- c(snp_column, beta_columns, se_columns)
missing_columns <- setdiff(required_columns, names(data))
if (length(missing_columns) > 0) {
  stop("missing required input columns: ", paste(missing_columns, collapse = ", "))
}

snp_id <- data[[snp_column]]
if (any(is.na(snp_id)) || anyDuplicated(snp_id) > 0) {
  stop("SNP IDs must be present and unique")
}
effect_est <- as.matrix(data[beta_columns])
effect_se <- as.matrix(data[se_columns])
if (!all(vapply(effect_est, is.numeric, logical(1))) ||
    !all(vapply(effect_se, is.numeric, logical(1)))) {
  stop("beta and se columns must be numeric")
}

binary_vector <- as.integer(binary_outcomes)

args <- list(
  effect.est = effect_est,
  effect.se = effect_se,
  binary.outcomes = binary_vector,
  trait.names = trait_names,
  snp.id = snp_id,
  bb.alg = bb_alg,
  bb.selection = bb_selection,
  reg.steps = reg_steps,
  prior.1 = prior_1,
  prior.c = prior_c,
  uniform.priors = uniform_priors,
  snpscores = snpscores
)
if (!is.null(trait_subset)) args$trait.subset <- trait_subset
if (!is.null(reg_thresh)) args$reg.thresh <- reg_thresh
if (!is.null(align_thresh)) args$align.thresh <- align_thresh
if (!is.null(prior_12)) args$prior.12 <- prior_12

result <- do.call(hyprcoloc::hyprcoloc, args)

write.table(
  result$results,
  table_path,
  sep = "\t",
  quote = FALSE,
  row.names = FALSE,
  na = "NA"
)
sink(log_path, split = TRUE)
cat("## hyprcoloc (official R package 0.0.2)\n")
cat("traits:", paste(trait_names, collapse = ", "), "\n")
print(result)
sink()
saveRDS(result, rds_path)
