# Official MR-PRESSO run driven by the plugin env channel: every legacy
# wrapper spec param arrives as an environment variable instead of being
# interpolated into R source by Rust. Booleans render as true/false and
# as.logical() accepts both spellings; numbers render as JSON literals and
# as.numeric() parses them exactly like the legacy embedded literals.

input <- Sys.getenv("AUTONOMICS_INPUT0")
result_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
data <- read.delim(input, check.names = FALSE, stringsAsFactors = FALSE)

beta_outcome <- Sys.getenv("MRPRESSO_BETA_OUTCOME")
sd_outcome <- Sys.getenv("MRPRESSO_SD_OUTCOME")
# String arrays are space-joined by the env renderer; splitting on a single
# space with fixed = TRUE is the exact inverse of that join. Elements
# containing spaces cannot round-trip (documented plugin limitation).
beta_exposure <- strsplit(Sys.getenv("MRPRESSO_BETA_EXPOSURE"), " ", fixed = TRUE)[[1]]
sd_exposure <- strsplit(Sys.getenv("MRPRESSO_SD_EXPOSURE"), " ", fixed = TRUE)[[1]]

# The manifest DSL cannot express cross-field or non-empty constraints (the
# legacy Rust validate()); the script enforces them with the same messages.
if (!nzchar(trimws(beta_outcome)) || !nzchar(trimws(sd_outcome))) {
  stop("beta_outcome and sd_outcome cannot be empty")
}
if (length(beta_exposure) == 0 || length(beta_exposure) != length(sd_exposure)) {
  stop("beta_exposure and sd_exposure must be non-empty and have equal lengths")
}

set.seed(as.numeric(Sys.getenv("MRPRESSO_SEED")))
result <- MRPRESSO::mr_presso(
  BetaOutcome = beta_outcome,
  BetaExposure = beta_exposure,
  SdOutcome = sd_outcome,
  SdExposure = sd_exposure,
  OUTLIERtest = as.logical(Sys.getenv("MRPRESSO_OUTLIER_TEST")),
  DISTORTIONtest = as.logical(Sys.getenv("MRPRESSO_DISTORTION_TEST")),
  data = data,
  NbDistribution = as.numeric(Sys.getenv("MRPRESSO_NB_DISTRIBUTION")),
  SignifThreshold = as.numeric(Sys.getenv("MRPRESSO_SIGNIF_THRESHOLD"))
)
sink(log_path, split = TRUE)
print(result)
sink()
saveRDS(result, result_path)
