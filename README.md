# Autosys → Databricks Cross-Network Integration

Fire-and-forget integration: Autosys CMD job calls the Databricks Jobs API (`run-now`) over outbound HTTPS. Autosys marks success when the API returns HTTP 200 with a `run_id`; it does not wait for the Databricks run to finish.

## Quick start

```bash
cp config/env.template config/.env   # fill in workspace URL, job ID, token
chmod +x scripts/*.sh tests/*.sh
./scripts/check_network_egress.sh     # step 1: network
./scripts/setup_databricks.sh verify # step 2: databricks (admin)
./tests/run_tests.sh                  # step 5: full validation
```

## Layout

| Path | Purpose |
|------|---------|
| [scripts/trigger_databricks_job.sh](scripts/trigger_databricks_job.sh) | Main trigger script (deploy to Autosys agent) |
| [scripts/check_network_egress.sh](scripts/check_network_egress.sh) | Network + auth validation |
| [scripts/setup_databricks.sh](scripts/setup_databricks.sh) | Databricks SP, permissions, IP allowlist |
| [autosys/trigger_databricks_etl.jil](autosys/trigger_databricks_etl.jil) | Autosys job definition |
| [docs/deployment.md](docs/deployment.md) | Full deployment steps |
| [docs/firewall-request.md](docs/firewall-request.md) | Network team ticket template |

## Architecture

```
Autosys Agent --HTTPS POST--> *.cloud.databricks.com/api/2.1/jobs/run-now
                                      |
                                      v
                              Databricks Job (async)
```

See [docs/deployment.md](docs/deployment.md) for detailed setup.
