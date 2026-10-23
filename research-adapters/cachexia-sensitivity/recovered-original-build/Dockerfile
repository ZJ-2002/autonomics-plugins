FROM localhost/cachexia-lcmm@sha256:602bbf79fa81124edc1d78f366a71e2f8e55f1c768377810104eb81bb03ac97a
ENV MAKEFLAGS=-j1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libfftw3-dev && rm -rf /var/lib/apt/lists/*
COPY sources/ /opt/cachexia-sensitivity/sources/
RUN R CMD INSTALL /opt/cachexia-sensitivity/sources/mathjaxr_2.0-0.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/metadat_1.6-0.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/metafor_5.2-1.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/MetaUtility_2.1.2.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/EValue_4.1.4.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/SparseM_1.84-2.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/MatrixModels_0.5-4.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/quantreg_6.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/sn_2.1.3.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/TFisher_0.2.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/DEoptimR_1.2-2.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/robustbase_0.99-7.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/qqconf_1.3.2.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/plotrix_3.8-14.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/BiocGenerics_0.58.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/Biobase_2.72.0.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/multtest_2.68.0.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/TH.data_1.1-5.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/zoo_1.9-1.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/sandwich_3.1-3.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/multcomp_1.4-32.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/mutoss_0.1-14.tar.gz && \
    R CMD INSTALL /opt/cachexia-sensitivity/sources/metap_1.14.tar.gz && \
    Rscript -e 'library(EValue);library(metap);stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("EValue"))=="4.1.4",as.character(packageVersion("metap"))=="1.14")'
