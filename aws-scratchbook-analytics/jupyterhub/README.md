# Multi-Tenant JupyterHub

One JupyterHub per **team** per **environment**. Each combination gets its own
URL, namespace, EFS home/share, and IAM (IRSA) role.

## Files

| Path | Purpose |
|------|---------|
| `base-values.yaml` | Static Helm values shared by all teams/envs |
| `envs/<env>.yaml` | Per-environment overlay (image, HMS, S3, OIDC, ingress) - templated |
| `teams/<team>.yaml` | Per-team overlay (allowed OIDC groups, team share mount) - templated |
| `config/<env>.env` | Per-env values sourced by `install.sh` (gitignored; copy from `.example`) |
| `storage/efs-pvc.tmpl.yaml` | Per-team EFS PVCs (home + team share) - templated |
| `rbac/singleuser-sa.tmpl.yaml` | Namespace + IRSA ServiceAccount + HMS NetworkPolicy - templated |
| `install.sh` | `install.sh <team> <env>` renders overlays and deploys |

## URL scheme

`https://<team>.<env>.<DOMAIN>` — e.g. `https://retail-cards.dev.jupyter.example.com`

## Deploy

```bash
# 1. point kubectl at the target env's EKS cluster
# 2. fill in the env config
cp config/dev.env.example config/dev.env   # edit values

# 3. render only (no cluster changes) to review
DRY_RUN=1 ./install.sh retail-cards dev

# 4. deploy
./install.sh retail-cards dev
./install.sh brands dev
```

## Access model

- **URL is discovery, not authorization.** Each hub's `allowed_groups`
  (from `teams/<team>.yaml`) restricts login to that team's OIDC group.
- Each pod assumes `jhub-<team>-singleuser` (IRSA): read `curated/<team>` +
  `warehouse`, write only `scratch/<team>/<user>`.
- `/home/{username}` is private; `/shared/<team>` is the team collaboration space.

## Add a new team

1. `cp teams/retail-cards.yaml teams/<team>.yaml` (nothing to edit; it uses `${TEAM}`).
2. Add the team to `infra/terraform` `teams` var and apply (creates IRSA).
3. Create DNS record `<team>.<env>.<DOMAIN>`.
4. `./install.sh <team> <env>`.

## IAM (IRSA)

Provision per-team roles with `infra/terraform` (module `modules/team-irsa`) per
environment, or use `infra/irsa/team-singleuser-policy.tmpl.json` with envsubst.
