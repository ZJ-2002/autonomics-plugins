# Source candidate only: build/measure a child before changing any adapter manifest.
FROM ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d

USER root
# Only Python transport is added. Refuse any R package/version or numerical
# runtime change; no install.packages(), R update, BLAS change or apt upgrade.
RUN set -eu; \
    Rscript --vanilla -e 'stopifnot(as.character(getRversion()) == "4.6.1", as.character(utils::packageVersion("stats")) == "4.6.1"); saveRDS(utils::installed.packages()[,c("Package","Version"),drop=FALSE], "/tmp/official-r-packages.rds"); writeLines(normalizePath(c(file.path(R.home("lib"),"libR.so"),system.file("libs",paste0("stats",.Platform$dynlib.ext),package="stats"),utils::sessionInfo()$BLAS,La_library()),mustWork=TRUE),"/tmp/official-r-runtime.paths")'; \
    xargs -d '\n' sha256sum < /tmp/official-r-runtime.paths > /tmp/official-r-runtime.sha256; \
    apt-get update; \
    apt-get install -y --no-install-recommends --no-upgrade python3-minimal; \
    sha256sum -c /tmp/official-r-runtime.sha256; \
    Rscript --vanilla -e 'stopifnot(as.character(getRversion()) == "4.6.1", as.character(utils::packageVersion("stats")) == "4.6.1", identical(utils::installed.packages()[,c("Package","Version"),drop=FALSE],readRDS("/tmp/official-r-packages.rds")))'; \
    python3 -I -S -c 'import sys,decimal,hashlib,json,math,os,pathlib,re,shutil,subprocess,tempfile; assert sys.version_info >= (3,8)'; \
    rm -rf /var/lib/apt/lists/* /tmp/official-r-packages.rds /tmp/official-r-runtime.paths /tmp/official-r-runtime.sha256
