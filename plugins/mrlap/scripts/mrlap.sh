# mrlap_official - official R MRlap (frozen) in one container run.
# Pure R source executed by the `Rscript` interpreter (the twosamplemr
# harmonise.sh pattern).
#
# Contract (WO-R-02): one DAG instance computes one MRlap edge. The script
# is the plugin-port of the frozen canonical rerun
# (WOE4_mrlap_seed_rerun.R canonical v2, results/cachexia-v4/
# acceptance-mrlap-seed1-20261006/canonical/): per-edge RNGkind +
# set.seed(seed) immediately before MRlap(); do_pruning=FALSE and
# user_SNPsToKeep from input port 2 (rsID one per line); fixed LD-score and
# HM3 panel paths under the family panel mount. No statistical parameter
# differs from the canonical.
#
# Inputs:  port 0 exposure GWAS sumstat TSV (MRlap inputGWAS layout),
#          port 1 outcome GWAS sumstat TSV, port 2 instrument rsID list.
# Outputs: port 0 one-row summary TSV (17 numeric fields, the exact column
#          set of WOE4_mrlap_summary_seed1.tsv; NA stays NA), port 1 full
#          result RDS, port 2 print(res) text, port 3 run log.

run_mrlap <- function(outputs) {
initial_sinks <- sink.number()
on.exit(while (sink.number() > initial_sinks) sink(), add = TRUE)
input_exp <- Sys.getenv("AUTONOMICS_INPUT0")
input_out <- Sys.getenv("AUTONOMICS_INPUT1")
input_iv  <- Sys.getenv("AUTONOMICS_INPUT2")
summary_path <- outputs[[1L]]
rds_path  <- outputs[[2L]]
txt_path  <- outputs[[3L]]
log_path  <- outputs[[4L]]

if (!all(nzchar(c(input_exp, input_out, input_iv, summary_path, rds_path, txt_path, log_path)))) {
  stop("All declared input/output ports are required", call. = FALSE)
}
output_values <- c(summary_path, rds_path, txt_path, log_path)
output_parents <- vapply(dirname(output_values), normalizePath, character(1), mustWork = TRUE)
output_paths <- file.path(output_parents, basename(output_values))
if (anyDuplicated(output_paths)) stop("Output paths must be distinct", call. = FALSE)
link_targets <- Sys.readlink(output_paths)
if (any(file.exists(output_paths)) || any(!is.na(link_targets) & nzchar(link_targets))) {
  stop("Existing output must not be overwritten", call. = FALSE)
}
input_values <- c(input_exp, input_out, input_iv)
if (any(!file_test("-f", input_values))) {
  stop("Input files must exist and be regular files", call. = FALSE)
}

exp_label <- Sys.getenv("MRLAP_EXPOSURE")
out_label <- Sys.getenv("MRLAP_OUTCOME")
ld_path   <- Sys.getenv("MRLAP_LD_PATH", "/panels/ldsc_assets/eur_w_ld_chr")
hm3_path  <- Sys.getenv("MRLAP_HM3_PATH", "/panels/ldsc_assets/w_hm3.noMHC.snplist")
if (trimws(exp_label) == "") stop("exposure cannot be empty", call. = FALSE)
if (trimws(out_label) == "") stop("outcome cannot be empty", call. = FALSE)
if (any(grepl("[\t\r\n]", c(exp_label, out_label)))) {
  stop("Trait labels must not contain TSV row or column separators", call. = FALSE)
}
if (!dir.exists(ld_path)) stop("LD directory must exist", call. = FALSE)
if (!file.exists(hm3_path) || dir.exists(hm3_path)) stop("HM3 file must exist", call. = FALSE)

# Seed contract mirrors the canonical v2 procedure and the twosamplemr
# WO-R-03 fix: RNGkind frozen to Mersenne-Twister/Inversion/Rejection,
# set.seed immediately before MRlap() — get_correction is a parametric
# rnorm/runif bootstrap (self-reported 8000/6000 sims, no seed argument),
# so unseeded corrected_se/p are Monte-Carlo quantities.
seed_raw <- Sys.getenv("MRLAP_SEED", "1")
seed_value <- suppressWarnings(as.numeric(seed_raw))
if (!grepl("^[0-9]+$", seed_raw) || !is.finite(seed_value) || seed_value < 1 || seed_value > 2147483647) {
  stop(paste0("seed must be an integer in 1..2147483647, got `", seed_raw, "`"), call. = FALSE)
}
seed_int <- as.integer(seed_value)

ivs <- readLines(input_iv, warn = FALSE)
if (length(ivs) == 0L) stop("instrument list is empty", call. = FALSE)
if (any(!nzchar(ivs)) || any(grepl("[[:space:][:cntrl:]]", ivs))) {
  stop("Invalid instrument identifiers", call. = FALSE)
}
if (anyDuplicated(ivs)) stop("Duplicate instrument identifiers", call. = FALSE)
stopifnot(as.character(packageVersion("MRlap")) == "0.0.3.3")
stopifnot(as.character(packageVersion("GenomicSEM")) == "0.0.5")
stopifnot(as.character(packageVersion("TwoSampleMR")) == "0.7.11")
loadNamespace("MRlap")

sink(log_path, split = TRUE)
cat("MRlap version:", as.character(packageVersion("MRlap")), "\n")
cat("GenomicSEM version:", as.character(packageVersion("GenomicSEM")), "\n")
cat("TwoSampleMR version:", as.character(packageVersion("TwoSampleMR")), "\n")
cat("edge:", exp_label, "->", out_label, "\n")
cat("requested IVs:", length(ivs), "\n")
cat("RNG seed:", seed_raw, "\n")
cat("ld:", ld_path, "hm3:", hm3_path, "do_pruning: FALSE\n")
flush.console()

RNGkind("Mersenne-Twister", "Inversion", "Rejection")
set.seed(seed_int)
res <- MRlap::MRlap(exposure = input_exp, outcome = input_out,
                    ld = ld_path, hm3 = hm3_path,
                    do_pruning = FALSE, user_SNPsToKeep = ivs,
                    verbose = FALSE)
required_correction_fields <- c("observed_effect", "observed_effect_se", "corrected_effect",
                                "corrected_effect_se", "corrected_effect_p")
if (!is.list(res$MRcorrection) || !all(required_correction_fields %in% names(res$MRcorrection)) ||
    any(!vapply(res$MRcorrection[required_correction_fields], function(value) {
  is.numeric(value) && length(value) == 1L && is.finite(value)
}, logical(1)))) stop("Official primary inference is non-estimable; no analytic output published", call. = FALSE)
if (res$MRcorrection$observed_effect_se <= 0 || res$MRcorrection$corrected_effect_se <= 0 ||
    res$MRcorrection$corrected_effect_p < 0 || res$MRcorrection$corrected_effect_p > 1) {
  stop("Official primary inference has invalid SE or P; no analytic output published", call. = FALSE)
}
# Defensive summary builder: nested result objects, g() guards every
# NULL/empty field to NA (the WOE4_mrlap_summary_fix.R lesson — never
# coerce an absent quantity to 0, NA-vs-NA comparisons stay honest).
g <- function(value) {
  if (is.null(value) || length(value) == 0L) return(NA_real_)
  if (!is.numeric(value) || length(value) != 1L || is.infinite(value) || is.nan(value)) {
    stop("Summary fields must be numeric scalars or explicit missing values", call. = FALSE)
  }
  as.numeric(value)
}
mc <- res$MRcorrection
ld <- res$LDSC
s <- data.frame(
  edge = paste0(exp_label, "->", out_label),
  m_IVs = g(mc$m_IVs),
  h2_exp = g(ld$h2_exp), h2_exp_se = g(ld$h2_exp_se),
  h2_out = g(ld$h2_out), h2_out_se = g(ld$h2_out_se),
  rg = g(ld$rg), rg_se = g(ld$rg_se),
  gcov = g(ld$gcov), gcov_se = g(ld$gcov_se),
  int_crosstrait = g(ld$int_crosstrait), int_crosstrait_se = g(ld$int_crosstrait_se),
  mr_naive = g(mc$observed_effect), mr_naive_se = g(mc$observed_effect_se),
  mr_corrected = g(mc$corrected_effect), mr_corrected_se = g(mc$corrected_effect_se),
  mr_corrected_p = g(mc$corrected_effect_p),
  egger_intercept_p = g(mc$egger_intercept_p))
saveRDS(res, rds_path)
sink()
sink(txt_path)
print(res)
sink()
write.table(s, summary_path, sep = "\t", row.names = FALSE, quote = FALSE)
cat("\n== mrlap_official summary ==\n")
print(s, digits = 10)
0L
}

publish_mrlap_outputs <- function(writer) {
  need <- function(condition, message) {
    if (!isTRUE(condition)) stop(message, call. = FALSE)
  }
  destinations <- vapply(0:3, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), "")
  need(all(nzchar(destinations)), "All declared output ports are required")
  destinations <- vapply(destinations, function(filename)
    file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename)), character(1))
  need(!anyDuplicated(destinations), "Output paths must be distinct")
  path_present <- function(filename) {
    target <- Sys.readlink(filename)
    file.exists(filename) || (!is.na(target) && nzchar(target))
  }
  need(!any(vapply(destinations, path_present, logical(1))), "Existing output must not be overwritten")
  stage <- tempfile(pattern = ".mrlap-owned-", tmpdir = dirname(destinations[[1L]]))
  need(dir.create(stage, mode = "0700"), "Private output staging could not be created")
  private_outputs <- file.path(stage, c("mrlap_summary.tsv", "mrlap.RDS", "mrlap_result.txt", "mrlap.log"))
  created <- list()
  completed <- FALSE
  file_identity <- function(filename) {
    value <- system2("stat", c("-c", shQuote("%d:%i"), shQuote(filename)), stdout = TRUE, stderr = TRUE)
    need(is.null(attr(value, "status")) && length(value) == 1L && grepl("^[0-9]+:[0-9]+$", value), "Output file identity unavailable")
    value[[1L]]
  }
  on.exit({
    if (!completed) {
      for (owned in rev(created)) {
        tryCatch({
          if (path_present(owned$path) && identical(file_identity(owned$path), owned$identity)) unlink(owned$path)
        }, error = function(error) warning(paste("Output rollback retained an unverified path:", conditionMessage(error))))
      }
    }
    unlink(stage, recursive = TRUE)
  }, add = TRUE)
  status <- tryCatch(writer(private_outputs), error = function(error) {
    target <- Sys.readlink(private_outputs[[4L]])
    need(is.na(target) || !nzchar(target), "Failure log must not be a symlink")
    need(!file.exists(private_outputs[[4L]]) || file_test("-f", private_outputs[[4L]]), "Failure log must be a regular file")
    cat("BLOCKED ", conditionMessage(error), "\n", file = private_outputs[[4L]], append = TRUE, sep = "")
    1L
  })
  need(is.numeric(status) && length(status) == 1L && !is.na(status) && is.finite(status) && status %in% c(0L, 1L), "Invalid wrapper exit status")
  positions <- if (status == 0L) seq_along(destinations) else 4L
  for (position in positions) {
    filename <- private_outputs[[position]]
    target <- Sys.readlink(filename)
    need(file_test("-f", filename) && (is.na(target) || !nzchar(target)), "Required staged output must be a regular non-symlink file")
    identity <- file_identity(filename)
    need(file.link(filename, destinations[[position]]), "Exclusive output publication failed")
    created[[length(created) + 1L]] <- list(path = destinations[[position]], identity = identity)
  }
  completed <- TRUE
  status
}

if (sys.nframe() == 0L) {
  exit_status <- publish_mrlap_outputs(run_mrlap)
  if (exit_status != 0L) quit(save = "no", status = exit_status)
}
