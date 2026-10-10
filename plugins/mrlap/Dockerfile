FROM docker.io/rocker/r-ver:4.6.1

LABEL org.opencontainers.image.title="autonomics-mrlap-official" \
  org.opencontainers.image.version="0.0.3.3" \
  org.opencontainers.image.source="https://github.com/n-mounier/MRlap" \
  org.opencontainers.image.license="GPL-3" \
  org.opencontainers.image.revision="660f026864f8bfbbad5a8206bdff7d58f5d5d05b"

# CRAN snapshot for the transitive dependency layer. The three method
# packages are pinned by exact git commit below (CRAN no longer carries
# TwoSampleMR/GenomicSEM/MRlap); snapshot choice only fixes the support
# stack (dplyr/ggplot2/lavaan/...). 2026-09-13 is the snapshot the
# twosamplemr family image was built against, keeping the two families'
# support stacks comparable.
ARG CRAN_SNAPSHOT=2026-09-13
ARG MRLAP_SHA256=42e74c0cd7b2dd071ef67fb8921bc2c1d8ace4bc8e5526c61feb8d8647c0a1cf
ARG TWOSAMPLEMR_SHA256=a203d74170d58e9424fc21dd8d2dc00f9bc017ae90e4c75db136c26daddfda3a
ARG GENOMICSEM_SHA256=cf5f1a7f2ba2fd74a586734fe2138c9f3d88d5a4a73319bb20b736501dbdcaaa
ARG MRMIX_SHA256=b8847e5f57311dc5335461e4e1fcee13c832ff03f26f53819746bf292709d8b6
ARG RADIALMR_SHA256=71216b4a1a8827a3f2dd6322c72db4f490793e861df0d626f0bf4e189a524ea5
ARG MRPRESSO_SHA256=8bee27809fdf2ab69e549d08db0ff914d1af80f16119973c56f98c07f54f8728

ENV CRAN_SNAPSHOT=${CRAN_SNAPSHOT}

WORKDIR /tmp/source

RUN Rscript -e 'options(repos = c(CRAN = sprintf("https://packagemanager.posit.co/cran/__linux__/noble/%s", Sys.getenv("CRAN_SNAPSHOT"))), HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(), paste(getRversion(), R.version$platform, R.version$arch, R.version$os))); install.packages(c("cli", "cowplot", "data.table", "dplyr", "ggplot2", "glmnet", "gridExtra", "gtable", "ieugwasr", "jsonlite", "knitr", "lattice", "magrittr", "MASS", "pbapply", "plotly", "psych", "rmarkdown", "tidyr", "tidyselect", "rlang", "stringr", "tibble", "plyr", "e1071", "readr", "gdata", "lavaan", "doParallel", "foreach", "iterators", "splitstackshape", "R.utils", "mgsub", "simsalapar", "Rcpp", "Matrix", "stringi"))'

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

# Kernel parity with the frozen host acceptance environment: the host ran
# reference BLAS/LAPACK 3.12.0 single-threaded (/usr/lib/libblas.so.3.12.0
# in R_environment_after.txt), while rocker defaults to OpenBLAS-pthread.
# OpenBLAS shifted the two bootstrap-aggregate columns (corrected SE/P) by
# ~1e-9/1e-8 against the host reference on the first container parity,
# bit-identical seed behaviour excluded the RNG as the cause. Switching
# the alternatives pins the same numerical kernel, making the 51-field
# host-vs-container comparison strict instead of tolerance-based.
RUN update-alternatives --set libblas.so.3-x86_64-linux-gnu /usr/lib/x86_64-linux-gnu/blas/libblas.so.3 \
  && update-alternatives --set liblapack.so.3-x86_64-linux-gnu /usr/lib/x86_64-linux-gnu/lapack/liblapack.so.3 \
  && Rscript -e 'writeLines(unname(sessionInfo()$BLAS))'

# Method packages pinned to the exact commits the frozen host acceptance
# environment recorded (R_environment_after.txt RemoteSha fields of the
# seed1 acceptance library /home/zj-normal/R/library): MRlap @660f026 =
# the acceptance-recorded RemoteSha; TwoSampleMR @d4df219 (0.7.11) and
# GenomicSEM @da95d431 (0.0.5) = host install provenance. MRMix/RadialMR/
# MRPRESSO reuse the commits the twosamplemr family image pins; the host
# RemoteSha fields agree for MRMix and MRPRESSO. ieugwasr stays on the CRAN
# snapshot (host library carries 1.1.0 exactly like this snapshot).
RUN set -eux; \
  curl -fsSL https://codeload.github.com/gqi/MRMix/tar.gz/56afdb2bc96760842405396f5d3f02e60e305039 -o MRMix.tar.gz; \
  echo "${MRMIX_SHA256}  MRMix.tar.gz" > checksums; \
  curl -fsSL https://codeload.github.com/WSpiller/RadialMR/tar.gz/a30ff117fbfb6733ecdad0d69b8f5dd07958ed47 -o RadialMR.tar.gz; \
  echo "${RADIALMR_SHA256}  RadialMR.tar.gz" >> checksums; \
  curl -fsSL https://codeload.github.com/rondolab/MR-PRESSO/tar.gz/3e3c92d7eda6dce0d1d66077373ec0f7ff4f7e87 -o MRPRESSO.tar.gz; \
  echo "${MRPRESSO_SHA256}  MRPRESSO.tar.gz" >> checksums; \
  curl -fsSL https://codeload.github.com/GenomicSEM/GenomicSEM/tar.gz/da95d431a4709693d07eae55e172ade55526948b -o GenomicSEM.tar.gz; \
  echo "${GENOMICSEM_SHA256}  GenomicSEM.tar.gz" >> checksums; \
  curl -fsSL https://codeload.github.com/MRCIEU/TwoSampleMR/tar.gz/d4df21929fdabeb2f89686ffaad0db5f56973d64 -o TwoSampleMR.tar.gz; \
  echo "${TWOSAMPLEMR_SHA256}  TwoSampleMR.tar.gz" >> checksums; \
  curl -fsSL https://codeload.github.com/n-mounier/MRlap/tar.gz/660f026864f8bfbbad5a8206bdff7d58f5d5d05b -o MRlap.tar.gz; \
  echo "${MRLAP_SHA256}  MRlap.tar.gz" >> checksums; \
  sha256sum -c checksums; \
  Rscript -e 'install.packages(c("MRMix.tar.gz", "RadialMR.tar.gz", "MRPRESSO.tar.gz", "GenomicSEM.tar.gz", "TwoSampleMR.tar.gz", "MRlap.tar.gz"), repos = NULL, type = "source", INSTALL_opts = "--no-build-vignettes")'; \
  rm -f *.tar.gz checksums

RUN Rscript -e 'stopifnot(packageVersion("MRlap") == "0.0.3.3"); stopifnot(packageVersion("TwoSampleMR") == "0.7.11"); stopifnot(packageVersion("GenomicSEM") == "0.0.5"); suppressMessages(library(MRlap)); suppressMessages(library(TwoSampleMR)); suppressMessages(library(GenomicSEM)); cat("mrlap-official environment OK\n")'

WORKDIR /work

ENTRYPOINT ["Rscript"]
