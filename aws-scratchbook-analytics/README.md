# AWS Scratchbook Analytics

JupyterHub scratchbooks on **existing EKS**, reading **S3 Iceberg** through your **HMS pod + Aurora** metastore. No Git for notebook sharing — **EFS** only. No Glue/Athena as the primary catalog path.

## Layout

| Path | Purpose |
|------|---------|
| [jupyterhub/](jupyterhub/) | Z2JH Helm `values.yaml`, EFS PVCs, IRSA SA, install script |
| [infra/irsa/](infra/irsa/) | IAM trust + S3 policy JSON for notebook pods |
| [infra/terraform/](infra/terraform/) | Terraform for single-user IRSA role |
| [images/notebook/](images/notebook/) | Dockerfile, Spark/HMS config, `start_spark_session.py` |
| [bootstrap/](bootstrap/) | Example notebook + seed script for `/shared/examples` |
| [docs/](docs/) | Ops + user guide |

## Quick start (cluster already has EKS, HMS, Aurora, S3 Iceberg)

1. Replace all `REPLACE_*` placeholders in `jupyterhub/` and `infra/`.
2. Apply IRSA (Terraform or AWS CLI) → annotate `jupyterhub-singleuser` SA.
3. Build/push notebook image: `images/notebook/build-push.sh`.
4. Install Hub: `jupyterhub/install.sh`.
5. Seed examples onto shared EFS: `bootstrap/seed_shared_examples.sh`.
6. Login → start server (spawns **one pod**) → open `read_iceberg_via_hms.ipynb`.

## How it maps to Databricks

| Databricks | This platform |
|------------|---------------|
| Workspace | JupyterHub |
| Notebook | `.ipynb` on EFS |
| Cluster | User pod + Spark → HMS → S3 |
| Unity Catalog / metastore | HMS + Aurora |

See [docs/ops-hub-hms-s3.md](docs/ops-hub-hms-s3.md).
