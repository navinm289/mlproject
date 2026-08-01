# Firewall Request Template

Submit this to your network/security team to allow Autosys → Databricks integration.

## Request Summary

| Field | Value |
|-------|-------|
| **Source** | Autosys agent host(s): `<hostname>` / `<internal-ip>` |
| **Destination** | `*.cloud.databricks.com` |
| **Port** | 443 (HTTPS) |
| **Direction** | Outbound |
| **Protocol** | TCP |
| **Purpose** | Trigger Databricks ETL jobs via REST API |

## Egress IP to Allowlist in Databricks

Run on the Autosys agent:

```bash
curl -s https://ifconfig.me/ip
```

Provide the returned IP to the Databricks admin for IP Access List entry `autosys-prod`.

## Proxy (if applicable)

If traffic egresses via corporate HTTP proxy, provide:

- Proxy host: `<proxy.example.com>`
- Proxy port: `<8080>`
- Authentication: `<none / NTLM / basic>`

The wrapper script supports `HTTP_PROXY` and `HTTPS_PROXY` environment variables.

## Validation After Approval

```bash
./scripts/check_network_egress.sh
```

Expected: steps 1–4 pass with HTTP 200 on auth test.
