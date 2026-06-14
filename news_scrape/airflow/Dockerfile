FROM apache/airflow:2.10.2-python3.12

# Cài các gói system cần thiết dưới quyền root
# USER root
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential gcc g++ libffi-dev libxml2-dev libxslt1-dev \
#     python3-dev curl \
#  && apt-get clean \
#  && rm -rf /var/lib/apt/lists/*

# Quay lại user airflow trước khi cài pip packages
USER airflow
WORKDIR /opt/airflow

# Copy requirements và cài bằng airflow user
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm
RUN mkdir -p /opt/airflow/hf_cache

# Set PYTHONPATH
ENV PYTHONPATH="/opt/airflow:${PYTHONPATH}"

# Copy source code
COPY airflow/dags /opt/airflow/dags
COPY airflow/scripts /opt/airflow/scripts
COPY mongo /opt/airflow/mongo
COPY producer /opt/airflow/producer
COPY scraper /opt/airflow/scraper
COPY utils /opt/airflow/utils
COPY config /opt/airflow/config
COPY ner_model /opt/airflow/ner_model
COPY hooks /opt/airflow/hooks
COPY .env /opt/airflow
