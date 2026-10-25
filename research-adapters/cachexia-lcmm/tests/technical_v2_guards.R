arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 1L)
source_path <- normalizePath(arguments[[1]], mustWork = TRUE)
body <- parse(source_path)[[1]][[3]][[3]]
definitions <- c("CONTRACT_VERSION", "ROLE", "require_value", "exact", "text", "strings", "number", "validate_request", "technical_provenance", "lineage_entry", "validate_bundle", "validate_receipt")
load_guards <- function(version) {
  previous <- Sys.getenv("AUTONOMICS_TECHNICAL_CONTRACT_VERSION", unset = NA_character_)
  on.exit(if (is.na(previous)) Sys.unsetenv("AUTONOMICS_TECHNICAL_CONTRACT_VERSION") else Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = previous))
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = version)
  environment <- new.env(parent = globalenv())
  for (statement in as.list(body)[-1]) {
    if (is.call(statement) && identical(statement[[1]], as.name("<-")) && is.symbol(statement[[2]]) && as.character(statement[[2]]) %in% definitions) eval(statement, environment)
  }
  stopifnot(all(definitions %in% ls(environment)))
  environment
}
request <- function(environment, role = "EMPIRICAL_TECHNICAL_INPUT") list(schema_version = if (environment$CONTRACT_VERSION == "2") 2L else 1L,
  mode = "fit", scope = "TECHNICAL_ONLY_NOT_G0", input_role = role,
  scientific_qualification = "NOT_GRANTED", analysis_role = environment$ROLE, test_id = "technical-only-toy-input",
  input0_sha256 = paste(rep("a", 64), collapse = ""), input2_sha256 = paste(rep("b", 64), collapse = ""),
  expected_row_ids = list("r1", "r2"), max_input_bytes = 10000L, max_rows = 2L, params = list())
reject <- function(command) stopifnot(inherits(tryCatch({force(command); NULL}, error = identity), "error"))
first <- load_guards("1")
second <- load_guards("2")
synthetic <- request(first, "SYNTHETIC_TECHNICAL_INPUT")
empirical <- request(second)
first$validate_request(synthetic, "fit")
second$validate_request(empirical, "fit")
second$validate_request(request(second, "SYNTHETIC_TECHNICAL_INPUT"), "fit")
cat("PASS 1 accepted roles are explicit and versioned\n")
reject(first$validate_request(empirical, "fit"))
reject(second$validate_request(synthetic, "fit"))
reject(load_guards("3")$validate_request(empirical, "fit"))
cat("PASS 2 version crossover and unknown version rejected\n")
for (field in c("scope", "input_role", "scientific_qualification", "analysis_role")) {
  modified <- empirical
  modified[[field]] <- "G0_PASS"
  reject(second$validate_request(modified, "fit"))
}
cat("PASS 3 no scientific permission or unknown role admitted\n")
original <- list(mode = "fit", input0_sha256 = "original", nested = list(value = pi))
stopifnot(identical(first$technical_provenance(original, synthetic), original))
stopifnot(identical(first$lineage_entry("fit", synthetic), list(mode = "fit", input0_sha256 = synthetic$input0_sha256, input2_sha256 = synthetic$input2_sha256)))
cat("PASS 4 version1 metadata byte semantics preserved\n")
receipt <- list(schema_version = 2L, analysis_role = second$ROLE, source_sha256 = empirical$input0_sha256,
  row_ids = empirical$expected_row_ids, eligibility = "COMPLETE_OBSERVATIONS_NOT_RESEARCH_PERMISSION",
  input_role = empirical$input_role, scope = empirical$scope, scientific_qualification = "NOT_GRANTED")
second$validate_receipt(receipt, empirical, c("r1", "r2"))
for (field in c("input_role", "eligibility", "scope", "scientific_qualification", "source_sha256")) {
  modified <- receipt
  modified[[field]] <- "INVALID"
  reject(second$validate_receipt(modified, empirical, c("r1", "r2")))
}
reject(second$validate_receipt(receipt, empirical, c("r2", "r1")))
cat("PASS 5 complete-observation receipt preserves source role and row axis\n")
legacy_receipt <- list(schema_version = 1L, analysis_role = first$ROLE, source_sha256 = synthetic$input0_sha256,
  row_ids = synthetic$expected_row_ids, eligibility = "SYNTHETIC_COMPLETE_OBSERVATIONS_NOT_RESEARCH_PERMISSION")
first$validate_receipt(legacy_receipt, synthetic, c("r1", "r2"))
reject(second$validate_receipt(legacy_receipt, empirical, c("r1", "r2")))
cat("PASS 6 legacy receipt cannot become empirical qualification\n")
fit <- structure(list(conv = 1L, best = pi, V = pi), class = "hlme")
bundle <- second$technical_provenance(list(mode = "fit", scope = empirical$scope, analysis_role = second$ROLE,
  fit = fit, source_sha256 = empirical$input0_sha256, data = data.frame(row_id = c("r1", "r2")),
  row_ids = c("r1", "r2"), request = empirical, lineage = list(second$lineage_entry("fit", empirical))), empirical)
stopifnot(identical(second$validate_bundle(bundle, empirical), bundle))
modified <- empirical
modified$input_role <- "SYNTHETIC_TECHNICAL_INPUT"
reject(second$validate_bundle(bundle, modified))
reject(first$validate_bundle(bundle, synthetic))
cat("PASS 7 downstream state role and version must agree\n")
modified <- bundle
modified$input_role <- "SYNTHETIC_TECHNICAL_INPUT"
modified$request$input_role <- "SYNTHETIC_TECHNICAL_INPUT"
toy_request <- request(second, "SYNTHETIC_TECHNICAL_INPUT")
reject(second$validate_bundle(modified, toy_request))
modified <- bundle
modified$lineage[[1]]$schema_version <- 1L
reject(second$validate_bundle(modified, empirical))
cat("PASS 8 lineage cannot silently relabel empirical data\n")
local({
  directory <- tempfile("lcmm-v2-guard-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE))
  saveRDS(bundle, file.path(directory, "state.rds"), version = 3)
  restored <- readRDS(file.path(directory, "state.rds"))
  stopifnot(identical(restored, bundle), identical(restored$fit, fit), identical(restored$input_role, "EMPIRICAL_TECHNICAL_INPUT"))
})
cat("PASS 9 complete RDS and empirical provenance roundtrip unchanged\n")
stopifnot(identical(second$lineage_entry("predict", empirical)$input_role, "EMPIRICAL_TECHNICAL_INPUT"))
reject(second$validate_request(within(empirical, expected_row_ids <- list("r1", "r1")), "fit"))
cat("PASS 10 row and lineage guards do not execute any author model\n")
