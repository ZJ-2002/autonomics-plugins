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

input_exp <- Sys.getenv("AUTONOMICS_INPUT0")
input_out <- Sys.getenv("AUTONOMICS_INPUT1")
input_iv  <- Sys.getenv("AUTONOMICS_INPUT2")
summary_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
rds_path  <- Sys.getenv("AUTONOMICS_OUTPUT1")
txt_path  <- Sys.getenv("AUTONOMICS_OUTPUT2")
log_path  <- Sys.getenv("AUTONOMICS_OUTPUT3")

exp_label <- Sys.getenv("MRLAP_EXPOSURE")
out_label <- Sys.getenv("MRLAP_OUTCOME")
ld_path   <- Sys.getenv("MRLAP_LD_PATH", "/panels/ldsc_assets/eur_w_ld_chr")
hm3_path  <- Sys.getenv("MRLAP_HM3_PATH", "/panels/ldsc_assets/w_hm3.noMHC.snplist")
if (trimws(exp_label) == "") stop("exposure cannot be empty", call. = FALSE)
if (trimws(out_label) == "") stop("outcome cannot be empty", call. = FALSE)

# Seed contract mirrors the canonical v2 procedure and the twosamplemr
# WO-R-03 fix: RNGkind frozen to Mersenne-Twister/Inversion/Rejection,
# set.seed immediately before MRlap() — get_correction is a parametric
# rnorm/runif bootstrap (self-reported 8000/6000 sims, no seed argument),
# so unseeded corrected_se/p are Monte-Carlo quantities.
seed_raw <- Sys.getenv("MRLAP_SEED", "1")
seed_int <- suppressWarnings(as.integer(seed_raw))
if (is.na(seed_int) || seed_int < 1L || seed_int > 2147483647L) {
  stop(paste0("seed must be an integer in 1..2147483647, got `", seed_raw, "`"), call. = FALSE)
}

ivs <- readLines(input_iv)
ivs <- ivs[nzchar(ivs)]
if (length(ivs) == 0L) stop("instrument list is empty", call. = FALSE)

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
saveRDS(res, rds_path)
sink()
sink(txt_path)
print(res)
sink()

# Defensive summary builder: nested result objects, g() guards every
# NULL/empty field to NA (the WOE4_mrlap_summary_fix.R lesson — never
# coerce an absent quantity to 0, NA-vs-NA comparisons stay honest).
g <- function(x) if (is.null(x) || length(x) == 0) NA else as.numeric(x)[1]
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
write.table(s, summary_path, sep = "\t", row.names = FALSE, quote = FALSE)
cat("\n== mrlap_official summary ==\n")
print(s, digits = 10)
q(status = 0)
