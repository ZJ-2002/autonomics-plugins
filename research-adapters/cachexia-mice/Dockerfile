FROM localhost/cachexia-survey@sha256:8186f7fc9fa4a75023821b8f0f22634b82c2112916c426a20ee40075c4753243
ENV MAKEFLAGS=-j1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY runtime-debs/ /opt/cachexia-mice/runtime-debs/
RUN dpkg -i /opt/cachexia-mice/runtime-debs/*.deb
COPY sources/ /opt/cachexia-mice/sources/
RUN R CMD INSTALL /opt/cachexia-mice/sources/backports_1.5.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/broom_1.0.13.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/pan_2.0.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/rbibutils_2.4.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/Rdpack_2.6.6.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/nloptr_2.2.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/reformulas_0.4.4.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/lme4_2.0-6.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/ucminf_1.2.3.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/ordinal_2026.7-26.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/jomo_2.7-6.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/forcats_1.0.1.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/haven_2.5.5.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/mitml_0.4-5.tar.gz && \
    R CMD INSTALL /opt/cachexia-mice/sources/mice_3.19.0.tar.gz && \
    Rscript -e 'stopifnot(as.character(getRversion()) == "4.6.1", as.character(packageVersion("mice")) == "3.19.0")'

