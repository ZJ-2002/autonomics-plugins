# NicheNet official stack, tier-1 wrapper. License: GPL-3.0-only.
#
# Upstream has no LICENSE file (the grant lives in DESCRIPTION only), so the
# image carries the full GPL-3 text at /usr/share/licenses/COPYING.GPLv3.
# This repository (Dockerfile + install_packages.R + renv.lock + the pinned
# source tarball in vendor-src/) is the Corresponding Source for the image.
#
# Pins:
#   nichenetr f9906f3a51ddc09405a04ece9de375688e03facb (v2.2.0, 2024-09-05)
#   R 4.4.1 on ubuntu 22.04 (rocker/r-ver), CRAN deps from the Posit
#   Package Manager jammy BINARY snapshot 2024-10-01, Bioconductor-only
#   deps (ComplexHeatmap/rhdf5 chain) from Bioc 3.20 source.
#   Zenodo record 7074291 human priors, MD5-checked at build time; the
#   image digest therefore pins algorithm AND prior networks together.
FROM docker.io/rocker/r-ver:4.4.1

ARG http_proxy=
ARG https_proxy=
ARG no_proxy=localhost,127.0.0.1

ENV PPM_CRAN=https://packagemanager.posit.co/cran/__linux__/jammy/2024-10-01

# Build deps for the source-compiled Bioc packages + runtime libs that the
# PPM jammy binaries link against (cairo, png/jpeg/tiff, icu, freetype/
# harfbuzz/fribidi via ragg, xml/curl/ssl). libglpk40 is igraph's runtime:
# nichenetr Imports igraph, and PPM binary installs skip load tests, so a
# missing lib only explodes at first dlopen - nichenetr's lazy-load died on
# libglpk.so.40 once. readelf over every compiled dep (igraph 2.0.3 links
# glpk+xml2+BLAS/LAPACK only; nloptr vendors nlopt; ragg/textshaping/
# systemfonts need only libs already pulled by the -dev set) confirms glpk
# is the single soname outside the base image. geos/gdal/udunits
# deliberately absent: only sf (a Suggests) would need them.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      gfortran \
      ca-certificates \
      file \
      git \
      libcairo2-dev \
      libcurl4-openssl-dev \
      libfontconfig1-dev \
      libfreetype6-dev \
      libfribidi-dev \
      libglpk40 \
      libharfbuzz-dev \
      libicu-dev \
      libjpeg-turbo8-dev \
      libpng-dev \
      libssl-dev \
      libtiff5-dev \
      libxml2-dev \
      libxt-dev \
 && rm -rf /var/lib/apt/lists/*

# The whole R dependency tree + the commit-pinned official package.
# Writes /opt/autonomics/renv.lock (exported out and committed to the repo).
# Two layers (mirroring the cellchat plugin): the slow Bioc/HDF5 compile
# layer survives any hiccup in the fast nichenetr layer.
COPY install_packages.R /tmp/install_packages.R
RUN Rscript /tmp/install_packages.R bioc
RUN Rscript /tmp/install_packages.R nichenetr && rm -f /tmp/install_packages.R

# GPL-3 full text (upstream ships none) and the I/O-translation-only driver.
COPY LICENSES/GPL-3.0-only.txt /usr/share/licenses/COPYING.GPLv3
COPY driver.R /opt/autonomics/driver.R

# Official prior networks (Zenodo 7074291, human nsga2r set), MD5-gated:
# the build fails if any prior deviates from the Zenodo-published checksum.
COPY vendor/zenodo_checksums.md5 /opt/nichenetr/priors/checksums.md5
COPY vendor/ligand_target_matrix_nsga2r_final.rds \
     vendor/weighted_networks_nsga2r_final.rds \
     vendor/lr_network_human_21122021.rds \
     /opt/nichenetr/priors/
RUN cd /opt/nichenetr/priors && md5sum -c checksums.md5

WORKDIR /workdir
ENTRYPOINT ["Rscript", "/opt/autonomics/driver.R"]
