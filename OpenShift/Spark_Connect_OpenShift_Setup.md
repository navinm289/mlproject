# Apache Spark Connect on OpenShift: Replication Guide

**Last updated:** 2026-11-09  
**Repository topic:** OpenShift / Apache Spark / PySpark  
**Status:** Reference procedure based on colleague screenshots; not yet validated in the user's namespace

> **Security:** All examples below use placeholders. Never commit real OpenShift API hostnames, internal image registry addresses, Vault roles, Kerberos keytabs/principals, AWS account IDs, KMS key IDs, credentials, or private infrastructure URLs to this repository. Follow enterprise approval and change-management requirements.

## 1. What the colleague is doing

The colleague starts an Apache Spark Connect server on **Spark 3.5.8** with a Kubernetes **cluster-mode spark-submit** in OpenShift. The driver pod hosts the Spark Connect gRPC endpoint on port **15050**. A developer uses the OpenShift CLI to forward that port to **localhost:15050**, then runs local Python with the PySpark Connect client using **sc://localhost:15050**.

This is **open-source Spark Connect on OpenShift, not Databricks Connect**. Python acts as a remote client; the driver and executor workload run inside OpenShift.

~~~text
Developer laptop / VS Code
  PySpark Connect client
       | sc://localhost:15050 (gRPC)
       v
  oc port-forward
       | authenticated Kubernetes API tunnel
       v
OpenShift namespace
  Spark driver pod
    Spark Connect server :15050
       |
       v
  Spark executor pod(s)
       |
       +--> Hive Metastore / Hadoop / S3, if configured
~~~

**Observations from screenshots (not a confirmed successful test):**
- Spark / Spark Connect version: 3.5.8; Scala artifact suffix: 2.12.
- Spark Connect server class: org.apache.spark.sql.connect.service.SparkConnectServer.
- Application JAR: local:///opt/spark/jars/spark-connect_2.12-3.5.8.jar.
- Driver: 1 CPU core, 4 GiB Spark driver memory.
- Executor: 1 initial instance, 1 core, 4 GiB Spark executor memory.
- Spark Connect gRPC binding port: 15050.
- Existing pod templates, Kubernetes service account, Vault integration, S3 endpoint configuration, KMS settings, Kerberos configuration, and Hive catalog settings are reused from the corporate Spark environment.

**Important:** Screenshots show the commands and proposed client code, but do **not** prove a successful gRPC connection, query, or Hive access. Validate each milestone separately.

## 2. Prerequisites

1. OpenShift CLI (oc) installed and working from the approved development machine / jump host.
2. Valid OpenShift login and access to the target namespace.
3. Permission to create Spark driver and executor resources through an approved Kubernetes service account.
4. An approved Spark **3.5.8** image containing the Spark distribution and required Spark Connect server libraries; or use the corresponding Spark Connect version for the Spark runtime actually deployed.
5. A spark-submit environment that can reach the OpenShift API and can reference the existing Spark image.
6. Python **3.10 or 3.11** on the client is a practical starting choice, with a clean virtual environment.
7. Network permissions to use oc port-forward to the driver pod.

Avoid copying another employee's identity, keytab, IAM/Vault role, KMS key, or internal endpoints.

## 3. Step-by-step replication

### Step A: Log in and check permissions

~~~bash
oc login --server=https://<OPENSHIFT_API_HOST>:6443
oc whoami
oc project <NAMESPACE>
oc get pods -n <NAMESPACE>
~~~

Use your organization's approved authentication mechanism. Avoid putting passwords directly into shell history.

### Step B: Confirm Spark and the server JAR

Run within the Spark submission environment / approved image:

~~~bash
/opt/spark/bin/spark-submit --version
ls -l /opt/spark/jars/spark-connect_2.12-3.5.8.jar
~~~

If running Spark 3.5.3 instead, select a compatible Spark Connect **3.5.3** server artifact and a **3.5.3** Python client. The server requires the rest of its Spark Connect dependencies, not just a stray JAR copied into an unrelated image.

### Step C: Start a minimal Spark Connect server

Run this where spark-submit is installed and can authenticate to Kubernetes. Replace the example service account with the **approved existing** account.

~~~bash
export NS="<NAMESPACE>"
export K8S_API="$(oc whoami --show-server)"
export SPARK_IMAGE="<APPROVED_SPARK_IMAGE>"
export SPARK_CONNECT_VERSION="3.5.8"

/opt/spark/bin/spark-submit \
  --master "k8s://$K8S_API" \
  --deploy-mode cluster \
  --name spark-connect-test \
  --conf "spark.kubernetes.namespace=$NS" \
  --conf "spark.kubernetes.container.image=$SPARK_IMAGE" \
  --conf "spark.kubernetes.authenticate.driver.serviceAccountName=<APPROVED_SERVICE_ACCOUNT>" \
  --conf spark.executor.instances=1 \
  --conf spark.driver.cores=1 \
  --conf spark.driver.memory=4g \
  --conf spark.executor.cores=1 \
  --conf spark.executor.memory=4g \
  --conf spark.connect.grpc.binding.port=15050 \
  --class org.apache.spark.sql.connect.service.SparkConnectServer \
  "local:///opt/spark/jars/spark-connect_2.12-$SPARK_CONNECT_VERSION.jar"
~~~

**Notes:**
- Spark cluster mode launches the **driver inside OpenShift**, not on the local laptop.
- **local:///...** means the JAR must be present at that path **inside the Spark container image**.
- Depending on your image, library layout, Spark Connect dependencies, and Spark/Kubernetes setup, additional configuration may be required.
- Keep initial testing independent of Hive, S3, Vault and Kerberos; add those integrations after the simple query passes.
- This starts a long-running Spark application. Terminate it using your organization's standard Spark/Kubernetes process once testing finishes.

### Step D: Find driver pod, inspect status and logs

~~~bash
oc -n <NAMESPACE> get pods
oc -n <NAMESPACE> describe pod <SPARK_CONNECT_DRIVER_POD>
oc -n <NAMESPACE> logs <SPARK_CONNECT_DRIVER_POD>
~~~

Confirm the driver is **Running**, the Connect server is initialized and no classpath / dependency / authorization errors appear. Check executor startup too.

### Step E: Forward the gRPC port

Open a **separate terminal** on your local machine (where oc login works):

~~~bash
oc -n <NAMESPACE> port-forward pod/<SPARK_CONNECT_DRIVER_POD> 15050:15050
~~~

Keep that terminal open while the client runs. It forwards local port **15050** to the driver pod. For this developer-only test, no public OpenShift Route is necessary.

### Step F: Create the local Python client environment

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "pyspark[connect]==3.5.8"
python -m pip check
~~~

On Windows, activate the environment with:

~~~powershell
.venv\Scripts\Activate.ps1
~~~

**Dependency caution:** The colleague's screenshots explicitly pinned newer versions such as PyArrow 26 and grpcio 1.83. Do not copy those pins without validation. The **PySpark 3.5.8** documentation lists PyArrow **>=4,<13**, grpcio and grpcio-status **>=1.48,<1.57**, and googleapis-common-protos **==1.56.4**. Use the Spark-version-specific dependency guidance, test pip resolution, and prefer a clean isolated environment.

### Step G: Run a basic client test

Create **spark_connect_test.py**:

~~~python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .remote("sc://localhost:15050")
    .getOrCreate()
)

print("Spark version:", spark.version)
print("Spark session class:", type(spark))

# Verify Connect client -> driver -> executor operations.
spark.sql("SELECT 1 AS test").show()
print("Range row count:", spark.range(1000).count())

# Run this only after Hive configuration is added successfully:
# spark.sql("SHOW DATABASES").show()

spark.stop()
~~~

Run:

~~~bash
python spark_connect_test.py
~~~

**Pass criteria:** Client session successfully connects, SQL returns test=1, and range count=1000. Do not claim Hive access until separately confirmed.

## 4. Add enterprise settings after the minimal test

The original screenshot included several integrations that are **not required merely to establish Spark Connect**.

| Setting area | Why it exists | When to add |
| --- | --- | --- |
| Driver and executor pod templates | Mounts, policies, initialization and standard corporate pod configuration | When your namespace/image requires them |
| Kubernetes service account | API authorization for driver/executor creation and interaction | For every Kubernetes Spark application |
| Vault annotation / secret integration | Approved runtime secret retrieval | If required by the platform team |
| S3 VPC endpoint | Private network path to S3 | When accessing the relevant S3 storage |
| AWS KMS configuration | Encryption/key access | When storage objects require it |
| Kerberos principal + keytab | Authenticate to Kerberized Hadoop/Hive services | When accessing those services |
| Hadoop ConfigMap | core-site.xml, hdfs-site.xml, hive-site.xml, etc. | When existing Hadoop integration needs it |
| krb5 ConfigMap | Kerberos realm configuration | For Kerberos access |
| Hive catalog implementation | Uses Hive-backed catalog | To query existing Hive metadata |
| Arrow allocator JVM setting | Native Arrow memory allocation behavior | Only if specifically required and tested |

Illustrative settings to append to spark-submit **after validating your organization's actual names and paths**:

~~~bash
--conf spark.kubernetes.driver.podTemplateFile=<APPROVED_DRIVER_TEMPLATE_PATH> \
--conf spark.kubernetes.executor.podTemplateFile=<APPROVED_EXECUTOR_TEMPLATE_PATH> \
--conf spark.kubernetes.hadoop.configMapName=<APPROVED_HADOOP_CONFIGMAP> \
--conf spark.kubernetes.kerberos.krb5.configMapName=<APPROVED_KRB5_CONFIGMAP> \
--conf spark.sql.catalogImplementation=hive
~~~

For Hive access, validate metastore connectivity, authorization, DNS, mounted config files and any required Kerberos tickets. For S3, validate endpoint/DNS routing, bucket policy, IAM identity, KMS key permissions and Hadoop S3A compatibility. **Local laptop credentials are not automatically the credentials used by Spark executors.**

## 5. Spark Connect vs existing PySpark ETL framework

Spark Connect can support DataFrame operations (SQL, joins, filters, aggregation, DataFrame writes) from a remote Python client. It is **not an identical replacement** for classic PySpark.

Before moving the existing standardization framework to this connection model, audit usages of:
- spark.sparkContext, SparkContext, RDD APIs and df.rdd;
- direct JVM/Py4J access, including _jvm, _jdf;
- Python UDF or custom-library deployment requirements;
- local file paths versus paths accessible to the **remote** driver/executors;
- driver-side collect(), toPandas() and other operations returning data to the client;
- security boundaries, isolation, and session lifecycle for simultaneous users.

**Recommendation:** Preserve the existing Spark submission path for production ETL until the compatibility tests pass. Use Connect first for interactive development and framework validation.

## 6. Troubleshooting

| Problem | What to inspect first |
| --- | --- |
| Connection refused on localhost:15050 | Driver is Running? Connect server bound to 15050? Port-forward still active? |
| gRPC UNAVAILABLE | Tunnel permissions, pod restarts, server startup failure, wrong port |
| ClassNotFoundException / NoClassDefFoundError | Server JAR and matching Spark Connect dependencies in container |
| Pod Pending | Namespace quotas, image pull secrets, node capacity, scheduling |
| Kubernetes Forbidden | Approved service account/RBAC, namespace |
| SELECT 1 works but SHOW DATABASES fails | Hive settings, metastore DNS, credentials, Kerberos, ConfigMaps |
| SELECT 1 works but S3 read fails | S3 endpoint, IAM, bucket policy, KMS, S3A libraries |
| SparkContext or RDD unsupported | Convert to supported Spark Connect DataFrame APIs |
| pip dependency conflicts | Fresh venv; install the compatible pyspark[connect] version and run pip check |

For troubleshooting, first determine which layer failed: **client install → port-forward → gRPC server → Spark execution → Hive/S3**. Debug only that layer, not everything simultaneously.

## 7. Security and operational notes

- Treat **oc port-forward** as a development/testing tunnel for authorized individuals. Do not expose an unauthenticated Spark Connect gRPC endpoint publicly.
- Open-source Spark Connect **does not provide general built-in client authentication**; use organization-approved authenticating gateways, TLS and access policy for shared services.
- Avoid committing screenshots or raw commands containing real internal DNS names, cloud account IDs, principals, pod names tied to identities, keytab paths or secret material.
- Reuse enterprise access controls. Do **not** grant new IAM permissions simply to make the demo run.
- A long-lived driver consumes cluster resources. Monitor CPU/memory and stop it when finished.

## 8. Ordered validation checklist

- [ ] Confirm approved OpenShift namespace and service account.
- [ ] Confirm Spark runtime version and Scala artifact version.
- [ ] Confirm Spark Connect server JAR **and dependencies** in the image.
- [ ] Launch the minimal Spark Connect driver in cluster mode.
- [ ] Confirm driver and executor pod status.
- [ ] Start oc port-forward on port 15050.
- [ ] Install matching local PySpark Connect client in clean venv.
- [ ] Pass SELECT 1 and spark.range(1000).count().
- [ ] Add organization-approved Hadoop/Hive/Kerberos settings.
- [ ] Pass SHOW DATABASES and a permitted test-table read.
- [ ] Add S3/VPC endpoint/KMS settings only as needed.
- [ ] Test existing ETL framework APIs for Spark Connect compatibility.
- [ ] Stop test resources when done.

## 9. Official documentation

- [Apache Spark 3.5.8: Spark Connect overview](https://spark.apache.org/docs/3.5.8/spark-connect-overview.html)
- [Apache Spark 3.5.8: Kubernetes deployment](https://spark.apache.org/docs/3.5.8/running-on-kubernetes.html)
- [PySpark 3.5.8: Installation and dependency versions](https://spark.apache.org/docs/3.5.8/api/python/getting_started/install.html)
- [Apache Spark 3.5.8: Configuration](https://spark.apache.org/docs/3.5.8/configuration.html)

**Next working milestone:** Make a minimal Spark Connect session work in the user's own OpenShift namespace before adding Hive/S3 and the standardization framework.
