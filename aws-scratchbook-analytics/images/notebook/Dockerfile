# Scratchbook notebook image: JupyterLab + PySpark + Iceberg + AWS
# Build: docker build -t REPLACE_ECR_REPO/scratchbook-notebook:1.0.0 .
# Push to ECR and set jupyterhub/values.yaml singleuser.image

FROM jupyter/pyspark-notebook:spark-3.5.1

USER root

ENV SPARK_HOME=/usr/local/spark \
    SPARK_CONF_DIR=/opt/spark/conf \
    ICEBERG_VERSION=1.5.2 \
    HADOOP_AWS_VERSION=3.3.4 \
    AWS_SDK_VERSION=1.12.262

RUN mkdir -p /opt/spark/conf /opt/scratchbook /shared/examples \
    && chown -R ${NB_UID}:${NB_GID} /opt/spark /opt/scratchbook

# Iceberg + S3A jars into Spark
RUN curl -fsSL -o ${SPARK_HOME}/jars/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar \
      https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar \
    && curl -fsSL -o ${SPARK_HOME}/jars/hadoop-aws-${HADOOP_AWS_VERSION}.jar \
      https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar \
    && curl -fsSL -o ${SPARK_HOME}/jars/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar \
      https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar

COPY spark-defaults.conf.template /opt/scratchbook/spark-defaults.conf.template
COPY spark-defaults.conf.template /opt/spark/conf/spark-defaults.conf
COPY start-spark-session.py /opt/scratchbook/start-spark-session.py
COPY requirements.txt /tmp/requirements.txt

USER ${NB_UID}

RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONPATH="/opt/scratchbook:${PYTHONPATH}" \
    PYSPARK_DRIVER_PYTHON=jupyter \
    PYSPARK_DRIVER_PYTHON_OPTS=lab
