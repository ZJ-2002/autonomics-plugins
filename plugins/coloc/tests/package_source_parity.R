arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 2L)
mode <- arguments[1L]
directory <- arguments[2L]
if (mode == "reference") .libPaths(c(file.path(directory, "official-library"), .libPaths()))
records <- list()
for (package in c("coloc", "susieR")) {
  if (mode == "reference") stopifnot(normalizePath(find.package(package)) ==
                                      normalizePath(file.path(directory, "official-library", package)))
  namespace <- asNamespace(package)
  definitions <- list()
  for (name in sort(ls(namespace, all.names = TRUE))) {
    value <- get(name, namespace, inherits = FALSE)
    if (is.function(value)) definitions[[name]] <- list(formals = formals(value), body = deparse(body(value)))
  }
  records[[package]] <- definitions
  cat(package, as.character(packageVersion(package)), "functions:", length(definitions),
      "location:", find.package(package), "\n")
}
saveRDS(records, file.path(directory, paste0("namespace-", mode, ".RDS")))
if (mode == "reference") {
  image <- readRDS(file.path(directory, "namespace-image.RDS"))
  stopifnot(identical(image, records))
  cat("Every defined namespace function body and formal argument matches freshly built author source\n")
}
