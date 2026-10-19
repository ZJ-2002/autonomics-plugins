arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 3L)
.libPaths(c(normalizePath(arguments[[2L]], mustWork = TRUE), .libPaths()))
stopifnot(as.character(utils::packageVersion("ieugwasr")) == "1.2.0")
source(arguments[[1L]])
permanent <- normalizePath(Sys.getenv("AUTONOMICS_VALIDATION_PERMANENT"), mustWork = TRUE)
output <- arguments[[3L]]
stopifnot(identical(normalizePath(dirname(output), mustWork = TRUE), permanent), !file.exists(output))
stopifnot(dir.create(output, recursive = FALSE, mode = "0700"))

namespace <- asNamespace("ieugwasr")
author_functions <- ls(namespace, all.names = TRUE)
author_functions <- author_functions[vapply(author_functions, function(name) is.function(get(name, namespace)), logical(1))]
author_bodies <- lapply(author_functions, function(name) serialize(get(name, namespace), NULL))
names(author_bodies) <- author_functions
requests <- list(
  list(operation = "associations", arguments = list(variants = c("rs1", "rs2"), id = "fixture-study", proxies = 0, assocs_per_request = 1, max_ids_per_request = 1)),
  list(operation = "phewas", arguments = list(variants = "rs1", batch = "fixture", pval = 0.01)),
  list(operation = "tophits", arguments = list(id = "fixture-study", force_server = FALSE)),
  list(operation = "variants_rsid", arguments = list(rsid = "rs1")),
  list(operation = "variants_chrpos", arguments = list(chrpos = "1:2", radius = 0)),
  list(operation = "ld_clump_api", arguments = list(clump_kb = 10000, clump_r2 = 0.001, clump_p = 1, pop = "EUR")),
  list(operation = "gwasinfo", arguments = list(id = "fixture-study"))
)
responses <- c(
  associations = '[{"rsid":"rs1","id":"fixture-study","beta":0.2,"se":0.1,"p":0.05,"n":"120","eaf":"0.3"}]',
  phewas = '[{"rsid":"rs1","id":"fixture-a","p":0.005,"n":"120"},{"rsid":"rs1","id":"fixture-b","p":0.001,"n":"130"}]',
  tophits = '[{"rsid":"rs1","id":"fixture-study","beta":0.2,"se":0.1,"p":0.05,"n":"120"}]',
  variants_rsid = '[{"_id":"rs1","_source":{"ID":"rs1","CHROM":"1","POS":2,"COMMON":1}}]',
  variants_chrpos = '[{"query":"1:2","ID":"rs1","CHROM":"1","POS":2,"COMMON":1}]',
  ld_clump_api = '["rs1"]',
  gwasinfo = '[{"id":"fixture-study","trait":"fixture","sample_size":120}]'
)
dataset <- data.frame(rsid = c("rs2", "rs1"), pval = c(0.2, 0.1), extra = c("keep-b", "keep-a"), row.names = c("row-b", "row-a"))
original_post <- get("POST", asNamespace("httr"))
original_get <- get("GET", asNamespace("httr"))
original_options <- options(ieugwasr_api = "https://invalid.fixture.test/", ieugwasr_reset = NULL)
transport_calls <- list()
current_body <- ""
current_status <- 200L
mock_transport <- function(url, ..., body = NULL) {
  stopifnot(startsWith(url, "https://invalid.fixture.test/"))
  transport_calls[[length(transport_calls) + 1L]] <<- list(url = url, query = body)
  structure(list(url = url, status_code = current_status,
                 headers = list(`content-type` = "application/json"), content = charToRaw(current_body)),
            class = "response")
}
empty_credential_resolver <- function(operation) {
  author <- get(operation, envir = namespace, inherits = FALSE)
  function(...) do.call(author, c(list(...), list(opengwas_jwt = "")))
}
observations <- list()
tryCatch({
  assignInNamespace("POST", mock_transport, ns = "httr")
  assignInNamespace("GET", mock_transport, ns = "httr")
  for (request in requests) {
    operation <- request$operation
    current_body <- responses[[operation]]
    current_status <- 200L
    transport_calls <- list()
    call_arguments <- request$arguments
    if (operation == "ld_clump_api") call_arguments$dat <- dataset
    reference <- do.call(empty_credential_resolver(operation), call_arguments)
    reference_calls <- transport_calls
    transport_calls <- list()
    directory <- file.path(output, operation)
    stopifnot(dir.create(directory, mode = "0700"))
    ports <- file.path(directory, c("complete_result.RDS", "typed_dataframe.json", "audit.json", "run.log"))
    publish_ports(ports, function(staged) write_official_products(request, if (operation == "ld_clump_api") dataset else NULL, staged, empty_credential_resolver))
    actual <- readRDS(ports[[1L]])
    stopifnot(identical(actual, reference), identical(transport_calls, reference_calls))
    if (operation == "associations") stopifnot(length(reference_calls) == 2L)
    if (operation == "phewas") stopifnot(identical(actual$id, c("fixture-b", "fixture-a")))
    if (operation == "tophits") stopifnot(reference_calls[[1L]]$query$preclumped == 1)
    if (operation == "ld_clump_api") stopifnot(identical(actual, dataset[2L, , drop = FALSE]))
    saveRDS(reference, file.path(directory, "independent_direct_author.RDS"), version = 3L)
    observations[[operation]] <- list(complete_RDS_identical = TRUE, official_transport_calls = length(reference_calls), request_transport_identical = TRUE)
  }
  current_body <- "[]"
  current_status <- 200L
  empty_request <- list(operation = "variants_rsid", arguments = list(rsid = "rs1"))
  direct_error <- tryCatch(invoke_official(empty_request, resolver = empty_credential_resolver), error = function(condition) conditionMessage(condition))
  empty_directory <- file.path(output, "empty-author-error")
  stopifnot(dir.create(empty_directory, mode = "0700"))
  empty_ports <- file.path(empty_directory, paste0("port-", 0:3))
  adapter_error <- tryCatch(publish_ports(empty_ports, function(staged) write_official_products(empty_request, NULL, staged, empty_credential_resolver)), error = function(condition) conditionMessage(condition))
  stopifnot(is.character(direct_error), identical(adapter_error, direct_error), !any(file.exists(empty_ports)))
  observations$empty_variants_rsid <- list(official_error_preserved = TRUE, no_normal_ports = TRUE, error = direct_error)
  current_body <- '{"message":"fixture permission denied"}'
  current_status <- 401L
  transport_error <- tryCatch(invoke_official(empty_request, resolver = empty_credential_resolver), error = function(condition) conditionMessage(condition))
  stopifnot(is.character(transport_error), grepl("401", transport_error, fixed = TRUE))
  observations$HTTP_401 <- list(official_error_preserved = TRUE, actual_network_requests = 0L)
}, finally = {
  assignInNamespace("POST", original_post, ns = "httr")
  assignInNamespace("GET", original_get, ns = "httr")
  options(original_options)
})
after_bodies <- lapply(author_functions, function(name) serialize(get(name, namespace), NULL))
names(after_bodies) <- author_functions
stopifnot(identical(author_bodies, after_bodies))
jsonlite::write_json(list(schema = "IEUGWASR_DIRECT_AUTHOR_MOCKED_TRANSPORT_V1", official_version = "1.2.0",
                         author_namespace_functions_unchanged = length(author_functions), observations = observations,
                         only_httr_transport_intercepted = TRUE, actual_network_requests = 0L,
                         actual_credentials_read = FALSE, image_verified = FALSE, DAG_verified = FALSE,
                         scientific_release_granted = FALSE), file.path(output, "verification.json"),
                     auto_unbox = TRUE, pretty = TRUE, null = "null")
