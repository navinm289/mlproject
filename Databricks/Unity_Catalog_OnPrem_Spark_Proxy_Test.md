# On-prem Spark to Databricks Unity Catalog through a proxy

## Purpose

Read-only proof of concept: confirm that Spark on the **actual on-prem driver host** can (1) reach Unity Catalog's Iceberg REST API through the corporate proxy, (2) load Iceberg metadata using an existing bearer token, and (3) read underlying AWS S3 data. Success in VS Code proves only the VS Code network path, not Spark connectivity.

### Logical flow

```text
On-prem Spark driver ---- HTTPS / bearer token ----> Corporate proxy ----> Databricks Unity Catalog Iceberg REST API
       |                                                                  |
       +---- S3 reads (driver/executors; potentially a different route) <--+ metadata + short-lived credentials
```

**Only read operations in this POC.** Never commit a real bearer token, proxy password, AWS key, internal workspace URL, or sensitive data to GitHub. Use approved secret injection. Spark configurations may appear in diagnostic logs or the UI, so use a test environment and approved credentials.

## Prerequisites

- Iceberg-readable table: managed Iceberg, supported foreign Iceberg, or Delta with Iceberg reads enabled. An ordinary Delta table without Iceberg reads cannot be read through this Iceberg interface.
- External data access enabled on the UC metastore, and the test identity granted `USE CATALOG`, `USE SCHEMA`, `SELECT`, and `EXTERNAL USE SCHEMA`.
- Network access to the Databricks workspace via the proxy; a separate network route to S3 where required.
- Compatible Spark, Scala and Iceberg runtime JAR versions, including AWS bundle. **Example below assumes Spark 3.5, Scala 2.12 and Iceberg 1.9.2.** Verify the on-prem version first; Spark 2.x needs a different approach.
- `jq` for the filtered REST response, and an existing short-lived token with sufficient UC permissions.

## 1. Validate the Unity Catalog REST API from the on-prem host

```bash
export DB_HOST='https://<your-workspace-host>'
export HTTPS_PROXY='http://<proxy-host>:<proxy-port>'
export UC_CATALOG='<catalog-name>'
export UC_SCHEMA='<schema-name>'
export UC_TABLE='<iceberg-table-name>'
# Obtain UC_TOKEN from an approved secret store/environment injection.

curl --fail-with-body --silent --show-error --proxy "$HTTPS_PROXY" \
  -H "Authorization: Bearer $UC_TOKEN" \
  -H 'Accept: application/json' \
  "$DB_HOST/api/2.1/unity-catalog/iceberg-rest/v1/catalogs/$UC_CATALOG/namespaces/$UC_SCHEMA/tables/$UC_TABLE" \
  | jq '{metadata_available: has("metadata"),
         s3_credentials_present: ((.config // {}) | has("s3.access-key-id")),
         aws_region: .config["client.region"]}'
```

**Never log the unfiltered response:** it may contain temporary S3 access keys, secret keys, and session tokens. Metadata available indicates a successful REST metadata request; credential vending is a separate capability and actual S3 access still needs testing. Some table types, including foreign Iceberg, may not vend S3 credentials.

## 2. Run the Spark read-only probe

Companion script: [uc_onprem_probe.py](./uc_onprem_probe.py).

```bash
export AWS_REGION='<s3-region>'
export UC_PROXY_HOST='<proxy-host-without-http-prefix>'
export UC_PROXY_PORT='<proxy-port>'
# Keep DB_HOST, UC_TOKEN, UC_CATALOG, UC_SCHEMA, UC_TABLE in the environment.

spark-submit \
  --packages 'org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.9.2,org.apache.iceberg:iceberg-aws-bundle:1.9.2' \
  uc_onprem_probe.py
```

If the corporate environment blocks package downloads, deploy the compatible JARs through an approved internal artifact repository or your Spark distribution. Distribute them to executors in YARN/Kubernetes too.

The script configures the Iceberg REST catalog alias `uc` with the workspace endpoint, `warehouse` set to the UC catalog, the bearer token from `UC_TOKEN`, and `S3FileIO` for AWS S3. It optionally configures `spark.sql.catalog.uc.rest.client.proxy.hostname` and `.port` for the **Iceberg Java REST client**. Check these properties against your deployed Iceberg version and verify traffic at the proxy. `HTTPS_PROXY` used by curl alone does not guarantee Spark JVM traffic is proxied. A TLS-inspecting proxy may require the enterprise CA in the JVM truststore.

## Interpretation

| Test | What it proves |
| --- | --- |
| REST API HTTP 200 with Iceberg metadata | Driver host → proxy → UC REST endpoint; token/permissions sufficient for this table |
| Spark `SHOW NAMESPACES` | Spark Iceberg REST client can connect to UC |
| Spark `SHOW TABLES` and schema | Spark can discover UC metadata |
| Spark `limit(5).show()` returns rows | Spark can also read table data from S3 (end-to-end proof) |
| HTTP 401 | Token invalid/expired or authentication rejected |
| HTTP 403 | Identify whether denial comes from proxy, Databricks permissions, or network policy |
| Metadata works, S3 read fails | Investigate S3 routing, credential vending, IAM, region, endpoint policy and executor logs |

Long-running jobs need token renewal and temporary S3 credential refresh, not just a token copied once from VS Code. This guide verifies a POC, **not production readiness**.

## Confirm before running

1. On-prem Spark + Scala versions and deployment mode (Cloudera/YARN/OpenShift).
2. UC table type and Iceberg REST eligibility.
3. Whether the proxy accepts on-prem driver traffic and executors can reach S3.
4. Bearer token type (OAuth vs PAT), duration, and secret-handling policy.

## Official references

- [Databricks: Access Databricks tables from Apache Iceberg clients](https://docs.databricks.com/aws/en/external-access/iceberg)
- [Databricks: Unity Catalog credential vending](https://docs.databricks.com/aws/en/external-access/credential-vending)
- [Apache Iceberg: REST catalog](https://iceberg.apache.org/docs/latest/rest-catalog/)
- [Apache Iceberg: Spark configuration](https://iceberg.apache.org/docs/latest/spark-configuration/)
