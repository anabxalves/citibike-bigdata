# ============================================================
# CitiBike BigData — Jupyter + PySpark + Delta Lake
# Base: jupyter/pyspark-notebook (Spark 3.5, Java 17, Python 3.11)
# ============================================================
FROM jupyter/pyspark-notebook:latest

USER root
RUN apt-get update --quiet && \
    apt-get install -y --no-install-recommends curl wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER ${NB_UID}

RUN pip install --no-cache-dir \
    delta-spark==3.2.0 \
    pyarrow \
    pandas \
    requests \
    holidays \
    tqdm \
    openmeteo-requests \
    requests-cache \
    retry-requests \
    matplotlib \
    seaborn \
    jupyterlab-git

WORKDIR /home/jovyan/work