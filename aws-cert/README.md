# AWS Certification Progress Agent

Track study sessions, practice exams, labs, and domain readiness for AWS certifications.

## Quick start

```bash
pip install -e ".[dev]"
aws-cert init --exam SAA-C03
aws-cert set-goal --exam-date 2026-09-15 --weekly-minutes 300
aws-cert log study --domain secure --minutes 60 --topics "IAM users/roles/policies" --notes "Policy evaluation"
aws-cert log practice --domain resilient --minutes 50 --score 40 --total 65
aws-cert status
aws-cert plan
```

## Files

| Path | Purpose |
|---|---|
| `progress.json` | Durable activity + domain stats |
| `STATUS.md` | Auto-generated readiness dashboard |
| `../.cursor/rules/aws-cert-progress.mdc` | Cursor rule for logging/planning |
| `../.cursor/agents/aws-cert-progress.md` | Reusable agent / automation prompt |

## Domain ids (SAA-C03)

- `secure` — Design Secure Architectures (30%)
- `resilient` — Design Resilient Architectures (26%)
- `performance` — Design High-Performing Architectures (24%)
- `cost` — Design Cost-Optimized Architectures (20%)

## Cursor agent usage

Ask things like:

- “Log 45 minutes on VPC security groups under secure.”
- “I scored 48/65 on a practice exam focused on resilience.”
- “What should I study next for SAA-C03?”
- “Weekly check-in on my AWS cert progress.”

The agent should update `progress.json` via `aws-cert` and refresh `STATUS.md`.
