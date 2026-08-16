# User guide — scratchbooks

## Login

1. Open the JupyterHub URL (SSO / OIDC).
2. Choose a profile (Light / Standard / Heavy).
3. Wait for **Your server is starting** — this creates your **Kubernetes pod**.

## Where files live

| Path | Purpose |
|------|---------|
| `/home/<you>/` | Personal notebooks (EFS) |
| `/shared/<group>/` | Team shared notebooks (EFS, no Git) |
| `/shared/examples/` | Read-only examples seeded by admins |

## Reading lakehouse tables

```python
from start_spark_session import get_spark
spark = get_spark()
spark.sql("SHOW DATABASES").show()
spark.table("your_db.your_table").show(10)
```

Data path: **Spark → HMS → S3 Iceberg**. Aurora is not queried directly.

## Writing

- Allowed: `s3://<lake>/scratch/<you>/…`
- Not allowed from scratch profiles: overwriting production Iceberg tables

```python
from start_spark_session import user_scratch_path
print(user_scratch_path())
```

## Stop server

Use **Control Panel → Stop My Server** when done (or wait for idle cull) to free the pod.
