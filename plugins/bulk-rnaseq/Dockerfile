FROM ghcr.io/zj-2002/deseq2@sha256:b89a390ff6dad2dfbc8999d169655a6f5e8368b9aa8bb52bbbc3ade518d88b55

USER root
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MAKEFLAGS=-j2 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends libuv1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY source-archives /tmp/method-sources
COPY build-image.R /tmp/build-image.R
RUN cd /tmp/method-sources && sha256sum --check SHA256SUMS \
    && Rscript --vanilla /tmp/build-image.R core
RUN Rscript --vanilla /tmp/build-image.R dependencies
RUN Rscript --vanilla /tmp/build-image.R WGCNA
RUN Rscript --vanilla /tmp/build-image.R verify \
    && rm -rf /tmp/method-sources /tmp/build-image.R

COPY limma_voom_runner.R /opt/autonomics/limma_voom_runner.R
COPY wgcna_runner.R /opt/autonomics/wgcna_runner.R
COPY Rscript-vanilla /opt/autonomics/Rscript-vanilla
RUN chmod 0555 /opt/autonomics/limma_voom_runner.R /opt/autonomics/wgcna_runner.R
RUN chmod 0555 /opt/autonomics/Rscript-vanilla

LABEL org.opencontainers.image.title="autonomics-bulk-rnaseq" \
      org.opencontainers.image.version="1.0.3" \
      org.opencontainers.image.source="https://github.com/ZJ-2002/autonomics-plugins" \
      org.opencontainers.image.licenses="Artistic-2.0 OR GPL-2.0-or-later"

WORKDIR /work
ENTRYPOINT ["Rscript", "--vanilla"]
