options(digits = 17)
require_value <- function(value, message) if (!isTRUE(value)) stop(message, call. = FALSE)
technical_contract_profile <- function(request) {
  version <- Sys.getenv("AUTONOMICS_TECHNICAL_CONTRACT_VERSION", unset = "1")
  require_value(version %in% c("1", "2"), "Unsupported technical contract version")
  schema <- if (version == "1") 1L else 2L
  role <- if (schema == 1L) "SYNTHETIC_MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION" else "MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION"
  allowed <- if (schema == 1L) "SYNTHETIC_TECHNICAL_INPUT" else c("SYNTHETIC_TECHNICAL_INPUT", "EMPIRICAL_TECHNICAL_INPUT")
  require_value(identical(request$schema_version, schema) && identical(request$scope, "TECHNICAL_ONLY_NOT_G0") && identical(request$scientific_qualification, "NOT_GRANTED") && identical(request$analysis_role, role), "No scientific/longitudinal eligibility or G0 granted; technical version must match")
  require_value(is.character(request$input_role) && length(request$input_role) == 1L && !is.na(request$input_role) && request$input_role %in% allowed, "Explicit versioned source role required")
  list(schema_version = schema, input_role = request$input_role, analysis_role = role)
}
technical_parent_role <- function(bundle, request) {
  profile <- technical_contract_profile(request)
  if (profile$schema_version == 2L) {
    require_value(is.list(bundle$request) && is.list(bundle$technical_lineage), "Versioned parent source-role lineage required")
    parent <- technical_contract_profile(bundle$request)
    require_value(identical(bundle$schema_version, 2L) && identical(bundle$scope, request$scope) && identical(bundle$analysis_role, profile$analysis_role) && identical(bundle$input_role, profile$input_role) && identical(parent, profile), "Parent schema/source role cannot cross versions or be relabeled")
    require_value(identical(bundle$technical_lineage$schema_version, 2L) && identical(bundle$technical_lineage$input_role, profile$input_role) && identical(bundle$technical_lineage$analysis_role, profile$analysis_role) && identical(bundle$technical_lineage$request_input_sha256, bundle$request$input0_sha256) && identical(bundle$technical_lineage$scientific_qualification_granted, FALSE), "Parent technical lineage differs")
    if (!is.null(bundle$parent)) {
      require_value(identical(bundle$technical_lineage$parent_input_role, bundle$parent$input_role), "Nested parent role lineage differs")
      technical_parent_role(bundle$parent, request)
    } else require_value(is.null(bundle$technical_lineage$parent_input_role), "Unexpected parent role without parent state")
  }
  invisible(profile)
}
checksum <- function(filename) {
  value <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_value(is.null(attr(value, "status")) && length(value) == 1L && grepl("^[0-9a-f]{64} ", value), "Input SHA unavailable")
  substr(value, 1L, 64L)
}
unique_keys <- function(value) {
  if (is.list(value)) {
    require_value(is.null(names(value)) || !anyDuplicated(names(value)), "Duplicate JSON keys forbidden")
    invisible(lapply(value, unique_keys))
  }
}
bind_json_hash <- function(bytes, hash) {
  require_value(is.raw(bytes) && grepl("^[0-9a-f]{64}$", hash), "Raw JSON and exact source hash required")
  codes <- as.integer(bytes)
  string_end <- function(start) {
    escaped <- FALSE
    for (position in seq.int(start + 1L, length(codes))) {
      if (escaped) escaped <- FALSE else if (codes[position] == 92L) escaped <- TRUE else if (codes[position] == 34L) return(position)
    }
    stop("Unterminated JSON token")
  }
  skip_space <- function(start) {
    while (start <= length(codes) && codes[start] %in% c(9L, 10L, 13L, 32L)) start <- start + 1L
    start
  }
  depth <- 0L
  position <- 1L
  matches <- list()
  while (position <= length(codes)) {
    if (codes[position] == 34L) {
      end <- string_end(position)
      next_position <- skip_space(end + 1L)
      if (depth == 1L && next_position <= length(codes) && codes[next_position] == 58L && identical(jsonlite::fromJSON(rawToChar(bytes[position:end])), "input0_sha256")) {
        start <- skip_space(next_position + 1L)
        require_value(codes[start] == 34L, "Upstream placeholder must be a string token")
        finish <- string_end(start)
        require_value(identical(jsonlite::fromJSON(rawToChar(bytes[start:finish])), "UPSTREAM_CONTENT_HASH"), "Only explicit unresolved placeholder may change")
        matches[[length(matches) + 1L]] <- c(start, finish)
      }
      position <- end + 1L
      next
    }
    if (codes[position] %in% c(123L, 91L)) depth <- depth + 1L
    if (codes[position] %in% c(125L, 93L)) depth <- depth - 1L
    position <- position + 1L
  }
  require_value(length(matches) == 1L, "Exactly one root source hash token required")
  start <- matches[[1]][1]
  finish <- matches[[1]][2]
  prefix <- if (start > 1L) bytes[seq_len(start - 1L)] else raw()
  suffix <- if (finish < length(bytes)) bytes[seq.int(finish + 1L, length(bytes))] else raw()
  c(prefix, charToRaw(paste0('"', hash, '"')), suffix)
}
run_binding_entry <- function(outputs) {
audit <- list(status = "RUNNING", G0_granted = FALSE, scientific_qualification_granted = FALSE, resident_deployment_granted = FALSE)
save_audit <- function() jsonlite::write_json(audit, outputs[2], auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA)
save_audit()
cat("RUNNING hash-only contract binding\n", file = outputs[3])
status <- tryCatch({
  require_value(as.character(getRversion()) == "4.6.1" && as.character(packageVersion("mice")) == "3.19.0" && Sys.getenv("AUTONOMICS_INPUT_COUNT") == "2", "Pinned runtime/two input ports required")
  input <- Sys.getenv("AUTONOMICS_INPUT0")
  template <- Sys.getenv("AUTONOMICS_INPUT1")
  require_value(file.info(template)$size <= 1024^2 && file.info(input)$size <= 16 * 1024^2, "Binder input byte budget exceeded")
  request <- jsonlite::fromJSON(template, simplifyVector = FALSE)
  unique_keys(request)
  keys <- c("schema_version", "mode", "scope", "input_role", "scientific_qualification", "analysis_role", "test_id", "input0_sha256", "input2_sha256", "expected_row_ids", "expected_columns", "max_input_bytes", "max_rows", "params")
  require_value(is.list(request) && setequal(names(request), keys), "Exact bind template schema required")
  profile <- technical_contract_profile(request)
  require_value(request$mode == "complete" && request$input0_sha256 == "UPSTREAM_CONTENT_HASH", "Only explicit unresolved upstream hash may be bound")
  require_value(is.numeric(request$max_rows) && !is.logical(request$max_rows) && length(request$max_rows) == 1L && is.finite(request$max_rows) && request$max_rows == floor(request$max_rows) && request$max_rows >= 2 && request$max_rows <= 10000, "Frozen row budget required")
  require_value(is.numeric(request$max_input_bytes) && !is.logical(request$max_input_bytes) && length(request$max_input_bytes) == 1L && is.finite(request$max_input_bytes) && request$max_input_bytes == floor(request$max_input_bytes) && request$max_input_bytes >= 1 && request$max_input_bytes <= 16 * 1024^2 && file.info(input)$size <= request$max_input_bytes, "Frozen byte budget required")
  bundle <- readRDS(input)
  technical_parent_role(bundle, request)
  require_value(inherits(bundle$result, "mids") && bundle$scope == "TECHNICAL_ONLY_NOT_G0" && bundle$analysis_role == request$analysis_role && identical(bundle$schema_version, profile$schema_version), "Qualified upstream technical mids state required")
  rows <- unlist(request$expected_row_ids, use.names = FALSE)
  require_value(is.list(request$expected_row_ids) && is.null(names(request$expected_row_ids)) && is.character(rows) && !anyNA(rows) && !anyDuplicated(rows) && length(rows) <= request$max_rows && identical(rows, bundle$original_row_ids), "Frozen exact upstream row universe differs")
  require_value(identical(unlist(request$expected_columns, use.names = FALSE), bundle$expected_columns) && identical(request$input2_sha256, bundle$status_sha256), "Frozen columns/status receipt differ")
  resolved <- request
  resolved$input0_sha256 <- checksum(input)
  unchanged <- resolved
  unchanged$input0_sha256 <- request$input0_sha256
  require_value(identical(unchanged, request), "Binding may change only source SHA256")
  original_bytes <- readBin(template, "raw", n = file.info(template)$size)
  bound_bytes <- bind_json_hash(original_bytes, resolved$input0_sha256)
  writeBin(bound_bytes, outputs[1])
  require_value(identical(jsonlite::fromJSON(outputs[1], simplifyVector = FALSE), resolved), "Serialized binding changed frozen parameters")
  audit$status <- "TECHNICAL_HASH_BINDING_PASS_NOT_SCIENTIFIC"
  audit$template_sha256 <- checksum(template)
  audit$input0_sha256 <- resolved$input0_sha256
  audit$resolved_sha256 <- checksum(outputs[1])
  audit$only_source_sha256_changed <- TRUE
  if (profile$schema_version == 2L) {
    audit$schema_version <- 2L
    audit$input_role <- profile$input_role
    audit$analysis_role <- profile$analysis_role
    audit$parent_technical_lineage <- bundle$technical_lineage
    audit$MCAR_MAR_MNAR_assumption_established <- FALSE
    audit$MICE_stationarity_MAR_MNAR_or_longitudinal_eligibility_proven <- FALSE
  }
  save_audit()
  cat("PASS hash-only binding\n", file = outputs[3], append = TRUE)
  0L
}, error = function(error) {
  unlink(outputs[1])
  audit$status <<- "BLOCKED"
  audit$error <<- conditionMessage(error)
  save_audit()
  cat("BLOCKED ", conditionMessage(error), "\n", file = outputs[3], append = TRUE)
  message(conditionMessage(error))
  2L
})
status
}
publish_outputs <- function(writer, output_count, diagnostics, input_count) {
  destinations <- vapply(seq_len(output_count) - 1L, function(index) Sys.getenv(paste0("AUTONOMICS_OUTPUT", index)), "")
  if (any(!nzchar(destinations))) stop("Every declared output path is required")
  destinations <- vapply(destinations, function(filename)
    file.path(normalizePath(dirname(filename), mustWork = TRUE), basename(filename)), character(1))
  if (anyDuplicated(destinations) || anyDuplicated(basename(destinations))) stop("Distinct output paths required")
  inputs <- vapply(seq_len(input_count) - 1L, function(index) Sys.getenv(paste0("AUTONOMICS_INPUT", index)), "")
  if (any(!nzchar(inputs))) stop("Both declared inputs are required")
  input_paths <- vapply(inputs, normalizePath, character(1), mustWork = TRUE)
  if (any(destinations %in% input_paths)) stop("Input and output paths must be distinct")
  path_present <- function(filename) {
    target <- Sys.readlink(filename)
    file.exists(filename) || (!is.na(target) && nzchar(target))
  }
  if (any(vapply(destinations, path_present, logical(1)))) stop("Refusing to overwrite existing output")
  stage <- tempfile(pattern = ".mice-owned-", tmpdir = dirname(destinations[[1L]]))
  if (!dir.create(stage, mode = "0700")) stop("Private output staging could not be created")
  created <- list()
  completed <- FALSE
  file_identity <- function(filename) {
    value <- system2("stat", c("-c", shQuote("%d:%i"), shQuote(filename)), stdout = TRUE, stderr = TRUE)
    if (!is.null(attr(value, "status")) || length(value) != 1L || !grepl("^[0-9]+:[0-9]+$", value)) {
      stop("Output file identity unavailable")
    }
    value[[1L]]
  }
  on.exit({
    if (!completed) {
      for (owned in rev(created)) {
        tryCatch({
          if (path_present(owned$path) && identical(file_identity(owned$path), owned$identity)) unlink(owned$path)
        }, error = function(error) warning(paste("Output rollback retained an unverified path:", conditionMessage(error))))
      }
    }
    unlink(stage, recursive = TRUE)
  }, add = TRUE)
  private_outputs <- file.path(stage, basename(destinations))
  status <- writer(private_outputs)
  if (length(status) != 1L || !status %in% c(0L, 2L)) stop("Invalid wrapper exit status")
  positions <- if (status == 0L) seq_along(destinations) else diagnostics
  for (position in positions) {
    identity <- file_identity(private_outputs[[position]])
    if (!file.link(private_outputs[[position]], destinations[[position]])) stop("Exclusive output publication failed")
    created[[length(created) + 1L]] <- list(path = destinations[[position]], identity = identity)
  }
  completed <- TRUE
  status
}
exit_status <- publish_outputs(run_binding_entry, 3L, c(2L, 3L), 2L)
if (exit_status != 0L) quit(save = "no", status = exit_status)

