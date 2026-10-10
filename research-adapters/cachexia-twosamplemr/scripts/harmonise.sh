
exp_path <- Sys.getenv("AUTONOMICS_INPUT0")
out_path <- Sys.getenv("AUTONOMICS_INPUT1")
harm_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
if (trimws(Sys.getenv("TWOSAMPLEMR_ID_EXPOSURE")) == "") stop("id_exposure cannot be empty", call. = FALSE)
if (trimws(Sys.getenv("TWOSAMPLEMR_EXPOSURE")) == "") stop("exposure cannot be empty", call. = FALSE)
if (trimws(Sys.getenv("TWOSAMPLEMR_ID_OUTCOME")) == "") stop("id_outcome cannot be empty", call. = FALSE)
if (trimws(Sys.getenv("TWOSAMPLEMR_OUTCOME")) == "") stop("outcome cannot be empty", call. = FALSE)
sink(log_path, split = TRUE)
cat("TwoSampleMR:", as.character(packageVersion("TwoSampleMR")), "\n")
exp <- TwoSampleMR::read_exposure_data(exp_path, sep = "\t")
out <- TwoSampleMR::read_outcome_data(out_path, sep = "\t")
cat("exposure rows:", nrow(exp), " columns:", paste(names(exp), collapse = ","), "\n")
cat("outcome rows:", nrow(out), " columns:", paste(names(out), collapse = ","), "\n")
exp$id.exposure <- Sys.getenv("TWOSAMPLEMR_ID_EXPOSURE")
exp$exposure <- Sys.getenv("TWOSAMPLEMR_EXPOSURE")
if (nzchar(Sys.getenv("TWOSAMPLEMR_UNITS_EXPOSURE"))) {
  exp$units.exposure <- Sys.getenv("TWOSAMPLEMR_UNITS_EXPOSURE")
}
out$id.outcome <- Sys.getenv("TWOSAMPLEMR_ID_OUTCOME")
out$outcome <- Sys.getenv("TWOSAMPLEMR_OUTCOME")
if (nzchar(Sys.getenv("TWOSAMPLEMR_UNITS_OUTCOME"))) {
  out$units.outcome <- Sys.getenv("TWOSAMPLEMR_UNITS_OUTCOME")
}
harm <- TwoSampleMR::harmonise_data(exp, out, action = as.numeric(Sys.getenv("TWOSAMPLEMR_HARMONISE_ACTION")))
cat("harmonised rows:", nrow(harm), " columns:", paste(names(harm), collapse = ","), "\n")
if (nrow(harm) == 0) stop("harmonise_data produced 0 rows; check SNP overlap between exposure and outcome")
names(harm)[names(harm) == "SNP"] <- "snp"
names(harm) <- gsub("\\.", "_", names(harm))
write.table(harm, harm_path, sep = "\t", quote = FALSE, row.names = FALSE)
sink()
