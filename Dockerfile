FROM apache/airflow:2.9.2

USER root
COPY requirements.txt /requirements.txt
RUN chown airflow: /requirements.txt

USER airflow
RUN pip install --no-cache-dir -r /requirements.txt

