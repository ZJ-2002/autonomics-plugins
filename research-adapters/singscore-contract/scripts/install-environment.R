# Software preparation only; never called during scientific execution.
stopifnot(identical(as.character(getRversion()), "4.6.1"))
cran <- sprintf("https://packagemanager.posit.co/cran/__linux__/noble/%s", Sys.getenv("CRAN_SNAPSHOT"))
options(repos = c(CRAN = cran), timeout = 600L,
  HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(), paste(getRversion(), R.version$platform, R.version$arch, R.version$os)))
utils::install.packages(c("BiocManager", "jsonlite", "digest"))
stopifnot(requireNamespace("BiocManager", quietly = TRUE),
  requireNamespace("jsonlite", quietly = TRUE), requireNamespace("digest", quietly = TRUE))
repositories <- BiocManager::repositories(version = Sys.getenv("BIOCONDUCTOR_RELEASE"))
options(repos = c(CRAN = cran, repositories[names(repositories) != "CRAN"]))
archive <- "/opt/autonomics-source/singscore_1.32.0.tar.gz"
stopifnot(identical(digest::digest(file = archive, algo = "sha256"),
  "b4ffcbcb215ec99b9c8159bcf47cebba02517ff2c76c6aebabd2d7848298fd5a"))
scratch <- tempfile(); dir.create(scratch)
utils::untar(archive, files = "singscore/DESCRIPTION", exdir = scratch)
description <- read.dcf(file.path(scratch, "singscore", "DESCRIPTION"))
stopifnot(identical(unname(description[1L, "Package"]), "singscore"),
  identical(unname(description[1L, "Version"]), "1.32.0"))
dependencies <- trimws(gsub("\\s*\\([^)]*\\)", "", strsplit(description[1L, "Imports"], ",")[[1L]]))
BiocManager::install(dependencies, ask = FALSE, update = FALSE, Ncpus = 2L)
stopifnot(all(vapply(dependencies, requireNamespace, logical(1), quietly = TRUE)))
utils::install.packages(archive, repos = NULL, type = "source")
stopifnot(requireNamespace("singscore", quietly = TRUE),
  identical(as.character(utils::packageVersion("singscore")), "1.32.0"))
dir.create("/opt/autonomics", showWarnings = FALSE)
packages <- as.data.frame(utils::installed.packages()[, c("Package", "Version", "Built", "LibPath")], stringsAsFactors = FALSE)
packages <- packages[order(packages$Package, packages$LibPath), , drop = FALSE]
utils::write.table(packages, "/opt/autonomics/installed-packages.tsv", sep = "\t", quote = FALSE, row.names = FALSE)
writeLines(capture.output(utils::sessionInfo()), "/opt/autonomics/session-info.txt")
jsonlite::write_json(list(scope = "SOFTWARE_ENVIRONMENT_NOT_STUDY_ACCEPTANCE",
  R_version = as.character(getRversion()), singscore_version = as.character(utils::packageVersion("singscore")),
  source_sha256 = digest::digest(file = archive, algo = "sha256"),
  CRAN = cran, Bioconductor = Sys.getenv("BIOCONDUCTOR_RELEASE")),
  "/opt/autonomics/software-identity.json", auto_unbox = TRUE, pretty = TRUE)
unlink(scratch, recursive = TRUE)
