#!/usr/bin/env Rscript
# SPDX-License-Identifier: GPL-3.0-only
#
# Install the OFFICIAL NicheNet stack for the tier-1 container. Two stages,
# run as separate Docker layers (mirroring the cellchat sibling plugin) so
# the slow Bioc layer (Rhdf5lib bundles and builds its own HDF5, ~15 min)
# survives any hiccup in the fast nichenetr layer:
#
#   Rscript install_packages.R bioc      # tooling + Bioc 3.20 source packages
#   Rscript install_packages.R nichenetr # nichenetr from the pinned GitHub commit
#
# Pin: nichenetr @ f9906f3a51ddc09405a04ece9de375688e03facb (tag v2.2.0,
# 2024-09-05; GitHub-only, no CRAN/Bioc release).
#
# Dependency strategy
#   - CRAN packages: Posit Package Manager jammy BINARY snapshot 2024-10-01
#     (era-consistent with the pin; still carries the since-archived mlr /
#     ParamHelpers that mlrMBO hard-Depends on). Binaries need no
#     compilation and link against jammy system libs.
#   - Bioconductor-only packages (ComplexHeatmap for nichenetr's Imports,
#     rhdf5 for the driver's h5ad reader): PPM's CRAN snapshots carry no
#     Bioc packages and this PPM server exposes no /bioc/ path, so they
#     come from bioconductor.org source pinned to Bioc 3.20 (released
#     2024-10-30, the R 4.4.x Bioc line; same pin as the cellchat sibling
#     plugin). Rhdf5lib bundles its own HDF5.
#   - Suggests are NOT installed (no sf/limma/mco/...).
#   - mco is only a Suggests of mlrMBO and not needed.
#
# The installed package is 'Rhdf5lib' (capital R): packageVersion() is
# case-sensitive on Linux; a lowercase query halted a whole build once.

options(
  repos = c(CRAN = Sys.getenv("PPM_CRAN", "https://packagemanager.posit.co/cran/__linux__/jammy/2024-10-01")),
  # PPM serves linux binaries only when the UA advertises R version+platform.
  HTTPUserAgent = sprintf(
    "R/%s R (%s)",
    getRversion(),
    paste(getRversion(), R.version[["platform"]], R.version[["arch"]], R.version[["os"]])
  ),
  Ncpus = 4,
  timeout = 600
)

cat("install: R", as.character(getRversion()), "\n")
cat("install: repo:", getOption("repos")[["CRAN"]], "\n")

fail <- function(...) {
  message("install: FATAL ", paste0(...))
  quit(save = "no", status = 1L)
}

pkgver <- function(pkg) as.character(packageVersion(pkg))

stage <- commandArgs(trailingOnly = TRUE)[[1]]

if (stage == "bioc") {
  # --- tooling (remotes for the GitHub pin, renv for the lockfile) ----------
  install.packages(c("remotes", "renv", "jsonlite"))
  if (!requireNamespace("remotes", quietly = TRUE)) fail("remotes install failed")

  # Sanity: confirm PPM really serves us binaries (compiled pkg with libs/).
  # PPM content-negotiates by User-Agent: the src/contrib PACKAGES index
  # lists the prebuilt tarballs for a matching linux R. If this canary
  # fails, every CRAN dep would compile from source - fail fast instead.
  install.packages("stringi")
  if (!file.exists(system.file("libs", package = "stringi"))) {
    fail("PPM served stringi as SOURCE (no libs/); check HTTPUserAgent")
  }
  cat("install: PPM binary canary OK (stringi has compiled libs)\n")

  # --- Bioconductor-only deps ----------------------------------------------
  # BiocManager is NOT used: its version-switch validator rejects the mixed
  # PPM-snapshot + Bioc state ("first downgrade 8 packages"). Plain
  # install.packages with a second named repo resolves each dependency from
  # wherever it lives: CRAN deps as PPM binaries, Bioc deps as Bioc source.
  options(repos = c(getOption("repos"),
                    BioC = "https://bioconductor.org/packages/3.20/bioc"))
  install.packages(c("ComplexHeatmap", "rhdf5"))
  for (p in c("ComplexHeatmap", "rhdf5", "Rhdf5lib", "rhdf5filters")) {
    if (!requireNamespace(p, quietly = TRUE)) fail(p, " install failed")
  }
  cat("install: ComplexHeatmap", pkgver("ComplexHeatmap"),
      "; rhdf5", pkgver("rhdf5"),
      "; Rhdf5lib", pkgver("Rhdf5lib"),
      "; rhdf5filters", pkgver("rhdf5filters"), "\n")
  quit(save = "no", status = 0L)
}

if (stage == "nichenetr") {
  # --- the official package, GitHub-only, commit-pinned ---------------------
  # BioC named repo again so install_github resolves ComplexHeatmap from 3.20.
  options(repos = c(getOption("repos"),
                    BioC = "https://bioconductor.org/packages/3.20/bioc"))
  Sys.setenv(R_REMOTES_UPGRADE = "never")
  # install_github builds nichenetr at the END, after ~250 binary deps; its
  # lazy-load is the first dlopen of many of those deps (PPM binaries skip
  # load tests). If a SYSTEM lib is missing, catch the error here and ldd-
  # sweep the whole library so ONE build failure lists EVERY unresolved
  # soname, instead of the next one surprising the next build.
  gh_error <- tryCatch(
    { remotes::install_github(
        "saeyslab/nichenetr@f9906f3a51ddc09405a04ece9de375688e03facb",
        upgrade = "never",
        dependencies = c("Depends", "Imports", "LinkingTo")  # never Suggests
      ); NULL },
    error = function(e) conditionMessage(e)
  )

  sos <- list.files(.libPaths()[[1]], pattern = "\\.so$",
                    recursive = TRUE, full.names = TRUE)
  missing <- character()
  for (f in sos) {
    o <- suppressWarnings(system2("ldd", shQuote(f), stdout = TRUE, stderr = FALSE))
    m <- grep("not found", o, fixed = TRUE, value = TRUE)
    if (length(m)) {
      pkg <- basename(dirname(dirname(f)))
      missing <- c(missing, paste0(pkg, ": ", trimws(m)))
    }
  }
  cat("install: ldd sweep:", length(sos), "shared objects,", length(missing), "unresolved\n")
  if (length(missing)) {
    cat("install: MISSING SYSTEM LIBS (add to apt layer):\n")
    cat(paste0("  ", missing, collapse = "\n"), "\n", sep = "")
    fail("unresolved shared libraries listed above")
  }
  if (!is.null(gh_error)) fail("install_github failed: ", gh_error)

  suppressPackageStartupMessages(library(nichenetr))
  ver <- pkgver("nichenetr")
  cat("install: nichenetr version:", ver, "\n")
  if (ver != "2.2.0") fail("expected nichenetr 2.2.0, got ", ver)

  sha <- packageDescription("nichenetr")$RemoteSha
  if (is.null(sha)) sha <- "<absent>"
  if (!identical(sha, "f9906f3a51ddc09405a04ece9de375688e03facb")) {
    cat("install: WARNING RemoteSha is", sha, "\n")
  }

  # --- renv lockfile: the full resolved library, for reproducibility -------
  dir.create("/opt/autonomics", recursive = TRUE, showWarnings = FALSE)
  renv::snapshot(
    library = .libPaths()[[1]],
    lockfile = "/opt/autonomics/renv.lock",
    type = "all",
    prompt = FALSE,
    force = TRUE
  )
  cat("install: renv.lock written to /opt/autonomics/renv.lock\n")
  cat("install: library size (packages):", nrow(installed.packages()), "\n")
  quit(save = "no", status = 0L)
}

fail("usage: Rscript install_packages.R bioc|nichenetr")
