# Analytics Sandbox (EKS JupyterHub) - Base

A minimal multi-user JupyterHub "scratchbook" on EKS via Zero-to-JupyterHub.
Phase 1 gives every OIDC user a private notebook pod and a persistent EFS home,
running a plain Python/JupyterLab image. Spark, extra libraries, and the
HMS/Iceberg lakehouse connection are explicit later phases.

## Architecture (Phase 1)

```
Users -> ALB (HTTPS) -> JupyterHub (EKS) -> per-user pod -> EFS home
                              |
                              +-> OIDC (Cognito) login
```

## Layout

```
analytics-sandbox/
  helm/
    values.yaml         # Z2JH: OIDC, base image, EFS home, ingress, cull
    efs-pvc.yaml        # efs-sc StorageClass + PV/PVC for homes
    namespace-sa.yaml   # namespace + singleuser ServiceAccount (IRSA-ready)
    install.sh          # envsubst config.env -> kubectl apply + helm upgrade --install
  image/
    Dockerfile          # base image now; TODO markers for Spark/libs later
    requirements.txt    # empty now; grow in Phase 2
  config.env.example    # ACCOUNT_ID, REGION, EFS id, OIDC issuer/client, HOST
```

## Prerequisites (not created here)

- EKS cluster with: AWS Load Balancer Controller, EFS CSI driver, cluster OIDC provider enabled.
- An EFS filesystem (id goes in `config.env`) reachable from the node subnets.
- A Cognito user pool (or IAM Identity Center app) with a client id/secret and
  callback `https://sandbox.<DOMAIN>/hub/oauth_callback`.
- DNS record + ACM cert for the host.

## Deploy

```bash
cd analytics-sandbox
cp config.env.example config.env      # fill OIDC, EFS id, host, cert ARN

# Preview the rendered manifests without touching a cluster:
DRY_RUN=1 ./helm/install.sh

# Real install (needs kubectl context + helm):
./helm/install.sh
```

`install.sh` renders `namespace-sa.yaml`, `efs-pvc.yaml`, and `values.yaml`
through `envsubst` (only known vars are substituted, so KubeSpawner's
`{username}` token is preserved), applies the namespace/SA/storage, then runs
`helm upgrade --install`.

**Done when:** multiple OIDC users can log in, each gets a private pod +
persistent EFS home, and notebooks run plain Python.

## Phase 2 - add Python libraries + Spark (later)

1. Add packages to `image/requirements.txt`, uncomment the pip install in
   `image/Dockerfile`, build and push to ECR.
2. Point `SINGLEUSER_IMAGE` / `SINGLEUSER_IMAGE_TAG` in `config.env` at the ECR image.
3. For Spark: switch the base to `jupyter/pyspark-notebook` (or add Spark +
   `hadoop-aws` + Iceberg jars) and optionally add Light/Standard profiles.
4. Create the `analytics-sandbox-singleuser` IAM role and scope its S3 access
   (the SA is already annotated for IRSA).

## Phase 3 - connect to the lakehouse (later)

- Wire the HMS Thrift URI + S3 Iceberg warehouse via `singleuser.extraEnv`
  and a `spark-defaults.conf`.
- Add a NetworkPolicy allowing the sandbox namespace to reach HMS.

## Out of scope for base

- Spark / heavy compute (Phase 2).
- HMS / Iceberg data access (Phase 3).
- Multi-team hubs, per-team IAM isolation.
- Shared/group folders (base is per-user home only).
