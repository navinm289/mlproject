# Hub ↔ HMS ↔ S3 vs ingestion

## Mental model

| Piece | Role |
|-------|------|
| **Ingestion jobs (EKS)** | Write Iceberg data to **S3**, register/update tables in **HMS** |
| **HMS pod** | Catalog API (Thrift `:9083`) — table → S3 location |
| **Aurora** | HMS **metadata DB only** (schemas, locations). Not queried for Iceberg rows |
| **JupyterHub** | Workspace front door: login → **one user pod** (JupyterLab) |
| **Notebook files** | On **EFS** (`/home/{user}`, `/shared/{group}`) — not Git |
| **PySpark in notebook** | Asks HMS for tables, reads Parquet/ORC Iceberg files from **S3** |

```text
Ingestion ──write──► S3 (Iceberg files)
    │
    └──register──► HMS pod ──metadata──► Aurora

User ──login──► JupyterHub ──spawn──► User pod (JupyterLab)
                                      │
                                      ├── EFS notebooks
                                      ├── Spark ──thrift──► HMS
                                      └── Spark ──s3──► Iceberg data
```

## Starting a notebook (pods)

1. User logs into JupyterHub (OIDC).
2. **Start My Server** → KubeSpawner creates **one pod** for that user.
3. Opening more `.ipynb` files uses the **same pod** (new tabs).
4. Idle cull (~60m) or Stop Server → pod deleted; EFS files remain.

This is similar to a Databricks **workspace + notebook + compute**, except compute is your EKS user pod (and Spark), not a Databricks cluster.

## Network & IAM

- Jupyter namespace must reach HMS Service (`thrift://…:9083`). See `jupyterhub/rbac-irsa.yaml` NetworkPolicy.
- Notebook pods use IRSA role `jupyterhub-singleuser`:
  - Read: `s3://…/curated/*`, `s3://…/warehouse/*`
  - Write: `s3://…/scratch/{user}/` only
- Aurora stays private to HMS; notebooks never connect to Aurora.

## Catalog rule

**One catalog of truth: HMS + Aurora.** Do not dual-register the same tables in Glue unless you have an explicit sync. Scratchbooks do **not** use Athena/Glue as the primary path.

## Profiles & safety

| Profile | Intent |
|---------|--------|
| Light / Standard | Read Iceberg via HMS; scratch writes to S3 only |
| Heavy | Larger submit path; still HMS + S3 |

Scratch profiles should be **read-mostly** on production Iceberg tables (avoid `DROP` / concurrent commits).

## Group sharing (no Git)

- Personal: `/home/{user}` on EFS  
- Group: `/shared/{group}/` on EFS  
- Examples: `/shared/examples/` (seed with `bootstrap/seed_shared_examples.sh`)

## Ops checklist

1. HMS healthy; Thrift DNS matches `HMS_THRIFT_URI` in Hub values.
2. IRSA annotation on `ServiceAccount/jupyterhub-singleuser`.
3. EFS PVCs bound; homes + shared paths exist.
4. Notebook image in ECR with Iceberg + hadoop-aws jars.
5. Test: open `/shared/examples/read_iceberg_via_hms.ipynb` → `SHOW DATABASES` → read known table.
