# Rollout & Validation

Overlay rendering is validated offline (both teams, dev). The steps below run the
actual deploy per environment. Each environment is a separate EKS cluster, so run
these while `kubectl` points at that cluster.

## Prereqs (per environment)

- `kubectl` context = target env cluster; `helm`, `envsubst` installed.
- EFS CSI driver + `efs-sc` StorageClass installed; EFS filesystem created.
- Per-team IRSA roles created: `cd infra/terraform && terraform apply -var-file=<env>.tfvars`.
- `config/<env>.env` filled in (copy from `<env>.env.example`).
- Notebook image pushed to that env's ECR (`images/notebook/build-push.sh`).
- DNS records for `<team>.<env>.<DOMAIN>` -> ingress ALB.

## Dev rollout

```bash
kubectl config use-context <dev-eks-context>
cp config/dev.env.example config/dev.env    # edit

DRY_RUN=1 ./install.sh retail-cards dev      # review rendered output
./install.sh retail-cards dev
./install.sh brands dev
```

## Validation checklist (per team hub)

1. Group gating (URL is not authorization):
   - A `retail-cards` group user can log into `retail-cards.dev...` -> pod starts.
   - A `brands`-only user hitting `retail-cards.dev...` -> access denied.
2. Per-user home isolation:
   - `echo $HOME` -> `/home/<user>`; another user cannot see it (separate subPath).
3. Team share:
   - `/shared/retail-cards` is read-write for retail-cards members only.
   - `/shared/brands` is NOT mounted in retail-cards pods.
4. HMS read:
   - Open `/shared/examples/read_iceberg_via_hms.ipynb`, run `SHOW DATABASES`,
     read a known table.
5. S3 scoping (IRSA):
   - Write to `s3://<lake>/scratch/retail-cards/<user>/...` succeeds.
   - Write to `curated/*` or another team's `scratch/*` is denied.

Verify pods/SA:

```bash
kubectl -n jhub-retail-cards get pods,sa,pvc
kubectl -n jhub-retail-cards get sa jupyterhub-singleuser -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'
```

## Promote to UAT then PROD

Same overlays, different cluster/context + config:

```bash
kubectl config use-context <uat-eks-context>
cp config/uat.env.example config/uat.env     # edit
./install.sh retail-cards uat
./install.sh brands uat

kubectl config use-context <prod-eks-context>
cp config/prod.env.example config/prod.env   # edit
./install.sh retail-cards prod
./install.sh brands prod
```

Prod overlay (`envs/prod.yaml`) tightens idle culling and disables `admin_access`.

## Add a new team later

1. `cp teams/retail-cards.yaml teams/<team>.yaml` (uses `${TEAM}`, no edits needed).
2. Add `<team>` to `infra/terraform` `teams` var; `terraform apply` per env.
3. Add DNS `<team>.<env>.<DOMAIN>`.
4. `./install.sh <team> <env>`.
