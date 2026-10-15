run_a_block <- function(text) {
  begin <- '} else if(mode=="run-A") {\n'
  end <- '\n} else if(mode=="run-B") {'
  occurrences <- function(marker) {
    positions <- gregexpr(marker, text, fixed=TRUE)[[1L]]
    if (identical(positions[[1L]], -1L)) 0L else length(positions)
  }
  if (occurrences(begin) != 1L || occurrences(end) != 1L) stop("Unique original run-A branch required")
  start <- regexpr(begin, text, fixed=TRUE)[[1L]]
  finish <- regexpr(end, text, fixed=TRUE)[[1L]]
  if (finish <= start) stop("Original branch markers are out of order")
  result <- substr(text, start + nchar(begin, type="chars"), finish - 1L)
  expected <- "0fe5cac9fff04351897ef3eca682ecb212e144b6e52604bc827ed141805bdc34"
  observed <- digest::digest(charToRaw(result), algo="sha256", serialize=FALSE)
  if (!identical(observed, expected)) stop("Exact original run-A branch required")
  result
}

complete_official_object <- function(actual, expected, location="root") {
  if (!identical(typeof(actual), typeof(expected))) stop(paste("Object type differs:", location))
  if (!identical(attributes(actual), attributes(expected))) stop(paste("Object attributes differ:", location))
  if (is.list(actual)) {
    if (length(actual) != length(expected)) stop(paste("Object length differs:", location))
    for (position in seq_along(actual)) {
      complete_official_object(actual[[position]], expected[[position]], paste0(location, "[[", position, "]]"))
    }
  } else if (!identical(actual, expected)) stop(paste("Complete official object differs:", location))
  invisible(TRUE)
}

sha256 <- function(path) digest::digest(file=path, algo="sha256", serialize=FALSE)
file_fact <- function(path) list(bytes=unname(file.info(path)$size), sha256=sha256(path))
write_json <- function(value, path) jsonlite::write_json(value, path, auto_unbox=TRUE, pretty=TRUE,
  digits=17, na="null", null="null")

original_statements <- function(block) {
  parsed <- parse(text=paste0("{\n", block, "\n}"), keep.source=FALSE)[[1L]]
  statements <- as.list(parsed)[-1L]
  relocated <- parse(text='checked<-system2("python",c(shQuote(file.path(root,"02_EXECUTION/verify_g0_v432.py")),"--quiet"));stopifnot(checked==0)', keep.source=FALSE)
  excluded <- which(vapply(statements, function(statement) any(vapply(as.list(relocated),
    function(expected) identical(statement, expected), logical(1))), logical(1)))
  if (!identical(excluded, c(4L, 5L))) stop("Exact two original whole-project verifier statements required")
  retained <- statements[-excluded]
  first_scientific <- which(vapply(retained, function(statement) identical(statement,
    quote(h<-read.delim(file.path(out,"A_FROZEN_EXPLORATORY_INPUT.tsv"),check.names=FALSE))), logical(1)))
  if (length(first_scientific) != 1L) stop("Unique original scientific entry required")
  list(original=statements, retained=retained, excluded=excluded,
    scientific=retained[seq.int(first_scientific, length(retained))],
    envelope=list(
      relocated_to_actual_outer_process=c('checked<-system2("python",c(shQuote(file.path(root,"02_EXECUTION/verify_g0_v432.py")),"--quiet"))',
        'stopifnot(checked==0)'),
      unchanged_statements_with_private_path_bindings=c("cfg read", "cert read", "original cfg/cert stopifnot",
        "dest assignment", "existing dest refusal", "dest creation", "all remaining run-A statements"),
      reference_only_instrumentation="write.table captures its evaluated object, then delegates unchanged arguments to utils::write.table",
      original_preamble_reused="options(stringsAsFactors=FALSE,warn=1); thread environment; set.seed(432202610)",
      original_library_path_injection_executed=FALSE))
}

main <- function() {
  stopifnot(as.character(getRversion()) == "4.6.1",
    as.character(packageVersion("TwoSampleMR")) == "0.7.11",
    TwoSampleMR::default_parameters()$nboot == 1000)
  options(stringsAsFactors=FALSE, warn=1)
  Sys.umask("0077")
  source("/source/namespace-identity.R", local=environment())
  identity <- namespace_function_identity()
  stopifnot(identity$function_count == 171L,
    identity$aggregate_sha256 == "127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73",
    sha256(system.file("DESCRIPTION", package="TwoSampleMR")) == "911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531",
    is.null(packageDescription("TwoSampleMR")$RemoteSha))
  method_path <- "/source/g0_v432_methods.R"
  method_sha <- "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd"
  stopifnot(sha256(method_path) == method_sha)
  text <- paste(readLines(method_path, warn=FALSE), collapse="\n")
  block <- run_a_block(text)
  program <- original_statements(block)
  writeLines(block, "/proof/original-run-A-branch.R", useBytes=TRUE)
  writeLines(vapply(program$scientific, function(statement) paste(deparse(statement, width.cutoff=500L),
    collapse="\n"), character(1)), "/proof/original-run-A-scientific-AST.R")
  write_json(program$envelope, "/proof/reference-envelope.json")
  reference_root <- "/proof/reference-root"
  reference_audit <- file.path(reference_root, "03_AUDIT/G0_v4.3.2_2026-10-11")
  stopifnot(!file.exists(reference_root), dir.create(reference_audit, recursive=TRUE, mode="0700"))
  input_names <- c("A_FROZEN_EXPLORATORY_INPUT.tsv", "A_ANALYSIS_CONFIG.json", "G0_V432_CERTIFICATE.json", "R_DEPENDENCY_LOCK.tsv")
  for (position in seq_along(input_names)) {
    stopifnot(file.copy(paste0("/inputs/input", position - 1L), file.path(reference_audit, input_names[[position]]), overwrite=FALSE))
  }
  inputs <- paste0("/inputs/input", 0:4)
  input_sha <- unname(vapply(inputs, sha256, character(1)))
  expected_inputs <- c("9d2b7c1e7ab66b3825b1563874d98fbf2a2bc341ab0a6948537f8ee81846a2fa",
    "8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f",
    "aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2",
    "8aeaa7bb2b22b2c4ae9852dc65d32d4f81cb927d875ecdd135822f2f1c2b8a56",
    "a79c4469321bcef7ffabb9f94ad557ca185409bd9177868a3c158d8debb484c2")
  stopifnot(identical(input_sha, expected_inputs))
  captured <- list()
  scope <- new.env(parent=globalenv())
  scope$root <- reference_root
  scope$out <- reference_audit
  scope$write.table <- function(x, file, ...) {
    filename <- basename(file)
    if (filename %in% names(captured)) stop("Duplicate original table writer call")
    captured[[filename]] <<- x
    utils::write.table(x, file, ...)
  }
  reference_log <- file("/proof/original-official-messages.log", open="wt")
  sink(reference_log)
  sink(reference_log, type="message")
  set.seed(432202610)
  tryCatch({
    for (statement in program$retained) eval(statement, envir=scope)
  }, finally={sink(type="message"); sink(); close(reference_log)})
  original_names <- c("ALL_METHODS_EXPLORATORY.tsv", "HETEROGENEITY.tsv", "EGGER_INTERCEPT.tsv",
    "ALL_LEAVE_ONE_OUT.tsv", "ALL_REGION_SENSITIVITIES.tsv")
  stopifnot(identical(names(captured), original_names), nrow(scope$h) == 39L,
    all(is.na(scope$ans$p_primary)), all(scope$ans$p_for_family == 1), nrow(scope$ans) == 3L,
    nrow(scope$sensitivities) == 9L)
  expected_main <- captured[[1L]]
  expected_main$p_raw_exploratory <- expected_main$pval
  expected_tables <- c(list(expected_main), unname(captured[2:5]), list(scope$h))
  table_names <- c(original_names, "QUALIFIED_INPUT.tsv")
  expected_directory <- "/proof/reference-normalized"
  stopifnot(dir.create(expected_directory, mode="0700"))
  table_comparisons <- list()
  for (position in seq_along(expected_tables)) {
    filename <- table_names[[position]]
    expected <- file.path(expected_directory, filename)
    actual <- file.path("/proof/current", filename)
    write.table(expected_tables[[position]], expected, sep="\t", quote=FALSE, row.names=FALSE, na="NA")
    bytes_equal <- identical(readBin(actual, "raw", n=file.info(actual)$size), readBin(expected, "raw", n=file.info(expected)$size))
    observed <- read.delim(actual, check.names=FALSE)
    expected_readback <- read.delim(expected, check.names=FALSE)
    stopifnot(bytes_equal, identical(observed, expected_readback))
    table_comparisons[[position]] <- list(port=position - 1L, name=filename, rows=nrow(observed), columns=ncol(observed),
      complete_bytes_equal=bytes_equal, complete_readback_equal=TRUE, actual=file_fact(actual), expected=file_fact(expected),
      original_unmodified_writer_output=file.exists(file.path(scope$dest, filename)),
      adapter_added_p_raw_exploratory=position == 1L, qualified_input_re_serialized=position == 6L)
  }
  expected_rds <- list(harmonised=scope$h, mr=expected_main, heterogeneity=captured[[2L]],
    egger_intercept=captured[[3L]], leave_one_out=captured[[4L]], regional_sensitivities=captured[[5L]],
    contract=list(R="4.6.1", TwoSampleMR="0.7.11", seed=432202610L, bootstrap_n=1000L,
      methods=c("mr_ivw", "mr_egger_regression", "mr_weighted_median"), overlap="O2", role="LEGACY_EXPLORATORY",
      primary_p_source="NA", scientific_authorization_granted=FALSE))
  actual_rds <- readRDS("/proof/current/twosamplemr_v432_a.RDS")
  complete_official_object(actual_rds, expected_rds)
  stopifnot(identical(actual_rds, expected_rds))
  saveRDS(expected_rds, file.path(expected_directory, "twosamplemr_v432_a.RDS"))
  cfg <- jsonlite::read_json(inputs[[2L]], simplifyVector=TRUE)
  cert <- jsonlite::read_json(inputs[[3L]], simplifyVector=TRUE)
  expected_provenance <- list(scope="FROZEN_V432_A_LEGACY", input_sha256=input_sha,
    adapter_sha256=sha256("/source/plugins/twosamplemr-v432-a/scripts/mr.R"), frozen_scientific_code_sha256=method_sha,
    R="4.6.1", TwoSampleMR="0.7.11", method_function_sha256=digest::digest(TwoSampleMR::mr_ivw, algo="sha256"),
    package_description=unclass(packageDescription("TwoSampleMR")),
    package_description_sha256=sha256(system.file("DESCRIPTION", package="TwoSampleMR")),
    dependency_lock_sha256=input_sha[[4L]], seed=432202610L, bootstrap_n=1000L, n_independent_IV=nrow(scope$h),
    exposure_role=cfg$exposure_role, certificate_role=cert$A$role, overlap_class=cfg$overlap_class,
    primary_p_source=cfg$primary_p_source, scientific_authorization_granted=FALSE, formal_scientific_pass_granted=FALSE)
  write_json(expected_provenance, file.path(expected_directory, "INPUT_METHOD_PROVENANCE.json"))
  actual_provenance <- jsonlite::read_json("/proof/current/INPUT_METHOD_PROVENANCE.json", simplifyVector=TRUE)
  normalized_provenance <- jsonlite::read_json(file.path(expected_directory, "INPUT_METHOD_PROVENANCE.json"), simplifyVector=TRUE)
  stopifnot(identical(actual_provenance, normalized_provenance))
  headers <- capture.output({
    cat("R:", "4.6.1", "TwoSampleMR:", "0.7.11", "\n")
    cat("Prequalified IV count:", nrow(scope$h), "; no clumping or re-harmonisation\n")
    cat("Scope:", "FROZEN_V432_A_LEGACY", "\n")
    cat("seed=432202610; bootstrap_n=1000; overlap=O2; LEGACY_EXPLORATORY; primary_p=NA; family_p=1\n")
  })
  expected_log <- c(headers, readLines("/proof/original-official-messages.log", warn=FALSE), capture.output(print(expected_main)))
  actual_log <- readLines("/proof/current/twosamplemr_v432_a.log", warn=FALSE)
  stopifnot(identical(actual_log, expected_log))
  writeLines(expected_log, file.path(expected_directory, "twosamplemr_v432_a.log"))
  prior <- "/proof/prior-seen"
  prior_comparisons <- lapply(seq_along(table_names), function(position) {
    filename <- table_names[[position]]
    stopifnot(sha256(file.path(prior, filename)) == sha256(file.path("/proof/current", filename)))
    list(port=position - 1L, name=filename, complete_bytes_equal=TRUE,
      already_seen_sha256=sha256(file.path(prior, filename)), current_sha256=sha256(file.path("/proof/current", filename)))
  })
  complete_official_object(actual_rds, readRDS(file.path(prior, "twosamplemr_v432_a.RDS")))
  previous_provenance <- jsonlite::read_json(file.path(prior, "INPUT_METHOD_PROVENANCE.json"), simplifyVector=TRUE)
  previous_adapter <- previous_provenance$adapter_sha256
  previous_provenance$adapter_sha256 <- NULL
  comparable_provenance <- actual_provenance
  comparable_provenance$adapter_sha256 <- NULL
  stopifnot(identical(previous_provenance, comparable_provenance),
    identical(readLines(file.path(prior, "twosamplemr_v432_a.log"), warn=FALSE), actual_log),
    identical(input_sha, unname(vapply(inputs, sha256, character(1)))))
  write_json(list(schema="FROZEN_A_REAL_39_LEGACY_OFFICIAL_REFERENCE_V1", variants=39L, seed=432202610L,
    R="4.6.1", TwoSampleMR="0.7.11", original_run_A_block_sha256="0fe5cac9fff04351897ef3eca682ecb212e144b6e52604bc827ed141805bdc34",
    original_scientific_source_sha256=method_sha, original_scientific_statements_unchanged=TRUE,
    original_scientific_statement_count=length(program$scientific), reference_retained_statement_count=length(program$retained),
    original_guard_statements_relocated=program$excluded, whole_original_cli_executed=FALSE,
    original_verifier_not_faked=TRUE, outer_whole_project_verifier_required=TRUE, envelope=program$envelope,
    overlap_class="O2", primary_p_source="NA", all_main_primary_missing=TRUE, all_main_adjustment_one=TRUE,
    six_complete_TSVs_byte_equal=TRUE, six_complete_TSVs_readback_equal=TRUE, tables=table_comparisons,
    complete_RDS_object_identical=TRUE, RDS_numeric_tolerance=0L, input_harmonised_object_identical=TRUE,
    independent_official_call_sequence=c("mr", "mr_heterogeneity", "mr_pleiotropy_test", "mr_leaveoneout", "mr", "mr", "mr"),
    call_sequence_evidence="UNCHANGED_FROZEN_STATEMENT_AST_AND_COMPLETE_OFFICIAL_RESULTS",
    methods=c("mr_ivw", "mr_egger_regression", "mr_weighted_median"),
    official_namespace_function_count=identity$function_count, official_namespace_aggregate_sha256=identity$aggregate_sha256,
    package_description_sha256=sha256(system.file("DESCRIPTION", package="TwoSampleMR")), observed_RemoteSha=NULL,
    all_nine_current_ports_checked=TRUE, full_provenance_contract_checked=TRUE, complete_log_checked=TRUE,
    log_byte_equal_to_original_cli_claimed=FALSE,
    log_reference="COMPLETE_ORIGINAL_OFFICIAL_MESSAGES_PLUS_DECLARED_ADAPTER_HEADERS_AND_PRINT",
    adapter_added_fields_disclosed=c("p_raw_exploratory", "contract", "qualified_input_serialization", "RDS", "diagnostic_log", "provenance"),
    prior_seen_comparisons=prior_comparisons, prior_RDS_object_identical=TRUE, prior_log_lines_identical=TRUE,
    prior_provenance_only_adapter_sha_may_differ=TRUE, prior_adapter_sha256=previous_adapter,
    current_adapter_sha256=actual_provenance$adapter_sha256,
    actual_DAG_executed=FALSE, new_independent_scientific_evidence=FALSE, MRlap_executed=FALSE,
    other_275_edges_executed=FALSE, production_changed=FALSE, scientific_authorization_granted=FALSE, g0_granted=FALSE),
    "/proof/reference-verification.json")
}

if (sys.nframe() == 0L) main()
