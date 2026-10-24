FROM apache/airflow:3.3.2-python3.13

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir \
    "apache-airflow==3.3.2" \
    -r /tmp/requirements.txt

WORKDIR /opt/airflow/project