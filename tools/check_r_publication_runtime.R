arguments <- commandArgs(trailingOnly=TRUE)
stopifnot(length(arguments) == 4L)
family <- arguments[[1L]]
original_script <- arguments[[2L]]
fixed_script <- arguments[[3L]]
output <- arguments[[4L]]
stopifnot(family %in% c("deseq2", "limma"), !file.exists(output), dir.create(output, recursive=TRUE, mode="0700"))
options(stringsAsFactors=FALSE, digits=15)
Sys.umask("0077")

sha256 <- function(path) {
  result <- system2("/usr/bin/sha256sum", c("--", shQuote(path)), stdout=TRUE, stderr=TRUE)
  if (!is.null(attr(result, "status")) || length(result) != 1L || !grepl("^[0-9a-f]{64} ", result)) stop("file hash unavailable")
  substr(result, 1L, 64L)
}

inode <- function(path) {
  result <- system2("/usr/bin/stat", c("-c", shQuote("%d:%i"), "--", shQuote(path)), stdout=TRUE, stderr=FALSE)
  if (!is.null(attr(result, "status")) || length(result) != 1L) stop("file inode unavailable")
  unname(result)
}

file_fact <- function(path) list(bytes=unname(file.info(path)$size), sha256=sha256(path))
is_assignment <- function(expression, name) is.call(expression) && identical(expression[[1L]], as.name("<-")) && identical(expression[[2L]], as.name(name))

scientific_body <- function(path) {
  expressions <- parse(path, keep.source=FALSE)
  main <- which(vapply(expressions, function(expression) is_assignment(expression, "main"), logical(1)))
  stopifnot(length(main) == 1L)
  statements <- as.list(expressions[[main]][[3L]][[3L]])[-1L]
  start <- which(vapply(statements, function(expression) is_assignment(expression, "report_path") && identical(expression[[3L]], quote(staged_outputs[[5]])), logical(1)))
  finish <- which(vapply(statements, function(expression) is.call(expression) && identical(expression[[1L]], as.name("if")) && any(grepl("output appeared during execution", deparse(expression), fixed=TRUE)), logical(1)))
  stopifnot(length(start) == 1L, length(finish) == 1L, start < finish)
  if (is_assignment(statements[[finish - 1L]], "links")) finish <- finish - 1L
  statements[seq.int(start + 1L, finish - 1L)]
}

old_body <- scientific_body(original_script)
new_body <- scientific_body(fixed_script)
stopifnot(identical(old_body, new_body))
writeLines(vapply(old_body, function(expression) paste(deparse(expression, width.cutoff=500L), collapse="\n"), character(1)), file.path(output, "unchanged-scientific-body.R"))

input <- file.path(output, "input")
stopifnot(dir.create(input, mode="0700"))
set.seed(432202610L)
sample_ids <- sprintf("S%02d", seq_len(12L))
gene_ids <- sprintf("GENE%04d", seq_len(200L))
means <- rep(seq(40, 400, length.out=200L), 12L)
condition <- rep(c("ctrl", "case"), each=6L)
effect <- rep(c(rep(1.6, 40L), rep(1, 160L)), 12L)
effect[rep(condition == "ctrl", each=200L)] <- 1
counts <- matrix(rnbinom(2400L, size=8, mu=means * effect), nrow=200L, dimnames=list(gene_ids, sample_ids))
metadata <- data.frame(sample_id=sample_ids, condition=condition, batch=rep(c("A", "B"), 6L), check.names=FALSE)
count_frame <- data.frame(gene_id=gene_ids, counts, check.names=FALSE)
count_path <- file.path(input, "counts.tsv")
metadata_path <- file.path(input, "samples.tsv")
write.table(count_frame, count_path, sep="\t", quote=TRUE, qmethod="double", row.names=FALSE)
write.table(metadata, metadata_path, sep="\t", quote=TRUE, qmethod="double", row.names=FALSE)
input_facts <- list(counts=file_fact(count_path), metadata=file_fact(metadata_path))
filenames <- if (family == "deseq2") c("results.tsv", "normalized_counts.tsv", "size_factors.tsv", "deseq2_dataset.rds", "run_report.json") else c("results.tsv", "voom_weights.tsv", "normalized_expression.tsv", "contrast_summary.tsv", "run_report.json")
parameters <- if (family == "deseq2") c(AUTONOMICS_DESEQ2_CONDITION_REFERENCE="ctrl", AUTONOMICS_DESEQ2_CONDITION_TEST="case", AUTONOMICS_DESEQ2_COVARIATES="batch", AUTONOMICS_DESEQ2_FIT_TYPE="mean", AUTONOMICS_DESEQ2_LFC_SHRINK="none", AUTONOMICS_DESEQ2_ALPHA="0.1", AUTONOMICS_DESEQ2_THREADS="1") else c(AUTONOMICS_LIMMA_OUTCOME="condition", AUTONOMICS_LIMMA_CONTRAST_VAR="condition", AUTONOMICS_LIMMA_CONTRAST_LEVELS="ctrl,case", AUTONOMICS_LIMMA_COVARIATES="batch", AUTONOMICS_LIMMA_OUTCOME_MODE="categorical", AUTONOMICS_LIMMA_NORMALIZATION="tmm", AUTONOMICS_LIMMA_ALPHA="0.05", AUTONOMICS_LIMMA_THREADS="1")
foreign_payload <- "EXPLICIT FOREIGN NONSCIENTIFIC BYTES"
fault_modes <- c("same-inode-success", "same-inode-later-link-failure", "foreign-stage-child", "last-link-rewrites-first", "staged-before-link")

run_entry <- function(script, label, mode) {
  set.seed(432202610L)
  directory <- file.path(output, label)
  stopifnot(dir.create(directory, mode="0700"))
  targets <- file.path(directory, filenames)
  names(targets) <- paste0("AUTONOMICS_OUTPUT", 0:4)
  do.call(Sys.setenv, as.list(c(AUTONOMICS_INPUT0=count_path, AUTONOMICS_INPUT1=metadata_path, targets, parameters)))
  scope <- new.env(parent=globalenv())
  calls <- 0L
  injected <- FALSE
  same_inode <- NA
  foreign_paths <- character()
  failure_injected <- FALSE
  mutate <- function(path) {
    before <- inode(path)
    writeLines(foreign_payload, path)
    same_inode <<- identical(before, inode(path))
    injected <<- TRUE
    foreign_paths <<- unique(c(foreign_paths, path))
  }
  scope$file.link <- function(from, to) {
    calls <<- calls + 1L
    if (mode == "same-inode-later-link-failure" && calls == 3L) {
      failure_injected <<- TRUE
      return(FALSE)
    }
    answer <- base::file.link(from, to)
    if (isTRUE(answer) && calls == 1L && startsWith(mode, "same-inode-")) {
      mutate(to)
      foreign_paths <<- unique(c(foreign_paths, from))
    }
    if (isTRUE(answer) && calls == 1L && mode == "foreign-stage-child") {
      path <- file.path(dirname(from), "FOREIGN-UNREGISTERED-MEMBER")
      writeLines(foreign_payload, path)
      injected <<- TRUE
      foreign_paths <<- path
    }
    if (isTRUE(answer) && calls == 5L && mode == "last-link-rewrites-first") mutate(targets[[1L]])
    if (isTRUE(answer) && calls == 1L && mode == "staged-before-link") {
      stage_paths <- get("staged_outputs", envir=parent.frame(), inherits=FALSE)
      original_identity <- get("publication_file_identity", envir=scope, inherits=FALSE)
      scope$publication_file_identity <- function(filename) {
        result <- original_identity(filename)
        if (!injected && identical(filename, unname(targets[[1L]]))) mutate(stage_paths[[2L]])
        result
      }
    }
    answer
  }
  warnings <- character()
  diagnostic <- NULL
  stdout <- file(file.path(directory, "stdout.log"), open="wt")
  stderr <- file(file.path(directory, "messages.log"), open="wt")
  sink(stdout)
  sink(stderr, type="message")
  tryCatch(withCallingHandlers(sys.source(script, envir=scope, keep.source=FALSE), warning=function(condition) {
    warnings <<- c(warnings, conditionMessage(condition))
    invokeRestart("muffleWarning")
  }), error=function(condition) diagnostic <<- conditionMessage(condition))
  sink(type="message")
  sink()
  close(stderr)
  close(stdout)
  present <- file.exists(targets)
  preserved <- vapply(foreign_paths, function(path) file.exists(path) && identical(readLines(path, warn=FALSE), foreign_payload), logical(1))
  products <- lapply(which(present), function(index) c(list(port=index - 1L, name=filenames[[index]]), file_fact(targets[[index]])))
  returned_success <- is.null(diagnostic)
  record <- list(case=label, mode=mode, complete_entry_sys_source_executed=TRUE, returned_success=returned_success, diagnostic=diagnostic, actual_link_calls=calls, injected=injected, same_inode=same_inode, later_link_failure_injected=failure_injected, foreign_paths=unname(as.list(foreign_paths)), all_foreign_paths_preserved=length(foreign_paths) > 0L && all(preserved), products=products, actual_present_ports=sum(present), warnings=unname(as.list(warnings)), full_fit_before_publication=calls > 0L, no_scientific_authorization=TRUE)
  jsonlite::write_json(record, file.path(directory, "observation.json"), auto_unbox=TRUE, pretty=TRUE, null="null", na="null")
  if (mode == "normal") stopifnot(returned_success, calls == 5L, all(present), !injected)
  else {
    stopifnot(injected, length(foreign_paths) > 0L, all(preserved))
    if (mode == "foreign-stage-child") stopifnot(returned_success, calls == 5L, all(present))
    else {
      stopifnot(!returned_success, same_inode, diagnostic %in% c("published output identity or contents changed", "staged output changed before publication", "output changed before publication completed"))
      if (mode == "last-link-rewrites-first") stopifnot(calls == 5L, diagnostic == "output changed before publication completed")
      if (mode == "staged-before-link") stopifnot(calls == 1L, diagnostic == "staged output changed before publication")
      if (startsWith(mode, "same-inode-")) stopifnot(calls == 1L, diagnostic == "published output identity or contents changed")
    }
  }
  gc(verbose=FALSE)
  record
}

records <- list(run_entry(original_script, "original-normal", "normal"), run_entry(fixed_script, "fixed-normal", "normal"))
for (mode in fault_modes) records[[length(records) + 1L]] <- run_entry(fixed_script, paste0("fixed-", mode), mode)
comparisons <- lapply(seq_along(filenames), function(index) {
  old <- file.path(output, "original-normal", filenames[[index]])
  current <- file.path(output, "fixed-normal", filenames[[index]])
  bytes_equal <- identical(sha256(old), sha256(current))
  if (family == "deseq2" && index == 4L) {
    actual <- all.equal(readRDS(old), readRDS(current), check.environment=FALSE, tolerance=0)
    jsonlite::write_json(list(port=index - 1L, actual_all_equal=actual, check_environment=FALSE, tolerance=0, compressed_bytes_equal=bytes_equal), file.path(output, "rds-comparison.json"), auto_unbox=TRUE, pretty=TRUE)
    stopifnot(isTRUE(actual))
    list(port=index - 1L, name=filenames[[index]], original=file_fact(old), fixed=file_fact(current), complete_object_equal=TRUE, check_environment=FALSE, tolerance=0, compressed_bytes_equal=bytes_equal)
  } else if (family == "deseq2" && index == 5L) {
    original_report <- jsonlite::read_json(old, simplifyVector=FALSE)
    fixed_report <- jsonlite::read_json(current, simplifyVector=FALSE)
    original_md5 <- unname(tools::md5sum(file.path(output, "original-normal", filenames[[4L]])))
    fixed_md5 <- unname(tools::md5sum(file.path(output, "fixed-normal", filenames[[4L]])))
    stopifnot(identical(original_report$outputs$dataset$md5, original_md5), identical(fixed_report$outputs$dataset$md5, fixed_md5))
    original_report$outputs$dataset$md5 <- "EACH_BOUND_OWN_COMPLETE_RDS_MD5"
    fixed_report$outputs$dataset$md5 <- "EACH_BOUND_OWN_COMPLETE_RDS_MD5"
    all_other_fields_exact <- identical(original_report, fixed_report)
    comparison <- list(port=index - 1L, name=filenames[[index]], original=file_fact(old), fixed=file_fact(current), complete_bytes_equal=bytes_equal, single_exact_dataset_md5_field_exception=TRUE, all_other_fields_exact=all_other_fields_exact, dataset_rds_md5=list(original=original_md5, fixed=fixed_md5))
    jsonlite::write_json(comparison, file.path(output, "normal-port-4-comparison.json"), auto_unbox=TRUE, pretty=TRUE)
    stopifnot(all_other_fields_exact)
    comparison
  } else {
    jsonlite::write_json(list(port=index - 1L, name=filenames[[index]], original=file_fact(old), fixed=file_fact(current), complete_bytes_equal=bytes_equal), file.path(output, paste0("normal-port-", index - 1L, "-comparison.json")), auto_unbox=TRUE, pretty=TRUE)
    stopifnot(bytes_equal)
    list(port=index - 1L, name=filenames[[index]], original=file_fact(old), fixed=file_fact(current), complete_bytes_equal=TRUE)
  }
})
stopifnot(identical(input_facts, list(counts=file_fact(count_path), metadata=file_fact(metadata_path))))
packages <- if (family == "deseq2") c("DESeq2", "apeglm", "jsonlite") else c("limma", "edgeR", "statmod", "jsonlite")
report <- list(schema="TWO_R_PUBLICATION_FULL_ENTRY_RUNTIME_V1", family=family, actual_cases=length(records), records=records, complete_normal_port_comparisons=comparisons, source_sha256=list(original=sha256(original_script), fixed=sha256(fixed_script)), scientific_body_AST_identical=TRUE, inputs=input_facts, genes=200L, samples=12L, per_entry_seed=432202610L, parameters=as.list(parameters), packages=as.list(setNames(vapply(packages, function(package) as.character(packageVersion(package)), character(1)), packages)), R_version=as.character(getRversion()), DESeq2_scope=if (family == "deseq2") "MEAN_DISPERSION_NONE_SHRINKAGE_ONLY_NOT_APEGLM_OR_ALL_FIT_BRANCHES" else NULL, official_package_entries_executed=TRUE, actual_DAG_executed=FALSE, full_manifest_resource_certified=FALSE, production_changed=FALSE, scientific_authorization_granted=FALSE, g0_granted=FALSE)
stopifnot(length(records) == 7L)
jsonlite::write_json(report, file.path(output, "verification.json"), auto_unbox=TRUE, pretty=TRUE, null="null")
cat("TWO_R_PUBLICATION_SEVEN_COMPLETE_ENTRIES_PROVEN", family, "\n")
