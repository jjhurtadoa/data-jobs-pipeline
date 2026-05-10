FROM apache/airflow:2.10.3-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow
ENV PATH="/home/airflow/.local/bin:${PATH}"
WORKDIR /opt/airflow

COPY airflow/requirements-airflow.txt /opt/airflow/requirements-airflow.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements-airflow.txt