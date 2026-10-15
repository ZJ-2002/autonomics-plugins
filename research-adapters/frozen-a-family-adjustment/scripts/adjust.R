options(digits = 17, width = 200)

FAMILY_COUNTS <- c(A_PRIMARY_EDGES = 88L, A_EXPANDED_EDGES = 188L,
                   A_PRIMARY_PATHS = 36L, A_EXPANDED_PATHS = 252L)
DEFINITION_SHA <- "2d110232f5f1c3097d763686df1ecec5212e3ca18b4b226ac8f5562c388813fd"
METHODS_SHA <- "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd"
PYTHON_SHA <- "2dd34cf6887e829334c2b3ba49f58be5c81b503333dc9183474208ebab49f08d"
SOURCE_NAMES <- c("01_REGISTRIES/GENETIC_EDGE_UNIVERSE.tsv", "01_REGISTRIES/GENETIC_PATH_UNIVERSE.tsv",
    "01_REGISTRIES/G0_LOCKED_HYPOTHESIS_UNIVERSE.tsv", "01_REGISTRIES/PRIMARY_P_DECISION_REGISTER.tsv",
    "01_REGISTRIES/FAMILY_LOCK_REGISTER.tsv", "01_REGISTRIES/MULTIPLICITY_REGISTER.tsv",
    "02_EXECUTION/EXECUTION_RULES_v4.3.2.json", "02_EXECUTION/execution_utils.py", "02_EXECUTION/g0_v432_methods.R")
SOURCE_BYTES <- c(58452L, 56329L, 11740332L, 21306L, 1907L, 6325L, 13853L, 5243L, 20329L)
SOURCE_SHA <- c("1952fd61e3404364b6bef12334e9743e97f418f80f16ffabd93b4b244473afb4",
    "bdb85f7ab874d2f2d913c75a2eeb60e56bc0b6049472eeb7f45c764b6eaaa1f2",
    "b8d7116aea0640f3677b72eb653b097c7ff2a7d4e7815819d9927b61790b782a",
    "92a49ae782060a6eb51fcc2d2bde65629f599714facbcb0ebefa53ea155f9f6a",
    "d7d1a89589fba8f8d115c0eefc9cfd4d270f2216181c70f9c528c4c1da9209c3",
    "b66a8b849068a695d65d90decad99229d8a10fe49213d4445d0dfe356f47fee6",
    "1ff187d5672c0448db193db4acb17ee78012ed2588f94bac580075b1cef2245b",
    PYTHON_SHA, METHODS_SHA)
INPUT_NAMES <- c("vectors.tsv", "assembly.tsv", "assembly-receipt.json", "g0_v432_methods.R")
OUTPUT_NAMES <- c("adjusted.tsv", "adjustment.RDS", "adjustment-receipt.json", "adjustment.log")

require_true <- function(value, message) {
  if (!isTRUE(value)) stop(message, call. = FALSE)
}

checksum <- function(path) {
  value <- suppressWarnings(system2("sha256sum", c("--", shQuote(path)), stdout = TRUE, stderr = TRUE))
  require_true(is.null(attr(value, "status")) && length(value) == 1L && grepl("^[0-9a-f]{64} ", value),
    "SHA256 identity unavailable")
  substr(value, 1L, 64L)
}

text_checksum <- function(text) {
  stage <- create_stage(tempdir(), "definition.R")
  on.exit(clean_stage(stage), add = TRUE)
  write_stage(stage, function(path) writeBin(charToRaw(text), path))
  checksum(stage$path)
}

exact_fields <- function(value, expected, label) {
  require_true(is.list(value) && !is.null(names(value)) && length(value) == length(expected) &&
    !anyDuplicated(names(value)) && setequal(names(value), expected), paste("Exact fields required:", label))
}

json_tree <- function(value) {
  if (is.list(value)) {
    require_true(is.null(names(value)) || !anyDuplicated(names(value)), "Duplicate JSON keys forbidden")
    invisible(lapply(value, json_tree))
  } else if (is.numeric(value)) {
    require_true(all(is.finite(value)), "Nonfinite JSON numbers forbidden")
  }
}

read_json <- function(path) {
  value <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  json_tree(value)
  value
}

integer_scalar <- function(value, expected) {
  is.numeric(value) && !is.logical(value) && length(value) == 1L && is.finite(value) && value == expected
}

string_vector <- function(value) {
  require_true(is.list(value) && is.null(names(value)) && all(vapply(value,
    function(item) is.character(item) && length(item) == 1L && !is.na(item), logical(1))), "JSON string array required")
  unlist(value, use.names = FALSE)
}

lexical_ids <- function(value) {
  require_true(is.character(value) && length(value) > 0L && !anyNA(value) &&
    all(grepl("^[A-Za-z0-9_.:+-]+$", value)) && !anyDuplicated(value), "Unique lexical IDs required")
}

read_table <- function(path, fields, rows) {
  widths <- count.fields(path, sep = "\t", quote = "", comment.char = "", blank.lines.skip = FALSE)
  require_true(length(widths) == rows + 1L && !anyNA(widths) && all(widths == length(fields)), "Complete rectangular TSV required")
  value <- read.delim(path, sep = "\t", quote = "", colClasses = "character", check.names = FALSE,
    comment.char = "", na.strings = NULL, blank.lines.skip = FALSE, fill = FALSE, stringsAsFactors = FALSE)
  require_true(identical(names(value), fields) && !anyDuplicated(names(value)) && nrow(value) == rows,
    "Exact TSV header and complete row count required")
  value
}

probabilities <- function(value) {
  require_true(is.character(value) && !anyNA(value) && all(nzchar(value)), "Explicit P or literal NA required")
  absent <- value == "NA"
  parsed <- suppressWarnings(as.numeric(value))
  require_true(all(is.finite(parsed[!absent])) && all(parsed[!absent] >= 0 & parsed[!absent] <= 1),
    "Finite probabilities in [0,1] or literal NA required")
  parsed[absent] <- NA_real_
  parsed
}

no_alias <- function(path) {
  require_true(is.character(path) && length(path) == 1L && nzchar(path) && startsWith(path, "/") &&
    !grepl("(^|/)([.]|[.][.])(/|$)|//|[\r\n\t]", path), "Absolute canonical paths required")
  parents <- path
  while (tail(parents, 1L) != "/") parents <- c(parents, dirname(tail(parents, 1L)))
  links <- Sys.readlink(parents)
  require_true(!any(!is.na(links) & nzchar(links)), "Symlink paths and ancestors forbidden")
}

file_identity <- function(path) {
  no_alias(path)
  observed <- suppressWarnings(system2("stat", c("--format=%d:%i:%f:%u:%g:%s:%y:%z", "--", shQuote(path)),
    stdout = TRUE, stderr = TRUE, env = "LC_ALL=C"))
  require_true(is.null(attr(observed, "status")) && length(observed) == 1L, "Ordinary file identity unavailable")
  fields <- strsplit(observed, ":", fixed = TRUE)[[1]]
  require_true(length(fields) >= 8L && bitwAnd(strtoi(fields[3], base = 16L), 61440L) == 32768L,
    "Ordinary non-symlink files required")
  observed
}

owned_fact <- function(path) {
  first <- file_identity(path)
  sha <- checksum(path)
  last <- file_identity(path)
  require_true(identical(first, last), "File identity changed during hashing")
  list(identity = strsplit(first, ":", fixed = TRUE)[[1]][1:6], sha256 = sha)
}

directory_fact <- function(path) {
  no_alias(path)
  observed <- suppressWarnings(system2("stat", c("--format=%d:%i:%f:%u:%g", "--", shQuote(path)),
    stdout = TRUE, stderr = TRUE, env = "LC_ALL=C"))
  require_true(is.null(attr(observed, "status")) && length(observed) == 1L,
    "Staging directory identity unavailable")
  fields <- strsplit(observed, ":", fixed = TRUE)[[1]]
  require_true(length(fields) == 5L && bitwAnd(strtoi(fields[3], base = 16L), 61440L) == 16384L,
    "Ordinary staging directory required")
  observed
}

create_stage <- function(parent, name) {
  no_alias(parent)
  stage <- new.env(parent = emptyenv())
  stage$directory <- tempfile(".a-family-adjust-", tmpdir = parent)
  require_true(dir.create(stage$directory, mode = "0700"), "Owned output staging directory unavailable")
  stage$identity <- directory_fact(stage$directory)
  stage$path <- file.path(stage$directory, name)
  stage$fact <- NULL
  stage
}

check_stage <- function(stage) {
  require_true(identical(directory_fact(stage$directory), stage$identity), "Staging directory identity changed")
}

write_stage <- function(stage, writer) {
  check_stage(stage)
  if (is.null(stage$fact)) {
    link <- Sys.readlink(stage$path)
    require_true(!file.exists(stage$path) && (is.na(link) || !nzchar(link)), "Fresh staged path required")
  } else {
    require_true(identical(owned_fact(stage$path), stage$fact), "Staged content changed before writing")
  }
  writer(stage$path)
  check_stage(stage)
  stage$fact <- owned_fact(stage$path)
  invisible(NULL)
}

clean_stage <- function(stage) {
  same_directory <- function() identical(tryCatch(directory_fact(stage$directory), error = function(error) NULL), stage$identity)
  if (!same_directory()) return(invisible(NULL))
  current <- tryCatch(owned_fact(stage$path), error = function(error) NULL)
  if (!is.null(stage$fact) && identical(current, stage$fact)) {
    if (!same_directory()) return(invisible(NULL))
    unlink(stage$path)
  }
  if (same_directory() && length(list.files(stage$directory, all.files = TRUE, no.. = TRUE)) == 0L) {
    suppressWarnings(system2("rmdir", c("--", shQuote(stage$directory)), stdout = FALSE, stderr = FALSE))
  }
  invisible(NULL)
}

check_assembly_receipt <- function(receipt, assembly, vectors, input_hashes) {
  fields <- c("schema", "scope", "scenario", "source_inputs", "family_counts", "family_ids", "output_sha256",
    "assembly_rows", "vector_rows", "vector_count", "raw_missing_preserved", "original_python_functions",
    "original_python_sha256", "request_sha256", "official_adjustment_performed", "MR_estimates_computed",
    "scientific_authorization_granted", "g0_granted")
  exact_fields(receipt, fields, "assembly receipt")
  require_true(identical(receipt$schema, "FROZEN_A_FAMILY_ASSEMBLY_RECEIPT_V1") &&
    ((identical(receipt$scope, "SYNTHETIC_NOT_RESEARCH") && receipt$scenario %in% c("BOUNDARY", "INTERIOR")) ||
     (identical(receipt$scope, "FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH") && identical(receipt$scenario, "REAL_FROZEN_NA_LEDGER"))),
    "Exact technical scope and scenario required")
  require_true(is.character(receipt$scenario) && length(receipt$scenario) == 1L &&
    integer_scalar(receipt$assembly_rows, 564) && integer_scalar(receipt$vector_rows, 840) &&
    integer_scalar(receipt$vector_count, 6) && identical(receipt$raw_missing_preserved, TRUE) &&
    identical(receipt$original_python_sha256, PYTHON_SHA) &&
    identical(string_vector(receipt$original_python_functions), c("primary_p", "strict_conjunction", "assert_locked_ids")) &&
    is.character(receipt$request_sha256) && length(receipt$request_sha256) == 1L &&
    grepl("^[0-9a-f]{64}$", receipt$request_sha256) &&
    all(vapply(receipt[c("official_adjustment_performed", "MR_estimates_computed", "scientific_authorization_granted", "g0_granted")],
      identical, logical(1), FALSE)), "Frozen source and false-authority receipt required")
  exact_fields(receipt$family_counts, names(FAMILY_COUNTS), "family counts")
  require_true(all(vapply(names(FAMILY_COUNTS), function(name) integer_scalar(receipt$family_counts[[name]],
    FAMILY_COUNTS[[name]]), logical(1))), "Frozen denominators cannot change")
  require_true(is.list(receipt$source_inputs) && is.null(names(receipt$source_inputs)) && length(receipt$source_inputs) == 9L,
    "All nine original source declarations required")
  for (index in seq_along(SOURCE_NAMES)) {
    item <- receipt$source_inputs[[index]]
    exact_fields(item, c("port", "name", "bytes", "sha256"), "source input")
    require_true(integer_scalar(item$port, index - 1L) && identical(item$name, SOURCE_NAMES[index]) &&
      integer_scalar(item$bytes, SOURCE_BYTES[index]) && identical(item$sha256, SOURCE_SHA[index]),
      "Frozen source declaration identity differs")
  }
  exact_fields(receipt$output_sha256, c("assembly.tsv", "vectors.tsv"), "assembly output hashes")
  require_true(identical(receipt$output_sha256[["assembly.tsv"]], input_hashes[["assembly.tsv"]]) &&
    identical(receipt$output_sha256[["vectors.tsv"]], input_hashes[["vectors.tsv"]]), "Assembly output hashes differ")
  exact_fields(receipt$family_ids, names(FAMILY_COUNTS), "ordered family identities")
  family_ids <- lapply(receipt$family_ids, string_vector)
  require_true(all(vapply(names(FAMILY_COUNTS), function(name) length(family_ids[[name]]) == FAMILY_COUNTS[[name]], logical(1))),
    "Complete frozen family members required")
  lexical_ids(unlist(family_ids, use.names = FALSE))
  lexical_ids(assembly$analysis_id)
  require_true(setequal(assembly$analysis_id, unlist(family_ids, use.names = FALSE)) &&
    all(assembly$scope == receipt$scope) && all(assembly$scenario == receipt$scenario) &&
    all(assembly$family_id %in% names(FAMILY_COUNTS)) && all(nzchar(assembly$primary_method)) && all(nzchar(assembly$reason)),
    "Complete assembly scope, scenario and identities required")
  for (family in names(FAMILY_COUNTS)) {
    require_true(identical(assembly$analysis_id[assembly$family_id == family], family_ids[[family]]),
      "Assembly family order differs from its declared frozen IDs")
  }
  raw <- probabilities(assembly$p_raw)
  if (receipt$scope == "FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH") {
    require_true(all(is.na(raw)), "Real frozen ledger transport cannot invent estimated P values")
  }
  vector_ids <- methods <- character()
  vector_members <- list()
  for (family in names(FAMILY_COUNTS)) {
    for (method in if (grepl("EDGES$", family)) c("BH", "BY") else "BY") {
      key <- paste(receipt$scope, receipt$scenario, family, method, sep = "/")
      vector_ids <- c(vector_ids, rep(key, FAMILY_COUNTS[[family]]))
      methods <- c(methods, rep(method, FAMILY_COUNTS[[family]]))
      vector_members[[key]] <- family_ids[[family]]
    }
  }
  require_true(identical(vectors$vector_id, vector_ids) && identical(vectors$method, methods),
    "Six complete vectors must retain their fixed family, method and row order")
  vector_raw <- probabilities(vectors$p_raw)
  for (key in names(vector_members)) {
    positions <- which(vectors$vector_id == key)
    ids <- vector_members[[key]]
    require_true(identical(vectors$analysis_id[positions], ids) &&
      identical(vector_raw[positions], raw[match(ids, assembly$analysis_id)]), "Vector raw P or ordered IDs differ from assembly")
  }
  list(scope = receipt$scope, scenario = receipt$scenario, members = vector_members, raw = vector_raw)
}

run_adjustment <- function(inputs, stages) {
  staged <- vapply(stages, function(stage) stage$path, character(1))
  require_true(as.character(getRversion()) == "4.6.1" && as.character(packageVersion("stats")) == "4.6.1",
    "Exact official R/stats 4.6.1 required")
  input_hashes <- as.list(setNames(vapply(inputs, checksum, character(1)), INPUT_NAMES))
  require_true(input_hashes[["g0_v432_methods.R"]] == METHODS_SHA, "Original scientific methods SHA differs")
  definition <- grep("^adjust_full <- function\\(", readLines(inputs[4], warn = FALSE), value = TRUE)
  require_true(length(definition) == 1L, "Exactly one frozen adjustment definition required")
  definition <- paste0(definition, "\n")
  require_true(text_checksum(definition) == DEFINITION_SHA, "Original adjustment function definition differs")
  official <- new.env(parent = asNamespace("stats"))
  eval(parse(text = definition), envir = official)
  require_true(is.function(official$adjust_full), "Original official adjustment helper unavailable")
  assembly <- read_table(inputs[2], c("analysis_id", "family_id", "scope", "scenario", "p_raw", "primary_method", "reason"), 564L)
  vectors <- read_table(inputs[1], c("vector_id", "analysis_id", "p_raw", "method"), 840L)
  receipt <- read_json(inputs[3])
  contract <- check_assembly_receipt(receipt, assembly, vectors, input_hashes)
  results <- list()
  adjusted <- vectors
  adjusted$q <- NA_character_
  for (key in names(contract$members)) {
    positions <- which(vectors$vector_id == key)
    raw <- contract$raw[positions]
    method <- unique(vectors$method[positions])
    require_true(length(method) == 1L, "One fixed method per complete vector required")
    value <- official$adjust_full(raw, method)
    require_true(length(value) == length(raw) && all(is.finite(value)) && all(value >= 0 & value <= 1),
      "Official adjusted vector must be complete and finite")
    adjusted$q[positions] <- sprintf("%.17g", value)
    results[[key]] <- list(analysis_id = vectors$analysis_id[positions], p_raw = raw,
      p_for_adjustment = ifelse(is.na(raw), 1, raw), q = value, method = method, n_total = length(raw))
  }
  write_stage(stages[[1]], function(path) write.table(adjusted, path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA"))
  write_stage(stages[[2]], function(path) saveRDS(list(vectors = results, input_sha256 = input_hashes, adjustment_definition = definition,
    R_version = "4.6.1", stats_version = "4.6.1"), path))
  result_receipt <- list(schema = "FROZEN_A_OFFICIAL_ADJUSTMENT_RECEIPT_V1", scope = contract$scope, scenario = contract$scenario,
    input_sha256 = input_hashes, output_sha256 = as.list(setNames(vapply(staged[1:2], checksum, character(1)), OUTPUT_NAMES[1:2])),
    R_version = "4.6.1", stats_version = "4.6.1", adjustment_definition_sha256 = DEFINITION_SHA,
    vector_count = 6L, rows = 840L, family_counts = as.list(FAMILY_COUNTS), official_function = "stats::p.adjust",
    invocation = "adjust_full(p, method)", missing_for_adjustment = 1L, MR_estimates_computed = FALSE,
    scientific_authorization_granted = FALSE, g0_granted = FALSE)
  write_stage(stages[[3]], function(path) jsonlite::write_json(result_receipt, path, auto_unbox = TRUE, pretty = TRUE, na = "null", null = "null"))
  require_true(identical(input_hashes, as.list(setNames(vapply(inputs, checksum, character(1)), INPUT_NAMES))),
    "Input bytes changed during official adjustment")
  write_stage(stages[[4]], function(path) cat("Official R/stats 4.6.1; six complete vectors; 840 rows; no MR or scientific authorization\n", file = path, append = TRUE))
}

execute <- function() {
  inputs <- vapply(0:3, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), character(1))
  outputs <- vapply(0:3, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), character(1))
  invisible(lapply(c(inputs, outputs), no_alias))
  require_true(!anyDuplicated(c(inputs, outputs)), "All input and output paths must be distinct")
  input_facts <- lapply(inputs, owned_fact)
  input_timestamps <- vapply(inputs, file_identity, character(1))
  require_true(all(file.info(inputs)$size > 0 & file.info(inputs)$size <= 8 * 1024^2), "Bounded nonempty input files required")
  require_true(all(dir.exists(dirname(outputs))) && !any(file.exists(outputs)), "Output parents must exist and outputs must be absent")
  stages <- list()
  on.exit(invisible(lapply(stages, clean_stage)), add = TRUE)
  for (index in seq_along(outputs)) stages[[index]] <- create_stage(dirname(outputs[index]), OUTPUT_NAMES[index])
  staged <- vapply(stages, function(stage) stage$path, character(1))
  write_stage(stages[[4]], function(path) writeLines("Frozen A family adjustment; technical execution only", path))
  published <- list()
  rollback <- function() {
    for (record in rev(published)) {
      current <- tryCatch(owned_fact(record$path), error = function(error) NULL)
      if (identical(current, record$fact)) unlink(record$path)
    }
  }
  publish <- function(index, expected) {
    check_stage(stages[[index]])
    require_true(identical(owned_fact(staged[index]), expected), "Staged output changed before publication")
    require_true(isTRUE(suppressWarnings(file.link(staged[index], outputs[index]))), "Fresh no-clobber publication refused")
    published[[length(published) + 1L]] <<- list(path = outputs[index], fact = expected)
    require_true(identical(owned_fact(outputs[index]), expected), "Published output identity or content differs")
  }
  tryCatch({
    run_adjustment(inputs, stages)
    require_true(identical(lapply(inputs, owned_fact), input_facts) &&
      identical(vapply(inputs, file_identity, character(1)), input_timestamps), "Input identity changed during execution")
    facts <- lapply(stages, function(stage) {
      check_stage(stage)
      require_true(!is.null(stage$fact) && identical(owned_fact(stage$path), stage$fact),
        "Completed staged output differs from its recorded identity or content")
      stage$fact
    })
    for (index in seq_along(staged)) publish(index, facts[[index]])
    for (record in published) require_true(identical(owned_fact(record$path), record$fact), "Final output identity or content differs")
    0L
  }, error = function(error) {
    rollback()
    logged <- tryCatch({
      write_stage(stages[[4]], function(path) cat("BLOCKED: ", conditionMessage(error), "\n", file = path, append = TRUE, sep = ""))
      publish(4L, stages[[4]]$fact)
      TRUE
    }, error = function(log_error) FALSE)
    if (!logged) tryCatch(publish_preflight_log(conditionMessage(error)), error = function(log_error) NULL)
    message("BLOCKED: ", conditionMessage(error))
    2L
  })
}

publish_preflight_log <- function(message) {
  path <- Sys.getenv("AUTONOMICS_OUTPUT3")
  no_alias(path)
  other <- c(vapply(0:3, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), character(1)),
    vapply(0:2, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), character(1)))
  require_true(!path %in% other && dir.exists(dirname(path)) && !file.exists(path),
    "Failure log must have its own absent output path and ordinary parent")
  stage <- create_stage(dirname(path), "adjustment.log")
  on.exit(clean_stage(stage), add = TRUE)
  write_stage(stage, function(staged) writeLines(paste0("BLOCKED: ", message), staged))
  expected <- stage$fact
  check_stage(stage)
  require_true(isTRUE(suppressWarnings(file.link(stage$path, path))), "Failure log no-clobber publication refused")
  require_true(identical(owned_fact(path), expected), "Failure log identity or content changed")
}

status <- tryCatch(execute(), error = function(error) {
  tryCatch(publish_preflight_log(conditionMessage(error)), error = function(log_error) NULL)
  message("BLOCKED: ", conditionMessage(error))
  2L
})
quit(save = "no", status = status)
