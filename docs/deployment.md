# Deployment Guide

## 1. Network (Autosys agent host)

```bash
# Detect egress IP — give to Databricks admin
curl -s https://ifconfig.me/ip

# Validate connectivity (after firewall + IP allowlist)
cp config/env.template config/.env
# Edit config/.env with workspace URL and token
chmod 600 config/.env
./scripts/check_network_egress.sh
```

See [firewall-request.md](firewall-request.md) for the network team ticket.

## 2. Databricks (admin)

```bash
# Authenticate CLI: databricks auth login --host https://<workspace-id>.cloud.databricks.com
cp config/env.template config/.env
# Set DATABRICKS_JOB_ID and AUTOSYS_EGRESS_IP

./scripts/setup_databricks.sh create-sp
# Generate PAT/OAuth token for autosys-trigger SP → store in config/.env as DATABRICKS_TOKEN

./scripts/setup_databricks.sh grant-job-access
./scripts/setup_databricks.sh add-ip-allowlist
./scripts/setup_databricks.sh verify
```

Manual UI steps if CLI unavailable:
- **Service principal**: Admin Console → Service principals → `autosys-trigger`
- **Permissions**: Job → Permissions → Add SP → Can Manage Run
- **IP Access List**: Admin Settings → IP Access Lists → add Autosys egress IP

## 3. Deploy wrapper script (Autosys agent)

```bash
sudo mkdir -p /opt/autosys/scripts /var/autosys/log
sudo cp scripts/trigger_databricks_job.sh /opt/autosys/scripts/
sudo chmod 755 /opt/autosys/scripts/trigger_databricks_job.sh
sudo chown autosys_svc:autosys /opt/autosys/scripts/trigger_databricks_job.sh
```

### Secure token storage (pick one)

**A. Autosys encrypted global variable**
- Define `databricks_token` in Autosys secure store
- Reference in JIL: `$(SECURE_VAR:databricks_token)`

**B. Restricted env file**
```bash
sudo tee /etc/autosys/databricks.env <<EOF
DATABRICKS_TOKEN=<token>
EOF
sudo chmod 600 /etc/autosys/databricks.env
sudo chown autosys_svc:autosys /etc/autosys/databricks.env
```
Add to wrapper script top: `[ -f /etc/autosys/databricks.env ] && source /etc/autosys/databricks.env`

## 4. Load Autosys job

Edit `autosys/trigger_databricks_etl.jil` — set machine, workspace URL, job ID.

```bash
jil < autosys/trigger_databricks_etl.jil
autorep -J trigger_databricks_etl
```

On-demand test:
```bash
sendevent -E FORCE_STARTJOB -J trigger_databricks_etl
```

## 5. Run tests

```bash
./tests/run_tests.sh
```

Verify in Databricks UI: Workflows → Job runs → confirm new run with logged `run_id`.

## Success criteria

| Autosys | Databricks |
|---------|------------|
| Job exits 0 | New run appears in UI |
| stdout contains `run_id=` | Run proceeds independently |
| HTTP errors → exit 1 | Failures visible in Job runs + optional email alerts |
