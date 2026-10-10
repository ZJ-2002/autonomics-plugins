FROM python:3.9-slim-bookworm

LABEL org.opencontainers.image.title="autonomics-ldsc-original" \
  org.opencontainers.image.version="3.0.1" \
  org.opencontainers.image.source="file:///mnt/disk3/ldsc3/ldsc"

RUN python -m pip install --no-cache-dir \
    numpy==1.23.3 \
    pandas==1.5.0 \
    scipy==1.9.2 \
    bitarray==2.6.0

WORKDIR /opt/ldsc

COPY ldsc.py munge_sumstats.py ./
COPY ldscore/ ./ldscore/

# LDSC 3.0.1 filters incompatible allele pairs but passes the pre-filter
# allele Series to alignment, so any rejected row still raises KeyError.
# The original build context (/mnt/disk3/ldsc3/ldsc, pristine upstream)
# is not portable; the vendored ldsc-python3/ tree already carries the
# fix in refactored naming (filter_alleles/select_and_log, no leading
# underscore, merged_sumstats instead of loop). Assert the fixed form so
# a code drift that regresses the allele-index fix still fails the build.
RUN python - <<'PY'
from pathlib import Path

path = Path("/opt/ldsc/ldscore/sumstats.py")
text = path.read_text()
fixed = """\
        valid_indices = filter_alleles(alleles)
        merged_sumstats = select_and_log(merged_sumstats, valid_indices, logger, "{N} SNPs with valid alleles.")
        merged_sumstats["Z2"] = align_alleles(
            merged_sumstats.Z2, alleles[valid_indices]
        )
"""
if fixed not in text:
    raise SystemExit("fixed LDSC 3.0.1 allele-filter block was not found")
PY

RUN chmod +x /opt/ldsc/ldsc.py /opt/ldsc/munge_sumstats.py \
  && ln -s /opt/ldsc/ldsc.py /usr/local/bin/ldsc \
  && ln -s /opt/ldsc/munge_sumstats.py /usr/local/bin/munge_sumstats

ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/opt/ldsc

WORKDIR /work

ENTRYPOINT ["ldsc"]
