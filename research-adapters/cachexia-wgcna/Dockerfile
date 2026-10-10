FROM localhost/cachexia-limma@sha256:9f2926aac80ea63597d0fbcd640ecfa566e683d794842d9fb8cb6aa000acbe5c
USER root
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MAKEFLAGS=-j1
COPY runtime-debs /opt/cachexia-wgcna-runtime-debs
COPY system-lock.json /opt/cachexia-wgcna-system-lock.json
RUN cd /opt/cachexia-wgcna-runtime-debs && sha256sum -c SHA256SUMS && dpkg -i ./*.deb
COPY sources /opt/cachexia-wgcna-sources
COPY source-plan.json /opt/cachexia-wgcna-source-plan.json
COPY install.R /opt/cachexia-wgcna-install.R
RUN mkdir -p /opt/cachexia-wgcna-library && Rscript --vanilla /opt/cachexia-wgcna-install.R /opt/cachexia-wgcna-sources /opt/cachexia-wgcna-source-plan.json /opt/cachexia-wgcna-library
ENV R_LIBS_SITE=/opt/cachexia-wgcna-library:/usr/local/lib/R/site-library:/usr/lib/R/site-library
USER 65532:65532
LABEL org.opencontainers.image.licenses="GPL-2.0-or-later" org.opencontainers.image.version="WGCNA1.74"
