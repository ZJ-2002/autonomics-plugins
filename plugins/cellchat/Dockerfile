# CellChat official stack, tier-① wrapper (GPL-3; source provision = this
# repo: Dockerfile + vendored upstream tarball at the pinned commit, see
# vendor/cellchat-75253cd0.tar.gz, sha256 recorded in /opt/autonomics/source.sha256).
# The image digest pins the official algorithm (jinworks/CellChat@75253cd0)
# AND the embedded CellChatDB (LazyData inside the package, zero runtime
# downloads) together; every run writes cellchat_provenance.json recording
# versions, DB version and parameters.
#
# Base: rocker/r-ver 4.4.1 = Ubuntu 22.04 (jammy) + R 4.4.1, ships the Posit
# Package Manager jammy binary repo by default. Chosen over
# bioconductor/bioconductor_docker:RELEASE_3_20 (~6GB, hundreds of Bioc
# packages we never load) — this base is 854MB and PPM gives precompiled
# binaries for every CRAN dep; only the four needed Bioc 3.20 packages and
# CellChat itself compile from source, once, at build time.
FROM docker.io/rocker/r-ver:4.4.1

ARG http_proxy=
ARG https_proxy=
ARG no_proxy=localhost,127.0.0.1

# Toolchain + dev headers: needed to compile the four Bioc source packages
# and CellChat's (tiny) Rcpp/RcppEigen src; PPM binaries link against the
# runtime libs the base image already ships.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      libcurl4-openssl-dev \
      libssl-dev \
      libxml2-dev \
      libicu-dev \
      libfontconfig1-dev \
      libfreetype6-dev \
      libpng-dev \
      libtiff-dev \
      libjpeg-dev \
      libharfbuzz-dev \
      libfribidi-dev \
      libbz2-dev \
      liblzma-dev \
      libzstd-dev \
      zlib1g-dev \
      libglpk-dev \
 && rm -rf /var/lib/apt/lists/*

COPY install-deps.R /opt/autonomics/install-deps.R
COPY vendor/cellchat-75253cd0.tar.gz /opt/src/cellchat-75253cd0.tar.gz
COPY vendor/presto-b5df6ee6.tar.gz /opt/src/presto-b5df6ee6.tar.gz

RUN mkdir -p /opt/autonomics /opt/src \
 && Rscript /opt/autonomics/install-deps.R bioc

RUN Rscript /opt/autonomics/install-deps.R cellchat \
 && sha256sum /opt/src/cellchat-75253cd0.tar.gz /opt/src/presto-b5df6ee6.tar.gz \
      > /opt/autonomics/source.sha256 \
 && rm /opt/src/cellchat-75253cd0.tar.gz /opt/src/presto-b5df6ee6.tar.gz \
 && cat /opt/autonomics/source.sha256

# GPL-3 full text (verbatim from the upstream repo's own LICENSE file).
COPY vendor/COPYING.GPLv3 /usr/share/licenses/COPYING.GPLv3

# Driver: I/O translation only — feeds engine h5ad to the official pipeline.
COPY driver.R /opt/autonomics/driver.R

WORKDIR /workdir
ENTRYPOINT ["Rscript", "/opt/autonomics/driver.R"]
