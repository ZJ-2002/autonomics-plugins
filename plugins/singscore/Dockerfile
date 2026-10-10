FROM docker.io/rocker/r-ver:4.6.1

LABEL org.opencontainers.image.title="autonomics-singscore-official" \
  org.opencontainers.image.source="https://github.com/davidsigala/singscore" \
  org.opencontainers.image.license="GPL-3"

# singscore is the v4.0 B-SPEC main score (rankGenes + simpleScore path,
# plan section 5). Bioconductor release channel fixed at build time; the
# exact package version is asserted by stopifnot below and recorded in the
# manifest image block, mirroring how the seed1/MRlap environment froze
# versions rather than trusting floating tags.
ARG CRAN_SNAPSHOT=2026-09-13
ARG BIOC_VERSION=3.23
ARG SIGNSCORE_VERSION=1.32.0
ENV CRAN_SNAPSHOT=${CRAN_SNAPSHOT} \
    BIOC_VERSION=${BIOC_VERSION} \
    SIGNSCORE_VERSION=${SIGNSCORE_VERSION}

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl zlib1g-dev libgsl-dev \
  && rm -rf /var/lib/apt/lists/*

RUN Rscript -e 'options(repos = c(CRAN = sprintf("https://packagemanager.posit.co/cran/__linux__/noble/%s", Sys.getenv("CRAN_SNAPSHOT"))), HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(), paste(getRversion(), R.version$platform, R.version$arch, R.version$os))); install.packages("BiocManager"); BiocManager::install(version = Sys.getenv("BIOC_VERSION"), ask = FALSE, update = FALSE, sites = c(BioC = sprintf("https://bioconductor.org/packages/%s/bioc", Sys.getenv("BIOC_VERSION")))); BiocManager::install("singscore", ask = FALSE, update = FALSE)'

RUN Rscript -e 'stopifnot(packageVersion("singscore") == Sys.getenv("SIGNSCORE_VERSION")); library(singscore); data(gseVizData); cat("singscore environment OK:", as.character(packageVersion("singscore")), "\n")'

WORKDIR /work

ENTRYPOINT ["Rscript"]
