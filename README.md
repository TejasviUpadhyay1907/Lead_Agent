# LeadRescue AI

> AI-powered lead rescue system for small and medium businesses.

**Built for:** WeMakeDevs × AWS First Commit — Bharat Builds Tour 2026

**Product status:** Prototype; not production-ready. See [MARKET_READINESS.md](MARKET_READINESS.md) for the evidence-based gap review and release gates.

---

## Problem

Small and medium businesses receive leads through multiple channels — WhatsApp, website forms, email, phone, marketplaces — but lose them because:

- Nobody responds quickly
- High-value leads aren't prioritized
- Follow-ups are forgotten
- There's no systematic rescue workflow

**Result:** Revenue lost. Customers gone.

## Solution

LeadRescue AI is an AI-powered lead rescue system that:

1. **Understands** incoming leads using an AI agent (Strands Agents SDK + Amazon Bedrock)
2. **Scores** leads with a deterministic, explainable scoring engine
3. **Classifies** leads as HOT / WARM / COLD
4. **Drafts** responses for human approval
5. **Detects** at-risk leads that haven't received timely responses
6. **Rescues** leads with follow-up workflows
7. **Audits** every action with a complete timeline

### Core Principle

> **AI understands. Software decides. Humans approve.**

---

## Architecture

```
React/Vite → S3+CloudFront → API Gateway → Lambda+FastAPI
                                                  ↓
                                    ┌─────────────┴──────────────┐
                                    │                            │
                              Strands Agent              Deterministic
                              (read-only)               Policy Engine
                                    │                            │
                              Amazon Bedrock            Scoring / Risk /
                                                       Follow-up / Audit
                                    │                            │
                                    └─────────────┬──────────────┘
                                                  ↓
                                              DynamoDB
                                                  ↓
                                          Human Approval UI
```

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite |
| Backend | Python 3.12 + FastAPI + Mangum |
| Agent | Strands Agents SDK |
| LLM | Amazon Bedrock (configurable model) |
| Database | DynamoDB (5 tables, including webhook deduplication) |
| Hosting | S3 + CloudFront |
| API | API Gateway + Lambda |
| IaC | AWS SAM |
| Observability | CloudWatch |

## AWS Services

| Service | Purpose |
|---|---|
| Lambda | Backend compute |
| API Gateway | REST API |
| DynamoDB | Lead, follow-up, audit, config storage |
| Bedrock | Foundation model inference |
| Secrets Manager | Inbound webhook HMAC secret |
| S3 | Frontend hosting |
| CloudFront | CDN + HTTPS |
| CloudWatch | Logs |
| IAM | Least-privilege policies |
| SAM | Infrastructure-as-code |

## Prerequisites

- Python 3.12+
- Node.js 18+
- AWS CLI v2
- AWS SAM CLI
- AWS account with Bedrock model access

## Local Development

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm ci
npm run dev
```

## Environment Variables

Copy `.env.example` to `backend/.env` for the API process and fill in values. For the browser build, copy `frontend/.env.example` to `frontend/.env` and fill in the OIDC settings:

```
AWS_REGION=<your-region>
BEDROCK_MODEL_ID=<active-model-id>
DEMO_MODE=true
```

`DEMO_MODE=true` is for local/demo data only. A production deployment must use `DEMO_MODE=false` and configure `JWT_ISSUER`, `JWT_JWKS_URL`, `JWT_AUDIENCE`, `JWT_REQUIRED_SCOPE`, `TENANT_ID`, `ADMIN_ROLE`, and `OPERATOR_ROLE`; SAM requires the identity values at deployment. The frontend includes OIDC Authorization Code with PKCE sign-in, but the provider configuration and role claims still require staging validation. The first supported commercial topology is one isolated deployment per customer; shared SaaS is not implemented.

For the browser sign-in flow, copy [frontend/.env.example](frontend/.env.example) to `frontend/.env` and set the customer's OIDC issuer, public client, API scope, and exact HTTPS redirect URI. The identity provider must allow the frontend origin and use Authorization Code with PKCE. Browser tokens remain in memory; users sign in again after a full page reload unless the identity provider reuses its SSO session.

Existing DynamoDB stacks require the tenant GSI update and [backfill migration](backend/scripts/backfill_tenant_data.py) before the updated API serves traffic. Run the script once per isolated customer: first without `--apply` to review counts, then with `--apply` only after confirming that the whole table belongs to that tenant. The script rejects rows already assigned to a different tenant.

Existing lead tables also need the customer-history index migration: deploy the `LeadsTable` GSI additions while the API remains offline, wait for `tenant-email-index` and `tenant-phone-index` to become `ACTIVE`, then run `python backend/scripts/backfill_customer_history_index.py --table leadrescue-leads --tenant-id <tenant> --region <region>` once as a dry run and again with `--apply`. Only then deploy/enable the API version that uses indexed history. New writes populate the hashed index keys automatically. These index keys are SHA-256 digests of normalized email/phone values with the tenant ID as prefix; raw identity values are not used as index partition keys.

The SAM template enables point-in-time recovery on lead, follow-up, audit, and configuration tables. Lambda logs expire after 90 days by default (`LogRetentionDays`). Every deployment must provide `AlarmTopicArn` for an SNS topic in the deployment region; the stack wires API and analysis-worker error/throttle alarms plus queue-age and dead-letter alarms to it. Confirm the topic has verified on-call subscribers and permits CloudWatch alarm delivery before deployment. If a Lambda log group already exists outside CloudFormation, import it into stack management before the first update; preserve its existing log history.

Before applying the migration, take/verify a DynamoDB backup or point-in-time recovery, pause writes to that deployment, wait for all tenant GSIs to report `ACTIVE`, and keep the API off until the backfill and smoke checks are complete. The migration is additive and can be re-run after an interrupted run.

The first inbound integration adapter is a signed webhook for CRMs and form systems that support outbound webhooks. Configure `WebhookSecretArn` in SAM and follow [INTEGRATIONS.md](INTEGRATIONS.md) to sign events and handle retries. This does not provide CRM write-back or message delivery.

Lead analysis in the browser uses the durable job endpoint (`POST /api/leads/{lead_id}/analysis-jobs`, with an `Idempotency-Key` header) and polls `GET /api/leads/analysis-jobs/{job_id}`. SQS retries failed worker deliveries and sends exhausted/crashed jobs to a dead-letter queue; the required alarm topic receives worker errors/throttles, queue delay, and dead-letter alarms. The older `POST /api/leads/{lead_id}/analyze` endpoint remains synchronous for compatibility; new integrations should use the job flow.

Company admins can download one lead record and its linked follow-ups and complete audit history from the lead detail page (`GET /api/privacy/leads/{lead_id}/export`). The export is tenant-scoped, marked no-store, and creates an audit event. This is a per-lead operational export; it does not locate every record for a person or replace a formal subject-access/deletion workflow.

Opt-outs apply to the contact across future leads matched by normalized email or phone. Before enabling this release on an existing deployment, pause API intake/outreach and the analysis worker event source, deploy the `CustomerSuppressionsTable`, run `python backend/scripts/backfill_customer_suppressions.py --leads-table leadrescue-leads --suppressions-table leadrescue-customer-suppressions --tenant-id <tenant> --region <region>` as a dry run, review the count, then repeat with `--apply` using a separate migration identity with scoped DynamoDB scan/write access. The API, webhook, and worker fail closed until the migration writes its tenant completion marker; `/ready` stays `503` until then. Resume intake and the worker only after the apply command completes and `/ready` returns `200`. New opt-outs and state-changing workflows update the suppression registry transactionally. The registry is durable and has no TTL; removing an opt-out requires verified consent and a separately controlled process that is not yet implemented.

API Gateway throttling defaults to 50 requests per second with a burst of 100 per customer deployment. Tune `ApiRateLimit` and `ApiBurstLimit` for the customer's traffic profile; the analysis worker also has a separate concurrency cap.

Company settings must contain business rules only. Secret-like keys are rejected on updates, and legacy values are masked in API responses; store connector credentials in AWS Secrets Manager instead.

## Hackathon Context

- **Event:** First Commit — Bharat Builds Tour
- **Dates:** September 17–20, 2026
- **Tracks:** Ship It (deployed) + Best UI
- **AI Tools Used:** Antigravity

This section records the project origin. It is not a claim of production readiness, customer data integration, or live message delivery. Approval currently simulates sending. Production deployments must configure trusted origins and keep `DEMO_MODE=false`.

## License

MIT
