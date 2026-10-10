FROM ghcr.io/zj-2002/ldsc@sha256:93b2542386a08df10402045b8036ff4da6733bea65324d50e326d035579d247a
COPY official /opt/cachexia-official-ldsc
COPY cloudpickle-3.1.2-py3-none-any.whl /opt/cachexia-proof-dependencies/
RUN python -m pip install --no-index --no-deps --no-cache-dir /opt/cachexia-proof-dependencies/cloudpickle-3.1.2-py3-none-any.whl
ENV PYTHONPATH=/opt/cachexia-official-ldsc PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /work
ENTRYPOINT ["python", "/opt/cachexia-official-ldsc/ldsc.py"]
