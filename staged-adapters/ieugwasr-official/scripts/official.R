official_contracts <- list(
  associations = list(required = c("variants", "id"), allowed = c("variants", "id", "proxies", "r2", "align_alleles", "palindromes", "maf_threshold", "assocs_per_request", "max_ids_per_request")),
  phewas = list(required = "variants", allowed = c("variants", "pval", "batch")),
  tophits = list(required = "id", allowed = c("id", "pval", "clump", "r2", "kb", "pop", "force_server")),
  variants_rsid = list(required = "rsid", allowed = "rsid"),
  variants_chrpos = list(required = "chrpos", allowed = c("chrpos", "radius")),
  ld_clump_api = list(required = c("clump_kb", "clump_r2", "clump_p", "pop"), allowed = c("clump_kb", "clump_r2", "clump_p", "pop")),
  gwasinfo = list(required = character(), allowed = "id")
)

validate_request <- function(request) {
  if (!is.list(request) || is.null(names(request)) || anyDuplicated(names(request)) ||
      !setequal(names(request), c("operation", "arguments"))) stop("Expected operation and arguments only")
  operation <- request$operation
  if (!is.character(operation) || length(operation) != 1L || is.na(operation) ||
      !operation %in% names(official_contracts)) stop("Unsupported official operation; gwasinfo_search has no author equivalent")
  arguments <- request$arguments
  if (!is.list(arguments) || (length(arguments) && (is.null(names(arguments)) ||
      any(!nzchar(names(arguments))) || anyDuplicated(names(arguments))))) stop("Arguments must be a named object")
  contract <- official_contracts[[operation]]
  if (length(setdiff(names(arguments), contract$allowed))) stop("Unsupported official argument")
  if (length(setdiff(contract$required, names(arguments)))) stop("Missing required official argument")
  vector_fields <- c("variants", "id", "rsid", "chrpos")
  numeric_fields <- c("proxies", "r2", "align_alleles", "palindromes", "maf_threshold", "assocs_per_request", "max_ids_per_request", "pval", "clump", "kb", "radius", "clump_kb", "clump_r2", "clump_p")
  for (field in names(arguments)) {
    value <- arguments[[field]]
    if (field %in% vector_fields) {
      if (is.list(value) && all(vapply(value, function(item) is.character(item) && length(item) == 1L && !is.na(item), logical(1)))) value <- if (length(value)) unlist(value, use.names = FALSE) else character()
      if (!is.character(value) || anyNA(value) || any(!nzchar(value))) stop("Expected nonmissing character vector")
      if (length(value) == 0L && !field %in% c("batch", "id")) stop("Empty variant vector")
    } else if (field == "batch") {
      if (is.list(value)) {
        if (!length(value)) value <- character()
        else if (all(vapply(value, function(item) is.character(item) && length(item) == 1L && !is.na(item), logical(1)))) value <- unlist(value, use.names = FALSE)
        else if (all(vapply(value, function(item) is.numeric(item) && length(item) == 1L && is.finite(item), logical(1)))) value <- unlist(value, use.names = FALSE)
      }
      if ((!is.character(value) && !is.numeric(value)) || anyNA(value) || (is.numeric(value) && any(!is.finite(value)))) stop("Expected character or numeric batch vector")
    } else if (field %in% numeric_fields) {
      if (!is.numeric(value) || length(value) != 1L || !is.finite(value)) stop("Expected finite numeric scalar")
    } else if (field == "force_server") {
      if (!is.logical(value) || length(value) != 1L || is.na(value)) stop("Expected logical force_server")
    } else if (field == "pop") {
      if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value)) stop("Expected population string")
    }
    arguments[[field]] <- value
  }
  list(operation = operation, arguments = arguments)
}

resolve_official <- function(operation) {
  get(operation, envir = asNamespace("ieugwasr"), inherits = FALSE)
}

invoke_official <- function(request, dataset = NULL, resolver = resolve_official) {
  checked <- validate_request(request)
  arguments <- checked$arguments
  if (checked$operation == "ld_clump_api") {
    if (!is.data.frame(dataset) || !all(c("rsid", "pval") %in% names(dataset))) stop("ld_clump_api requires original data.frame with rsid and pval")
    arguments$dat <- dataset
  } else if (!is.null(dataset)) stop("Dataset port is only valid for ld_clump_api")
  do.call(resolver(checked$operation), arguments)
}

typed_projection <- function(result) {
  if (!is.data.frame(result)) stop("Official result is not a data.frame; refusing lossy projection")
  if (anyDuplicated(names(result)) || any(!nzchar(names(result)))) stop("Cannot project duplicate or blank column names")
  columns <- lapply(seq_along(result), function(index) {
    value <- result[[index]]
    if (is.object(value) || !typeof(value) %in% c("integer", "double", "logical", "character") || !is.null(dim(value))) stop("Unsupported typed projection column; RDS remains private until all ports succeed")
    cells <- lapply(seq_along(value), function(row_index) {
      item <- value[[row_index]]
      if (is.double(item) && is.nan(item)) return(list(state = "NAN"))
      if (is.na(item)) return(list(state = "MISSING_NA"))
      if (is.double(item) && is.infinite(item)) return(list(state = if (item > 0) "POSITIVE_INFINITY" else "NEGATIVE_INFINITY"))
      list(state = "PRESENT", value = item)
    })
    list(name = names(result)[[index]], storage_type = typeof(value), cells = cells)
  })
  list(schema = "IEUGWASR_TYPED_DATAFRAME_PROJECTION_V1", rows = nrow(result),
       row_names = as.list(rownames(result)), columns = columns,
       authoritative_artifact = "complete_result.RDS", result_classes = as.list(class(result)))
}

path_identity <- function(filename) {
  result <- system2("/usr/bin/stat", c("--printf=%d:%i", "--", shQuote(filename)), stdout = TRUE, stderr = FALSE)
  if (!is.null(attr(result, "status")) || length(result) != 1L || !grepl("^[0-9]+:[0-9]+$", result)) stop("Cannot establish output identity")
  result
}

is_symlink <- function(filename) {
  target <- Sys.readlink(filename)
  !is.na(target) && nzchar(target)
}

port_exists <- function(filename) file.exists(filename) || is_symlink(filename)

publish_ports <- function(destinations, writer) {
  if (!is.character(destinations) || length(destinations) != 4L || anyNA(destinations) || any(!nzchar(destinations))) stop("Four output ports are required")
  destinations <- vapply(destinations, function(filename) {
    parent <- normalizePath(dirname(filename), mustWork = TRUE)
    file.path(parent, basename(filename))
  }, character(1))
  if (anyDuplicated(destinations) || any(vapply(destinations, port_exists, logical(1)))) stop("Output alias or existing output")
  stage <- tempfile(".ieugwasr-publication-", tmpdir = dirname(destinations[[1L]]))
  if (!dir.create(stage, mode = "0700")) stop("Cannot create private publication stage")
  on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  staged <- file.path(stage, paste0("port-", seq_len(4L)))
  created <- list()
  completed <- FALSE
  on.exit({
    if (!completed) for (entry in created) {
      identity <- tryCatch(path_identity(entry$filename), error = function(condition) "")
      if (identical(identity, entry$identity)) unlink(entry$filename)
    }
  }, add = TRUE)
  writer(staged)
  for (index in seq_along(staged)) {
    if (!file.exists(staged[[index]]) || is_symlink(staged[[index]]) || dir.exists(staged[[index]])) stop("Missing or unsafe staged output")
    identity <- path_identity(staged[[index]])
    if (!file.link(staged[[index]], destinations[[index]])) stop("Exclusive output publication failed")
    created[[length(created) + 1L]] <- list(filename = destinations[[index]], identity = identity)
  }
  completed <- TRUE
  invisible(destinations)
}

write_official_products <- function(request, dataset, outputs, resolver = resolve_official) {
  log_connection <- file(outputs[[4L]], open = "wt")
  initial_output <- sink.number()
  initial_message <- sink.number(type = "message")
  sink(log_connection)
  sink(log_connection, type = "message")
  on.exit({
    sink(type = "message")
    if (initial_message != 2L) sink(initial_message, type = "message")
    while (sink.number() > initial_output) sink()
    close(log_connection)
  }, add = TRUE)
  result <- invoke_official(request, dataset, resolver)
  projection <- typed_projection(result)
  saveRDS(result, outputs[[1L]], version = 3L)
  jsonlite::write_json(projection, outputs[[2L]], auto_unbox = TRUE, null = "null", pretty = TRUE, digits = NA)
  audit <- list(schema = "IEUGWASR_DIRECT_OFFICIAL_CALL_V1", operation = request$operation,
                author_implementation = "ieugwasr", declared_package_version = "1.2.0",
                authoritative_output = "complete_result.RDS", projection = "typed_dataframe.json",
                wrapper_request_payload_not_explicitly_logged = TRUE,
                credential_policy = "author environment; do not persist headers; real credential logging qualification pending",
                statistical_formula_reimplemented = FALSE, scientific_release_granted = FALSE)
  jsonlite::write_json(audit, outputs[[3L]], auto_unbox = TRUE, pretty = TRUE)
  cat("Official call and complete RDS serialization completed.\n")
  invisible(result)
}

main <- function() {
  if (!requireNamespace("ieugwasr", quietly = TRUE) || as.character(utils::packageVersion("ieugwasr")) != "1.2.0") stop("Requires locked official ieugwasr 1.2.0")
  if (!requireNamespace("jsonlite", quietly = TRUE)) stop("Requires jsonlite")
  input <- Sys.getenv("AUTONOMICS_INPUT0", unset = "")
  dataset_input <- Sys.getenv("AUTONOMICS_INPUT1", unset = "")
  outputs <- Sys.getenv(paste0("AUTONOMICS_OUTPUT", 0:3), unset = "")
  if (!nzchar(input) || !file.exists(input)) stop("Request JSON input required")
  request <- jsonlite::read_json(input, simplifyVector = FALSE)
  dataset <- if (nzchar(dataset_input)) readRDS(dataset_input) else NULL
  publish_ports(outputs, function(staged) write_official_products(request, dataset, staged))
  invisible(0L)
}

if (sys.nframe() == 0L) {
  status <- tryCatch(main(), error = function(condition) {
    message(conditionMessage(condition))
    1L
  })
  quit(save = "no", status = status, runLast = FALSE)
}
