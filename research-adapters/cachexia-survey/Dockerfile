FROM localhost/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434
ENV MAKEFLAGS=-j1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY sources/ /opt/cachexia-survey/sources/
RUN R CMD INSTALL /opt/cachexia-survey/sources/DBI_1.3.0.tar.gz && \
    R CMD INSTALL /opt/cachexia-survey/sources/mitools_2.7.tar.gz && \
    R CMD INSTALL /opt/cachexia-survey/sources/minqa_1.2.8.tar.gz && \
    R CMD INSTALL /opt/cachexia-survey/sources/RcppArmadillo_15.6.0-1.tar.gz && \
    R CMD INSTALL /opt/cachexia-survey/sources/survey_4.5.tar.gz && \
    Rscript -e 'stopifnot(as.character(getRversion()) == "4.6.1", as.character(packageVersion("survey")) == "4.5")'
