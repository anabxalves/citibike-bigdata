# ============================================================
# CitiBike BigData — Jupyter + PySpark + Delta Lake
# Base: jupyter/pyspark-notebook (Spark 3.5, Java 17, Python 3.11)
# ============================================================
FROM jupyter/pyspark-notebook:spark-3.5.2

USER root

# Dependências de sistema (caso precise de wget/curl para dados extras)
RUN apt-get update --quiet && \
    apt-get install -y --no-install-recommends curl wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER ${NB_UID}

# Instalar pacotes Python do projeto
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

# Diretório de trabalho — notebooks usam Path(os.getcwd()).parent para achar dados/
WORKDIR /home/jovyan/work
