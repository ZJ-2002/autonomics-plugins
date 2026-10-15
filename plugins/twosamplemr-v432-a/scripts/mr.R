# Narrow numerical adapter for the frozen v4.3.2 run-A sequence.
# It consumes already qualified IVs and does not grant scientific admission.
run_frozen_a <- function(inputs, paths) {
options(stringsAsFactors = FALSE, warn = 1)
Sys.setenv(OMP_NUM_THREADS = 1, OPENBLAS_NUM_THREADS = 1, MKL_NUM_THREADS = 1)
stopifnot(as.character(getRversion()) == "4.6.1",
          as.character(packageVersion("TwoSampleMR")) == "0.7.11",
          TwoSampleMR::default_parameters()$nboot == 1000)
sha <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)
input_sha <- unname(vapply(inputs, sha, ""))
cfg <- jsonlite::read_json(inputs[2], simplifyVector = TRUE)
cert <- jsonlite::read_json(inputs[3], simplifyVector = TRUE)
lock <- read.delim(inputs[4], check.names = FALSE)
proof <- jsonlite::read_json(inputs[5], simplifyVector = TRUE)
scientific_code_sha <- "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd"
stopifnot(identical(unname(input_sha[1:4]), unname(proof$input_sha256)),
          identical(proof$scientific_code_sha256, scientific_code_sha),
          identical(proof$R, "4.6.1"), identical(proof$TwoSampleMR, "0.7.11"),
          identical(cfg$status, "LOCKED"), identical(cfg$version, "4.3.2"),
          identical(cfg$analysis_id, "G0_V432_A_X01_M06"),
          identical(cfg$enabled_edge, "A_X01_M06"),
          identical(cfg$scientific_code_sha256, scientific_code_sha),
          identical(cfg$exposure_role, "LEGACY_EXPLORATORY"),
          identical(cfg$overlap_class, "O2"), identical(cfg$primary_p_source, "NA"),
          identical(cfg$ordinary_ivw_parallel, "EXPLORATORY_ONLY"),
          cfg$seed == 432202610, cfg$bootstrap_n == 1000, cfg$harmonise_action == 2,
          identical(cfg$methods, c("mr_ivw", "mr_egger_regression", "mr_weighted_median")),
          identical(cert$status, "G0_V432_MINIMUM_COMPLETE"),
          identical(cert$version, "4.3.2"), isTRUE(cert$A$allowed),
          identical(cert$A$analysis_id, cfg$analysis_id),
          identical(cert$A$role, "LEGACY_EXPLORATORY_O2_PRIMARY_NA"),
          identical(cert$A$confirmatory_allowed, FALSE),
          identical(lock$version[lock$package == "TwoSampleMR"], "0.7.11"),
          identical(cfg$program_sha256, input_sha[1]))
if (identical(proof$scope, "FROZEN_V432_A_LEGACY")) {
  frozen_sha <- c("9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa",
    "8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f",
    "aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2",
    "8aeaa7bb2b22b2c4ae9852dc65d32d4f81cb927d875ecdd135822f2f1c2b8a56")
  stopifnot(identical(unname(input_sha[1:4]), frozen_sha), cfg$n_independent_IV == 39)
} else if (identical(proof$scope, "SYNTHETIC_METHOD_TEST")) {
  stopifnot(identical(cfg$technical_scope, "SYNTHETIC_METHOD_TEST"),
            identical(cert$technical_scope, "SYNTHETIC_METHOD_TEST"),
            identical(proof$scientific_authorization_granted, FALSE),
            is.character(proof$generator_sha256),
            grepl("^[a-f0-9]{64}$", proof$generator_sha256),
            input_sha[1] != "9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa")
} else stop("Explicit frozen legacy or synthetic method-test proof scope required")
output_level <- sink.number()
message_level <- sink.number(type = "message")
logfile <- file(paths[8], open = "wt")
on.exit({
  try(if (sink.number(type = "message") != message_level) sink(type = "message"), silent = TRUE)
  try(while (sink.number() > output_level) sink(), silent = TRUE)
  try(close(logfile), silent = TRUE)
}, add = TRUE)
sink(logfile, split = TRUE)
sink(logfile, type = "message")
h <- read.delim(inputs[1], check.names = FALSE)
stopifnot(nrow(h) == cfg$n_independent_IV)
required <- c("SNP", "beta.exposure", "beta.outcome", "se.exposure", "se.outcome",
              "eaf.exposure", "eaf.outcome", "effect_allele.exposure", "other_allele.exposure",
              "effect_allele.outcome", "other_allele.outcome", "id.exposure", "id.outcome",
              "exposure", "outcome", "mr_keep", "action", "palindromic", "ambiguous",
              "remove", "source_INFO", "frequency_difference", "F_exposure", "chr37", "pos37",
              "eligibility_reason")
if (!all(required %in% names(h))) stop("Qualified dotted-column input schema required")
if (nrow(h) < 3 || anyDuplicated(h$SNP) || anyNA(h$SNP) || any(!nzchar(h$SNP)))
  stop("At least three unique qualified independent IVs required")
for (field in c("beta.exposure", "beta.outcome", "se.exposure", "se.outcome",
                "eaf.exposure", "eaf.outcome", "source_INFO", "frequency_difference",
                "F_exposure", "chr37", "pos37")) {
  if (!is.numeric(h[[field]]) || any(!is.finite(h[[field]]))) stop(paste("Invalid numeric column", field))
}
if (any(h$se.exposure <= 0 | h$se.outcome <= 0) ||
    any(h$eaf.exposure < 0 | h$eaf.exposure > 1 | h$eaf.outcome < 0 | h$eaf.outcome > 1) ||
    anyNA(h[, c("mr_keep", "action", "palindromic", "ambiguous", "remove", "eligibility_reason")]) ||
    any(!h$mr_keep | h$action != 2 | h$ambiguous | h$remove | h$eligibility_reason != "QUALIFIED") ||
    any(h$source_INFO < .8 | h$source_INFO > 1 | h$F_exposure < 10) ||
    any(abs(h$F_exposure - (h$beta.exposure / h$se.exposure)^2) > 1e-8 * pmax(1, h$F_exposure)) ||
    any(abs(h$frequency_difference - abs(h$eaf.exposure - h$eaf.outcome)) > 1e-12) ||
    any(h$palindromic & (h$frequency_difference > .10 |
        (h$eaf.exposure >= .42 & h$eaf.exposure <= .58) |
        (h$eaf.outcome >= .42 & h$eaf.outcome <= .58))) ||
    any(h$chr37 != as.integer(h$chr37) | h$chr37 < 1 | h$chr37 > 22 |
        h$pos37 != floor(h$pos37) | h$pos37 < 1))
  stop("Input violates prequalified action=2 / EAF / INFO / F / GRCh37 contract")
if (!identical(unique(h$id.exposure), "GCST90652391") ||
    !identical(unique(h$id.outcome), "GCST90002393") ||
    !identical(unique(h$exposure), "X01_BMFF_residual_INT") ||
    !identical(unique(h$outcome), "M06_monocyte_transformed"))
  stop("Only the frozen X01 to M06 trait pair is supported")
cat("R:", as.character(getRversion()), "TwoSampleMR:", as.character(packageVersion("TwoSampleMR")), "\n")
cat("Prequalified IV count:", nrow(h), "; no clumping or re-harmonisation\n")
cat("Scope:", proof$scope, "\n")
cat("seed=432202610; bootstrap_n=1000; overlap=O2; LEGACY_EXPLORATORY; primary_p=NA; family_p=1\n")
methods <- c("mr_ivw", "mr_egger_regression", "mr_weighted_median")
# Same global RNG initialization and official call order as g0_v432_methods.R run-A.
set.seed(432202610)
ans <- TwoSampleMR::mr(h, method_list = methods)
ans$role <- "EXPLORATORY_OVERLAP_UNRESOLVED"
ans$p_primary <- NA
ans$p_for_family <- 1
ans$p_raw_exploratory <- ans$pval
heterogeneity <- TwoSampleMR::mr_heterogeneity(h, method_list = c("mr_ivw", "mr_egger_regression"))
intercept <- TwoSampleMR::mr_pleiotropy_test(h)
loo <- TwoSampleMR::mr_leaveoneout(h)
mhc <- h$chr37 == 6 & h$pos37 >= 25000000 & h$pos37 <= 34000000
tert <- h$chr37 == 5 & h$pos37 >= 1 & h$pos37 <= 2000000
sensitivities <- do.call(rbind, lapply(list(exclude_MHC = !mhc,
  exclude_TERT_vicinity = !tert, exclude_both = !(mhc | tert)), function(keep) {
  r <- TwoSampleMR::mr(h[keep, , drop = FALSE], method_list = methods)
  r$p_primary <- NA
  r$role <- "REGISTERED_SENSITIVITY_ONLY"
  r
}))
sensitivities$sensitivity <- rep(c("exclude_MHC", "exclude_TERT_vicinity", "exclude_both"),
                                each = length(methods))
tables <- list(ans, heterogeneity, intercept, loo, sensitivities, h)
for (i in seq_along(tables)) write.table(tables[[i]], paths[i], sep = "\t", quote = FALSE,
                                        row.names = FALSE, na = "NA")
saveRDS(list(harmonised = h, mr = ans, heterogeneity = heterogeneity,
             egger_intercept = intercept, leave_one_out = loo, regional_sensitivities = sensitivities,
             contract = list(R = "4.6.1", TwoSampleMR = "0.7.11", seed = 432202610L,
               bootstrap_n = 1000L, methods = methods, overlap = "O2", role = "LEGACY_EXPLORATORY",
               primary_p_source = "NA", scientific_authorization_granted = FALSE)), paths[7])
print(ans)
script_path <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])
jsonlite::write_json(list(scope = proof$scope, input_sha256 = input_sha,
  adapter_sha256 = sha(script_path), frozen_scientific_code_sha256 = scientific_code_sha,
  R = as.character(getRversion()), TwoSampleMR = as.character(packageVersion("TwoSampleMR")),
  method_function_sha256 = digest::digest(TwoSampleMR::mr_ivw, algo = "sha256"),
  package_description = unclass(packageDescription("TwoSampleMR")),
  package_description_sha256 = sha(system.file("DESCRIPTION", package = "TwoSampleMR")),
  dependency_lock_sha256 = input_sha[4], seed = 432202610L, bootstrap_n = 1000L,
  n_independent_IV = nrow(h), exposure_role = cfg$exposure_role,
  certificate_role = cert$A$role, overlap_class = cfg$overlap_class,
  primary_p_source = cfg$primary_p_source, scientific_authorization_granted = FALSE,
  formal_scientific_pass_granted = FALSE), paths[9], pretty = TRUE, auto_unbox = TRUE, digits = 17)
sink(type = "message")
sink()
close(logfile)
}

execute_frozen_a <- function() {
  input_values <- Sys.getenv(paste0("AUTONOMICS_INPUT", 0:4), unset = "")
  output_values <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:8), unset = "")
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
  invisible(vapply(inputs, identity, ""))
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
        if (identical(current, record$identity) && identical(repeated, record$identity) &&
            identical(current_hash, record$sha256)) {
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
    directory <- tempfile(".twosamplemr-v432-a-stage-", tmpdir = parents[position])
    if (!dir.create(directory, mode = "0700")) stop("Cannot create owned staging directory")
    directory_identities[[directory]] <<- identity(directory, TRUE)
    directories <<- c(directories, directory)
    file.path(directory, basename(paths[position]))
  }, "")
  connection <- file(staged[8], open = "wx")
  close(connection)
  initial_log <- list(path = paths[8], identity = identity(staged[8]), sha256 = hash(staged[8]))
  if (!isTRUE(suppressWarnings(file.link(staged[8], paths[8])))) stop("Fresh log publication refused")
  verify_publication(initial_log)
  tryCatch({
    run_frozen_a(inputs, staged)
    if (!identical(before, unname(vapply(inputs, hash, "")))) stop("Input changed during official MR calculation")
    final_log <- list(path = paths[8], identity = identity(staged[8]), sha256 = hash(staged[8]))
    verify_publication(final_log)
    for (position in c(1:7, 9)) {
      own_identity <- identity(staged[position])
      own_hash <- hash(staged[position])
      if (!isTRUE(suppressWarnings(file.link(staged[position], paths[position])))) stop("Fresh result publication refused")
      published[[length(published) + 1]] <- list(path = paths[position], identity = own_identity, sha256 = own_hash)
      verify_publication(published[[length(published)]])
    }
    invisible(lapply(c(list(final_log), published), verify_publication))
    complete <- TRUE
  }, error = function(error) {
    log_identity <- tryCatch(identity(staged[8]), error = function(error) NA_character_)
    if (identical(log_identity, initial_log$identity))
      cat("BLOCKED:", conditionMessage(error), "\n", file = staged[8], append = TRUE)
    else cat("BLOCKED: replaced staged log preserved without append\n", file = stderr())
    stop(error)
  })
}

tryCatch(execute_frozen_a(), error = function(error) {
  cat("BLOCKED:", conditionMessage(error), "\n", file = stderr())
  quit(save = "no", status = 2)
})
