columns <- function(text) {
  if (!nzchar(text)) stop("Lossless R-array environment value is required")
  expressions <- parse(text = text, keep.source = FALSE)
  if (length(expressions) != 1L || !is.call(expressions[[1L]]) ||
      !identical(expressions[[1L]][[1L]], as.name("c"))) stop("Invalid R-array encoding")
  members <- as.list(expressions[[1L]])[-1L]
  if (!is.null(names(members)) && any(nzchar(names(members)))) stop("Named R-array entries are not supported")
  if (!all(vapply(members, function(member) is.character(member) && length(member) == 1L && !is.na(member), logical(1)))) {
    stop("R-array entries must be character literals; expressions are not evaluated")
  }
  vapply(members, identity, character(1), USE.NAMES = FALSE)
}

path_present <- function(filename) {
  target <- Sys.readlink(filename)
  file.exists(filename) || (!is.na(target) && nzchar(target))
}

file_identity <- function(filename) {
  result <- system2("stat", c("-c", shQuote("%d:%i"), shQuote(filename)), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(result, "status")) || length(result) != 1L || !grepl("^[0-9]+:[0-9]+$", result)) {
    stop("Output file identity unavailable")
  }
  result[[1L]]
}

main <- function() {
  input <- Sys.getenv("AUTONOMICS_INPUT0")
  result_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
  log_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
  if (any(!nzchar(c(input, result_path, log_path)))) stop("Input and both declared output paths are required")
  destinations <- vapply(c(result_path, log_path), function(filename) {
    file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename))
  }, character(1))
  if (anyDuplicated(destinations) || normalizePath(input, mustWork = TRUE) %in% destinations) {
    stop("Input and output paths must be distinct")
  }
  if (any(vapply(destinations, path_present, logical(1)))) stop("Refusing to overwrite existing result or log")
  stage <- tempfile(pattern = ".mrpresso-owned-", tmpdir = dirname(destinations[[1L]]))
  if (!dir.create(stage, mode = "0700")) stop("Private output staging could not be created")
  created <- list()
  published <- FALSE
  on.exit({
    if (!published) {
      for (owned in rev(created)) {
        tryCatch({
          if (path_present(owned$path) && identical(file_identity(owned$path), owned$identity)) unlink(owned$path)
        }, error = function(error) warning(paste("Output rollback retained an unverified path:", conditionMessage(error))))
      }
    }
    unlink(stage, recursive = TRUE)
  }, add = TRUE)
  data <- read.delim(input, check.names = FALSE, stringsAsFactors = FALSE)
  beta_outcome <- Sys.getenv("MRPRESSO_BETA_OUTCOME")
  sd_outcome <- Sys.getenv("MRPRESSO_SD_OUTCOME")
  beta_exposure <- columns(Sys.getenv("MRPRESSO_BETA_EXPOSURE_R"))
  sd_exposure <- columns(Sys.getenv("MRPRESSO_SD_EXPOSURE_R"))
  if (!nzchar(trimws(beta_outcome)) || !nzchar(trimws(sd_outcome))) {
    stop("beta_outcome and sd_outcome cannot be empty")
  }
  if (length(beta_exposure) == 0 || length(beta_exposure) != length(sd_exposure)) {
    stop("beta_exposure and sd_exposure must be non-empty and have equal lengths")
  }
  requested_columns <- c(beta_outcome, sd_outcome, beta_exposure, sd_exposure)
  if (any(!nzchar(requested_columns)) || any(make.names(requested_columns, unique = FALSE) != requested_columns)) {
    stop("MR-PRESSO requires syntactically valid formula column names")
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
  result_path <- file.path(stage, "mrpresso.RDS")
  log_path <- file.path(stage, "mrpresso.log")
  connection <- file(log_path, open = "wx")
  sink(connection, split = TRUE)
  tryCatch(print(result), finally = { sink(); close(connection) })
  saveRDS(result, result_path)
  for (position in seq_along(destinations)) {
    source <- c(result_path, log_path)[[position]]
    identity <- file_identity(source)
    if (!file.link(source, destinations[[position]])) stop("Exclusive output publication failed")
    created[[length(created) + 1L]] <- list(path = destinations[[position]], identity = identity)
  }
  published <- TRUE
}
main()
