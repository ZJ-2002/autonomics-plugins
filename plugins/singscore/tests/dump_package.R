arguments <- commandArgs(trailingOnly = TRUE)
if (length(arguments) != 2) stop("Expected reference library or INSTALLED, and output RDS")
if (arguments[1] != "INSTALLED") .libPaths(c(arguments[1], .libPaths()))
suppressMessages(library(singscore))
stopifnot(packageVersion("singscore") == "1.32.0")
if (arguments[1] != "INSTALLED") {
  stopifnot(startsWith(normalizePath(find.package("singscore")), normalizePath(arguments[1])))
}
namespace <- asNamespace("singscore")
representation <- function(method) {
  list(formals = paste(deparse(formals(method)), collapse = "\n"),
       body = paste(deparse(body(method)), collapse = "\n"))
}
functions <- list()
for (name in sort(ls(namespace, all.names = TRUE))) {
  value <- get(name, envir = namespace, inherits = FALSE)
  if (is.function(value)) functions[[name]] <- representation(value)
}
methods <- list()
for (name in c("rankGenes", "simpleScore")) {
  found <- findMethods(name, where = namespace)
  methods[[name]] <- lapply(found[sort(names(found))], representation)
}
saveRDS(list(functions = functions, methods = methods), arguments[2])
cat("package_location:", find.package("singscore"), "\n")
cat("functions:", length(functions), "\n")
cat("rankGenes methods:", length(methods$rankGenes), "\n")
cat("simpleScore methods:", length(methods$simpleScore), "\n")
print(sessionInfo())
