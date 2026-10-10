FROM docker.io/library/python@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83
ENV PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0
COPY wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --no-deps --find-links=/wheels numpy==2.5.3 scipy==1.18.1 pyarrow==25.0.1 && python -c "import scipy,numpy,pyarrow; assert (scipy.__version__,numpy.__version__,pyarrow.__version__)==('1.18.1','2.5.3','25.0.1')"
