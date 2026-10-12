FROM docker.io/rocker/r-ver@sha256:268e4c559c905a78519793f1a8c9ec5c8051a6ac98a16cbf489135ccdad330bb

# Official R 4.6.1, independently admitted by digest. The build context must
# include the exact Bioconductor archive specified below. Acquisition is a
# separate stage; the frozen scientific runtime never installs packages.
LABEL org.opencontainers.image.title="autonomics-singscore-contract" \
      org.opencontainers.image.description="Official singscore with frozen scoring and donor contrast adapters; study qualification separate" \
      org.opencontainers.image.licenses="GPL-3.0-only"

ENV CRAN_SNAPSHOT=2026-09-13 \
    BIOCONDUCTOR_RELEASE=3.23 \
    R_PROFILE_USER=/dev/null \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

# XVector (and its downstream GSEABase dependencies) compiles against zlib.
# This is a build dependency; the pinned image captures the resolved packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY singscore_1.32.0.tar.gz /opt/autonomics-source/singscore_1.32.0.tar.gz
RUN printf '%s\n' 'b4ffcbcb215ec99b9c8159bcf47cebba02517ff2c76c6aebabd2d7848298fd5a  /opt/autonomics-source/singscore_1.32.0.tar.gz' | sha256sum -c -
COPY scripts/install-environment.R /opt/autonomics-source/install-environment.R
RUN Rscript --vanilla /opt/autonomics-source/install-environment.R

COPY scripts/score.R scripts/contrasts.R /opt/autonomics/
RUN chmod 0555 /opt/autonomics/*.R \
    && groupadd --gid 1000 autonomics \
    && useradd --uid 1000 --gid autonomics --no-create-home autonomics

ENV HOME=/tmp XDG_CACHE_HOME=/tmp/cache
USER 1000:1000
WORKDIR /work
# Manifest commands choose score.R or contrasts.R explicitly. Avoid a hidden
# image entrypoint which changes the plugin's recorded interpreter/argv.
ENTRYPOINT []
CMD ["Rscript", "--vanilla", "-e", "stop('explicit frozen method command required')"]
