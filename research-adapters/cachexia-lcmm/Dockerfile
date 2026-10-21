FROM localhost/cachexia-mice@sha256:0a7b397b9fb5fca8128381525ab9482098445a2f29e309135464a8cd45fc0f57
ENV MAKEFLAGS=-j1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY sources/ /opt/cachexia-lcmm/sources/
RUN R CMD INSTALL /opt/cachexia-lcmm/sources/mvtnorm_1.4-2.tar.gz && \
    R CMD INSTALL /opt/cachexia-lcmm/sources/spacefillr_0.4.0.tar.gz && \
    R CMD INSTALL /opt/cachexia-lcmm/sources/marqLevAlg_2.0.8.tar.gz && \
    R CMD INSTALL /opt/cachexia-lcmm/sources/lcmm_2.2.2.tar.gz && \
    Rscript -e 'stopifnot(as.character(getRversion()) == "4.6.1", as.character(packageVersion("lcmm")) == "2.2.2", as.character(packageVersion("marqLevAlg")) == "2.0.8")'
