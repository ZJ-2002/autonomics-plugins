FROZEN_INPUT_SHA <- c(
  "254c57122637840e6dc4f952e6a73ba1e660063442e7a2b2d6b5e194db25d85a",
  "20b5269c35c322a5491138cf5a95d8c0ebff085ca12a6fe0c09c9d472fec30cd",
  "8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f",
  "aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2",
  "8aeaa7bb2b22b2c4ae9852dc65d32d4f81cb927d875ecdd135822f2f1c2b8a56",
  "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd")
QUALIFY_BLOCK_SHA <- "50be9627766c996714e1c18ef7c32862ed2f9807814a9f61b5b3bd7c476e4f1d"
EXPECTED_FUNCTION_COUNT <- 171L
EXPECTED_FUNCTION_AGGREGATE <- "127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73"
OUTPUT_NAMES <- c("A_HARMONIZED_INPUT_AUDIT.tsv", "A_FROZEN_EXPLORATORY_INPUT.tsv",
                  "A_HARMONIZATION_QUALIFICATION.json", "INPUT_METHOD_PROVENANCE.json", "harmonisation.log")

namespace_function_identity <- function() {
 namespace <- asNamespace("TwoSampleMR")
 names <- sort(ls(namespace,all.names=TRUE),method="radix")
 names <- names[vapply(names,function(name) is.function(get(name,envir=namespace,inherits=FALSE)),logical(1))]
 hashes <- vapply(names,function(name) {
  fun <- get(name,envir=namespace,inherits=FALSE)
  lines <- c(paste0("name=",name),"FORMALS",deparse(formals(fun),width.cutoff=500L),
             "BODY",deparse(body(fun),width.cutoff=500L))
  digest::digest(charToRaw(paste(lines,collapse="\n")),algo="sha256",serialize=FALSE)
 },"")
 aggregate <- digest::digest(charToRaw(paste(paste(names(hashes),hashes,sep="\t"),collapse="\n")),algo="sha256",serialize=FALSE)
 list(function_count=length(hashes),aggregate_sha256=aggregate,functions=as.list(hashes))
}

check_namespace_identity <- function(record) {
  if (!identical(record$function_count, EXPECTED_FUNCTION_COUNT) ||
      !identical(record$aggregate_sha256, EXPECTED_FUNCTION_AGGREGATE) ||
      length(record$functions) != EXPECTED_FUNCTION_COUNT || anyDuplicated(names(record$functions)))
    stop("Complete official TwoSampleMR namespace function identity differs")
  invisible(TRUE)
}

check_frozen_inputs <- function(hashes) {
  if (!identical(unname(hashes), FROZEN_INPUT_SHA)) stop("Only the exact six frozen harmonisation inputs are supported")
}

extract_qualify_a <- function(text) {
  first <- '} else if(mode=="qualify-A") {\n'
  last <- '\n} else if(mode=="test") {'
  starts <- gregexpr(first, text, fixed = TRUE)[[1]]
  ends <- gregexpr(last, text, fixed = TRUE)[[1]]
  if (length(starts) != 1L || starts[1L] < 1L || length(ends) != 1L || ends[1L] <= starts[1L])
    stop("Unique complete frozen qualify-A branch required")
  block <- substr(text, starts[1L] + nchar(first), ends[1L] - 1L)
  if (nchar(block, type = "bytes") != 2172L ||
      !identical(digest::digest(charToRaw(block), algo = "sha256", serialize = FALSE), QUALIFY_BLOCK_SHA))
    stop("Original qualify-A branch bytes differ")
  block
}

check_current_envelope <- function(h, cfg) {
  fields <- c("SNP", "mr_keep", "action", "remove", "ambiguous", "palindromic", "eligibility_reason",
              "F_exposure", "source_INFO", "frequency_difference", "eaf.exposure", "eaf.outcome")
  if (!all(fields %in% names(h)) || nrow(h) != 39L || anyNA(h[, fields]) || anyDuplicated(h$SNP) ||
      any(!nzchar(h$SNP)) || !identical(cfg$palindromic_EAF_excluded_interval, c(.42, .58)) ||
      cfg$palindromic_frequency_difference_max != .1 || cfg$M_source_INFO_min != .8 || cfg$F_reference_min != 10)
    stop("Exact current 39-IV configuration envelope required")
  numeric <- c("F_exposure", "source_INFO", "frequency_difference", "eaf.exposure", "eaf.outcome")
  if (any(!vapply(h[numeric], is.numeric, logical(1))) || any(!is.finite(as.matrix(h[numeric]))) ||
      any(!h$mr_keep | h$action != 2 | h$remove | h$ambiguous | h$eligibility_reason != "QUALIFIED") ||
      any(h$F_exposure < cfg$F_reference_min | h$source_INFO < cfg$M_source_INFO_min | h$source_INFO > 1) ||
      any(h$eaf.exposure < 0 | h$eaf.exposure > 1 | h$eaf.outcome < 0 | h$eaf.outcome > 1) ||
      any(h$palindromic & (h$frequency_difference > cfg$palindromic_frequency_difference_max |
        (h$eaf.exposure >= .42 & h$eaf.exposure <= .58) | (h$eaf.outcome >= .42 & h$eaf.outcome <= .58))))
    stop("Frozen branch output violates current EAF/INFO/F envelope; no automatic reselection is permitted")
  invisible(TRUE)
}

run_official_harmonisation <- function(inputs, paths) {
  options(stringsAsFactors = FALSE, warn = 1)
  Sys.setenv(OMP_NUM_THREADS = 1, OPENBLAS_NUM_THREADS = 1, MKL_NUM_THREADS = 1)
  set.seed(432202610)
  sha <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)
  input_sha <- unname(vapply(inputs, sha, ""))
  check_frozen_inputs(input_sha)
  description <- packageDescription("TwoSampleMR")
  description_sha <- sha(system.file("DESCRIPTION", package = "TwoSampleMR"))
  stopifnot(as.character(getRversion()) == "4.6.1", as.character(packageVersion("TwoSampleMR")) == "0.7.11",
            identical(description_sha, "911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531"),
            is.null(description$RemoteSha), is.null(description$GithubSHA1))
  package_identity <- namespace_function_identity()
  check_namespace_identity(package_identity)
  cfg <- jsonlite::read_json(inputs[3], simplifyVector = TRUE)
  cert <- jsonlite::read_json(inputs[4], simplifyVector = TRUE)
  lock <- read.delim(inputs[5], check.names = FALSE)
  stopifnot(identical(cfg$status, "LOCKED"), identical(cfg$version, "4.3.2"),
            identical(cfg$analysis_id, "G0_V432_A_X01_M06"), identical(cfg$enabled_edge, "A_X01_M06"),
            identical(cfg$exposure_role, "LEGACY_EXPLORATORY"), identical(cfg$overlap_class, "O2"),
            identical(cfg$primary_p_source, "NA"), cfg$harmonise_action == 2, cfg$n_independent_IV == 39,
            cfg$seed == 432202610, identical(cfg$scientific_code_sha256, input_sha[6]),
            identical(cert$status, "G0_V432_MINIMUM_COMPLETE"), isTRUE(cert$A$allowed),
            identical(cert$A$confirmatory_allowed, FALSE), identical(cert$A$role, "LEGACY_EXPLORATORY_O2_PRIMARY_NA"),
            identical(lock$version[lock$package == "TwoSampleMR"], "0.7.11"))
  block <- extract_qualify_a(readChar(inputs[6], nchars = file.info(inputs[6])$size, useBytes = TRUE))
  output_level <- sink.number()
  message_level <- sink.number(type = "message")
  logfile <- file(paths[5], open = "wt")
  on.exit({
    try(if (sink.number(type = "message") != message_level) sink(type = "message"), silent = TRUE)
    try(while (sink.number() > output_level) sink(), silent = TRUE)
    try(close(logfile), silent = TRUE)
  }, add = TRUE)
  sink(logfile, split = TRUE)
  sink(logfile, type = "message")
  read_tsv <- function(name) {
    position <- match(name, c("A_LD_CLUMPED_INSTRUMENTS.tsv", "A_OUTCOME_MATCHES.tsv"))
    if (is.na(position)) stop("Undeclared frozen branch input")
    read.delim(inputs[position], check.names = FALSE, colClasses = "character")
  }
  write_tsv <- function(x, name) {
    position <- match(name, OUTPUT_NAMES[1:2])
    if (is.na(position)) stop("Undeclared frozen branch table output")
    write.table(x, paths[position], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  }
  write_json <- function(x, name) {
    if (!identical(name, OUTPUT_NAMES[3])) stop("Undeclared frozen branch JSON output")
    jsonlite::write_json(x, paths[3], pretty = TRUE, auto_unbox = TRUE, na = "null", null = "null")
  }
  environment <- environment()
  eval(parse(text = block, keep.source = FALSE), envir = environment)
  check_current_envelope(environment$h, cfg)
  expected <- c("9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa",
                "9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa",
                "b0ec0e08840d3c77ea636a37b5b893af6051fcea7692c13de70b4c110b5960e7")
  stopifnot(identical(unname(vapply(paths[1:3], sha, "")), expected),
            identical(unname(vapply(inputs, sha, "")), input_sha))
  script_path <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])
  jsonlite::write_json(list(scope = "FROZEN_39_IV_LEGACY_HARMONISATION_ONLY_NOT_RAW_QC_PLINK_MR_OR_G0",
    input_sha256 = input_sha, input_bytes = unname(file.info(inputs)$size), adapter_sha256 = sha(script_path),
    original_scientific_code_sha256 = input_sha[6], qualify_A_block_sha256 = QUALIFY_BLOCK_SHA,
    original_qualify_A_branch_evaluated = TRUE, R = as.character(getRversion()), TwoSampleMR = "0.7.11",
    TwoSampleMR_RemoteSha = description$RemoteSha, package_description_sha256 = description_sha,
    package_namespace_function_count = package_identity$function_count,
    package_namespace_aggregate_sha256 = package_identity$aggregate_sha256,
    source_commit_supported_by_frozen_host_identity = "d4df21929fdabeb2f89686ffaad0db5f56973d64",
    package_identity_proof_session = "4f717274ece54f4396b8097b4db0ad8a",
    package_identity_proof_manifest_sha256 = "bf9ce79a277c51193bb7a8af3be6ca7c9231f14567d9e7f1d0fbcc7016364f48",
    output_sha256 = expected, n_clumped = 39L, n_qualified = 39L, seed = 432202610L,
    additional_config_envelope_checked_without_reselection = TRUE, raw_GWAS_QC_reexecuted = FALSE,
    PLINK_or_LD_reexecuted = FALSE, MR_estimates_computed = FALSE, original_full_project_verifier_executed = FALSE,
    scientific_authorization_granted = FALSE, formal_scientific_pass_granted = FALSE, G0 = FALSE),
    paths[4], pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 17)
  sink(type = "message")
  sink()
  close(logfile)
}

execute_harmonisation <- function() {
  input_values <- Sys.getenv(paste0("AUTONOMICS_INPUT", 0:5), unset = "")
  output_values <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:4), unset = "")
  if (any(!nzchar(c(input_values, output_values)))) stop("All declared input and output paths required")
  inputs <- unname(normalizePath(input_values, mustWork = TRUE))
  parents <- unname(normalizePath(dirname(output_values), mustWork = TRUE))
  if (any(!dir.exists(parents))) stop("Existing output parent directories required")
  paths <- unname(file.path(parents, basename(output_values)))
  if (anyDuplicated(paths) || any(paths %in% inputs)) stop("All output paths must be distinct from each other and inputs")
  links <- Sys.readlink(paths)
  if (any(file.exists(paths)) || any(!is.na(links) & nzchar(links))) stop("Refusing to overwrite existing or linked outputs")
  stat_program <- Sys.which("stat")
  if (!nzchar(stat_program)) stop("File ownership inspection requires stat")
  identity <- function(filename, directory = FALSE) {
    value <- suppressWarnings(system2(stat_program,
      c("-c", "%d:%i:%F", "--", shQuote(filename)), env = "LC_ALL=C", stdout = TRUE, stderr = TRUE))
    if (!is.null(attr(value, "status")) || length(value) != 1 ||
        !grepl(paste0("^[0-9]+:[0-9]+:", if (directory) "directory" else "regular( empty)? file", "$"), value))
      stop("Ordinary file or directory ownership cannot be proven")
    paste(strsplit(value, ":", fixed = TRUE)[[1]][1:2], collapse = ":")
  }
  before_identity <- unname(vapply(inputs, identity, ""))
  hash <- function(filename) digest::digest(file = filename, algo = "sha256", serialize = FALSE)
  verify_publication <- function(record) {
    first <- identity(record$path)
    content <- hash(record$path)
    last <- identity(record$path)
    if (!identical(first, record$identity) || !identical(last, record$identity) ||
        !identical(content, record$sha256)) stop("Published file no longer has its owned identity and content")
  }
  before <- unname(vapply(inputs, hash, ""))
  directories <- character()
  directory_identities <- character()
  published <- list()
  complete <- FALSE
  on.exit({
    if (!complete) {
      for (record in rev(published)) {
        current <- tryCatch(identity(record$path), error = function(error) NA_character_)
        current_hash <- tryCatch(hash(record$path), error = function(error) NA_character_)
        repeated <- tryCatch(identity(record$path), error = function(error) NA_character_)
        if (identical(current, record$identity) && identical(repeated, record$identity) && identical(current_hash, record$sha256)) {
          if (unlink(record$path) != 0) cat("BLOCKED: owned result rollback failed\n", file = stderr())
        } else cat("BLOCKED: foreign or modified result preserved during rollback\n", file = stderr())
      }
    }
    for (directory in directories) {
      current <- tryCatch(identity(directory, TRUE), error = function(error) NA_character_)
      if (identical(current, directory_identities[[directory]])) unlink(directory, recursive = TRUE)
      else cat("BLOCKED: replaced staging directory preserved during cleanup\n", file = stderr())
    }
  }, add = TRUE)
  staged <- vapply(seq_along(paths), function(position) {
    directory <- tempfile(".frozen-a-harmonisation-stage-", tmpdir = parents[position])
    if (!dir.create(directory, mode = "0700")) stop("Cannot create owned staging directory")
    directory_identities[[directory]] <<- identity(directory, TRUE)
    directories <<- c(directories, directory)
    file.path(directory, basename(paths[position]))
  }, "")
  connection <- file(staged[5], open = "wx")
  close(connection)
  initial_log <- list(path = paths[5], identity = identity(staged[5]), sha256 = hash(staged[5]))
  if (!isTRUE(suppressWarnings(file.link(staged[5], paths[5])))) stop("Fresh log publication refused")
  verify_publication(initial_log)
  tryCatch({
    run_official_harmonisation(inputs, staged)
    if (!identical(before, unname(vapply(inputs, hash, ""))) ||
        !identical(before_identity, unname(vapply(inputs, identity, "")))) stop("Input changed during official harmonisation")
    final_log <- list(path = paths[5], identity = identity(staged[5]), sha256 = hash(staged[5]))
    verify_publication(final_log)
    for (position in 1:4) {
      own_identity <- identity(staged[position])
      own_hash <- hash(staged[position])
      if (!isTRUE(suppressWarnings(file.link(staged[position], paths[position])))) stop("Fresh result publication refused")
      published[[length(published) + 1]] <- list(path = paths[position], identity = own_identity, sha256 = own_hash)
      verify_publication(published[[length(published)]])
    }
    invisible(lapply(c(list(final_log), published), verify_publication))
    complete <- TRUE
  }, error = function(error) {
    log_identity <- tryCatch(identity(staged[5]), error = function(error) NA_character_)
    if (identical(log_identity, initial_log$identity)) cat("BLOCKED:", conditionMessage(error), "\n", file = staged[5], append = TRUE)
    else cat("BLOCKED: replaced staged log preserved without append\n", file = stderr())
    stop(error)
  })
}

if (sys.nframe() == 0L) tryCatch(execute_harmonisation(), error = function(error) {
  cat("BLOCKED:", conditionMessage(error), "\n", file = stderr())
  quit(save = "no", status = 2)
})
