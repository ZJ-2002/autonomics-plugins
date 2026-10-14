args <- commandArgs(trailingOnly = TRUE)
h <- read.delim(file.path(args[1], "input.tsv"), check.names = FALSE)
r <- readRDS(file.path(args[2], "output6"))
w <- 1 / h$se.outcome^2
b <- sum(w * h$beta.exposure * h$beta.outcome) / sum(w * h$beta.exposure^2)
Q <- sum(w * (h$beta.outcome - b * h$beta.exposure)^2)
se <- sqrt(max(1, Q / (nrow(h) - 1)) / sum(w * h$beta.exposure^2))
ivw <- r$mr[r$mr$method == "Inverse variance weighted", ]
stopifnot(abs(ivw$b - b) < 1e-12, abs(ivw$se - se) < 1e-12,
          abs(ivw$pval - 2 * pnorm(-abs(b / se))) < 1e-12,
          (Q / (nrow(h)-1) < 1) == (args[3] == "under"),
          r$contract$bootstrap_n == 1000L,
          all(is.na(r$mr$p_primary)), all(r$mr$p_for_family == 1),
          all(r$mr$role == "EXPLORATORY_OVERLAP_UNRESOLVED"),
          identical(r$harmonised, h), nrow(r$leave_one_out) == nrow(h)+1,
          nrow(r$regional_sensitivities) == 9)
# Independent direct invocation follows the complete frozen official sequence.
set.seed(432202610)
methods <- c("mr_ivw", "mr_egger_regression", "mr_weighted_median")
direct <- TwoSampleMR::mr(h, method_list = methods)
stopifnot(identical(r$mr[, names(direct)], direct))
stopifnot(identical(r$heterogeneity, TwoSampleMR::mr_heterogeneity(h, method_list = methods[1:2])),
          identical(r$egger_intercept, TwoSampleMR::mr_pleiotropy_test(h)),
          identical(r$leave_one_out, TwoSampleMR::mr_leaveoneout(h)))
mhc <- h$chr37 == 6 & h$pos37 >= 25000000 & h$pos37 <= 34000000
tert <- h$chr37 == 5 & h$pos37 >= 1 & h$pos37 <= 2000000
regional <- do.call(rbind, lapply(list(exclude_MHC=!mhc, exclude_TERT_vicinity=!tert,
                                      exclude_both=!(mhc | tert)), function(keep) {
  z <- TwoSampleMR::mr(h[keep, , drop = FALSE], method_list = methods)
  z$p_primary <- NA; z$role <- "REGISTERED_SENSITIVITY_ONLY"; z
}))
regional$sensitivity <- rep(c("exclude_MHC", "exclude_TERT_vicinity", "exclude_both"), each = 3)
stopifnot(identical(r$regional_sensitivities, regional))
jsonlite::write_json(list(technical_method_checks = TRUE, scope = "SYNTHETIC_METHOD_TEST",
  independent_ivw_beta = b, independent_ivw_se = se, Q = Q, Q_over_df = Q/(nrow(h)-1),
  official_full_sequence_parity = TRUE, bootstrap_n = 1000,
  R = as.character(getRversion()), TwoSampleMR = as.character(packageVersion("TwoSampleMR")),
  mr_ivw_body = paste(deparse(body(TwoSampleMR::mr_ivw)), collapse="\n"),
  mr_ivw_formals = paste(deparse(formals(TwoSampleMR::mr_ivw)), collapse="\n"),
  scientific_authorization_granted = FALSE, g0_granted = FALSE), file.path(args[2], "verification.json"),
  pretty = TRUE, auto_unbox = TRUE, digits = 17)
