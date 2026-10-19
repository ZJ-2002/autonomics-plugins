FROM ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d

LABEL org.opencontainers.image.title="autonomics-ieugwasr-official" \
      org.opencontainers.image.source="https://github.com/MRCIEU/ieugwasr" \
      org.opencontainers.image.version="1.2.0" \
      org.opencontainers.image.revision="0c5b4cc6bc5e675afe222262950c8bb488f8d2f3"

ENV R_LIBS_USER=/opt/ieugwasr-library \
    R_ENABLE_JIT=0

COPY runtime/ /opt/autonomics-ieugwasr-runtime/
COPY runtime-source-lock.json /opt/autonomics-ieugwasr-runtime/runtime-source-lock.json

RUN set -eu; \
    cd /opt/autonomics-ieugwasr-runtime; \
    printf '%s\n' '1f35bc50083dae44c7a0284f833f437d887cb4641297431847b8f6f9ebea2084  SHA256SUMS' | sha256sum -c -; \
    test "$(find ieugwasr -type f | wc -l)" -eq 13; \
    test -z "$(find ieugwasr -type l -print)"; \
    sha256sum -c SHA256SUMS; \
    Rscript --vanilla -e 'stopifnot(as.character(getRversion())=="4.6.1",as.character(utils::packageVersion("ieugwasr"))=="1.1.0"); imports <- c("dplyr","httr","jsonlite","magrittr","stats"); stopifnot(all(vapply(imports,requireNamespace,logical(1),quietly=TRUE))); jsonlite::write_json(setNames(lapply(imports,function(name)as.character(utils::packageVersion(name))),imports),"base-dependency-versions.json",auto_unbox=TRUE,pretty=TRUE)'; \
    mkdir -p /opt/ieugwasr-library; \
    R CMD INSTALL --no-docs --no-help --no-demo --library=/opt/ieugwasr-library ieugwasr; \
    Rscript --vanilla -e 'stopifnot(as.character(utils::packageVersion("ieugwasr"))=="1.2.0",normalizePath(find.package("ieugwasr"))=="/opt/ieugwasr-library/ieugwasr"); namespace <- asNamespace("ieugwasr"); methods <- c("associations","phewas","tophits","variants_rsid","variants_chrpos","ld_clump_api","gwasinfo"); stopifnot(all(vapply(methods,function(name)is.function(get(name,namespace,inherits=FALSE)),logical(1)))); jsonlite::write_json(list(R=as.character(getRversion()),ieugwasr=as.character(utils::packageVersion("ieugwasr")),library=find.package("ieugwasr"),R_ENABLE_JIT=Sys.getenv("R_ENABLE_JIT"),methods=methods),"installed-package-identity.json",auto_unbox=TRUE,pretty=TRUE)'

WORKDIR /work
ENTRYPOINT ["Rscript"]
