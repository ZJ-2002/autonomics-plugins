FROM ghcr.io/zj-2002/singscore-official@sha256:04981a66d7c3fc7055a185a0102dc9f337dd63381b676681c08e52e8c22e2ca5
USER root
ENV MAKEFLAGS=-j1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
COPY *.tar.gz SHA256SUMS /opt/frozen-sources/
RUN cd /opt/frozen-sources && sha256sum -c SHA256SUMS
RUN R CMD INSTALL --no-docs --no-html --no-demo /opt/frozen-sources/assorthead_1.6.3.tar.gz
RUN R CMD INSTALL --no-docs --no-html --no-demo /opt/frozen-sources/beachmat_2.28.0.tar.gz
RUN R CMD INSTALL --no-docs --no-html --no-demo /opt/frozen-sources/BiocNeighbors_2.6.0.tar.gz
RUN R CMD INSTALL --no-docs --no-html --no-demo /opt/frozen-sources/SingleCellExperiment_1.34.0.tar.gz
RUN R CMD INSTALL --no-docs --no-html --no-demo /opt/frozen-sources/UCell_2.16.0.tar.gz
RUN Rscript --vanilla -e 'stopifnot(as.character(packageVersion("UCell")) == "2.16.0"); library(UCell)'
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["Rscript", "--vanilla"]
