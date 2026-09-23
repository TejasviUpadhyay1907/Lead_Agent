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
| Database | DynamoDB (8 tables, including privacy requests, durable jobs, suppressions, and webhook deduplication) |
| Hosting | S3 + CloudFront |
| API | API Gateway + Lambda |
| IaC | AWS SAM |
| Observability | CloudWatch |

## AWS Services

| Service | Purpose |
|---|---|
| Lambda | Backend compute |
| API Gateway | REST API |
| DynamoDB | Lead, follow-up, audit, config, webhook idempotency, customer suppression, analysis jobs, and privacy request storage |
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

For SAM production deployment, set both required Bedrock parameters: `BedrockModelId` is a **system-defined geographic inference profile ID** and `BedrockFoundationModelId` is its matching foundation model ID. The template deliberately has no default profile: a profile such as `us.amazon.nova-lite-v1:0` routes inference within the US geography, which may be inappropriate for a customer's data-residency policy. Choose the profile, source AWS Region, and model only after checking the current [Bedrock model page](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html) and obtaining the customer's approval for the full destination geography. The current SAM policies support geographic cross-Region profiles; in-Region-only inference and global profiles require a separately reviewed IAM configuration. The API and worker permissions cover the exact profile and only its matching foundation model, with foundation-model invocation constrained to that profile.

Before deployment, inspect the profile's current destinations with `aws bedrock get-inference-profile --inference-profile-identifier <profile-id> --region <source-region>`. After the customer approves the complete destination set, run the read-only validator (using credentials permitted to call `bedrock:GetInferenceProfile`):

```powershell
python backend/scripts/validate_bedrock_profile.py `
  --profile-id <profile-id> `
  --foundation-model-id <foundation-model-id> `
  --source-region <source-region> `
  --approved-destination-region <approved-region-1> `
  --approved-destination-region <approved-region-2>
```

The validator fails if the profile is inactive, is not a system-defined profile, belongs to another source Region, targets a different foundation model, or routes to a Region missing from the customer's approved list. It does not deploy, invoke the model, or establish that the production Lambda role has working inference permissions; those still require staging verification.

`DEMO_MODE=true` is for local/demo data only. A production deployment must use `DEMO_MODE=false` and configure `JWT_ISSUER`, `JWT_JWKS_URL`, `JWT_AUDIENCE`, `JWT_REQUIRED_SCOPE`, `TENANT_ID`, `ADMIN_ROLE`, and `OPERATOR_ROLE`; SAM requires the identity values at deployment. The frontend includes OIDC Authorization Code with PKCE sign-in, but the provider configuration and role claims still require staging validation. The first supported commercial topology is one isolated deployment per customer; shared SaaS is not implemented.

When demo mode is enabled in a local/test environment, repositories use in-memory synthetic data even if AWS credentials are present. This prevents local demos and tests from accidentally reading or writing a configured company database. Production SAM deployments set demo mode off and use DynamoDB.

For the browser sign-in flow, copy [frontend/.env.example](frontend/.env.example) to `frontend/.env` and set the customer's OIDC issuer, public client, API scope, and exact HTTPS redirect URI. The identity provider must allow the frontend origin and use Authorization Code with PKCE. Browser tokens remain in memory; users sign in again after a full page reload unless the identity provider reuses its SSO session.

Existing DynamoDB stacks require the tenant GSI update and [backfill migration](backend/scripts/backfill_tenant_data.py) before the updated API serves traffic. Run the script once per isolated customer: first without `--apply` to review counts, then with `--apply` only after confirming that the whole table belongs to that tenant. The script rejects rows already assigned to a different tenant.

Before production deployment, create a dedicated per-customer index HMAC secret and pass its ARN as `CustomerIndexSecretArn`. With AWS credentials authorized for `secretsmanager:GetRandomPassword` and `secretsmanager:CreateSecret`, run:

```bash
python backend/scripts/create_customer_index_secret.py \
  --name leadrescue/customer-index-hmac \
  --region <deployment-region>
```

The API and worker receive `GetSecretValue` access only to this configured secret. A 64-character generated `hmac_key` is used to derive tenant-scoped contact indexes and suppression keys. These are keyed pseudonyms; lead records still contain the contact fields needed by sales staff. Keep the key stable: key rotation changes every lookup key and can break customer-history matching and opt-out enforcement. Rotation needs a planned intake/worker pause, a new secret ARN, both index and suppression backfills with the new key, and verified reconciliation before traffic resumes; automatic key rotation is not supported. Completion markers record a short key fingerprint so the API stays unready if the backfills and active secret do not match.

Existing lead tables also need the customer-history index migration: deploy the `LeadsTable` GSI additions and `CustomerSuppressionsTable` while API intake and analysis are paused, wait for `tenant-email-index` and `tenant-phone-index` to become `ACTIVE`, then run `python backend/scripts/backfill_customer_history_index.py --table leadrescue-leads --tenant-id <tenant> --region <region> --index-secret-arn <customer-index-secret-arn> --suppressions-table leadrescue-customer-suppressions` once as a dry run and again with `--apply`. The migration identity needs `Scan` and `UpdateItem` on the lead table, `DeleteItem` and `PutItem` on the suppression table, and `GetSecretValue` on the exact index-key secret. Applying the migration removes its readiness marker before changing records and recreates it only after a complete scan. New writes populate HMAC-derived index keys; raw identity values are not used as index partition keys.

The SAM template enables point-in-time recovery on lead, follow-up, audit, and configuration tables. Lambda logs expire after 90 days by default (`LogRetentionDays`). Every deployment must provide `AlarmTopicArn` for an SNS topic in the deployment region; the stack wires API and analysis-worker error/throttle alarms plus queue-age and dead-letter alarms to it. Confirm the topic has verified on-call subscribers and permits CloudWatch alarm delivery before deployment. If a Lambda log group already exists outside CloudFormation, import it into stack management before the first update; preserve its existing log history.

Before applying the migration, take/verify a DynamoDB backup or point-in-time recovery, pause writes to that deployment, wait for all tenant GSIs to report `ACTIVE`, and keep the API off until the backfill and smoke checks are complete. The migration is additive and can be re-run after an interrupted run.

The first inbound integration adapter is a signed webhook for CRMs and form systems that support outbound webhooks. Configure `WebhookSecretArn` in SAM and follow [INTEGRATIONS.md](INTEGRATIONS.md) to sign events and handle retries. This does not provide CRM write-back or message delivery.

Lead analysis in the browser uses the durable job endpoint (`POST /api/leads/{lead_id}/analysis-jobs`, with an `Idempotency-Key` header) and polls `GET /api/leads/analysis-jobs/{job_id}`. SQS retries failed worker deliveries and sends exhausted/crashed jobs to a dead-letter queue; the required alarm topic receives worker errors/throttles, queue delay, and dead-letter alarms. The older `POST /api/leads/{lead_id}/analyze` endpoint remains synchronous for compatibility; new integrations should use the job flow.

Company admins can download one lead record and its linked follow-ups and complete audit history from the lead detail page (`GET /api/privacy/leads/{lead_id}/export`). The export is tenant-scoped, marked no-store, and creates an audit event. Explicitly detected English access/erasure requests from manual and signed-webhook intake are recorded in a separate tenant-scoped admin queue and linked to the lead audit timeline. These requests pause AI analysis, response actions, and rescue for that lead record; a future sales inquiry should arrive as a new lead. Erasure requests also suppress future outreach to the matched contact. After an administrator marks identity verified, the queue can page candidate lead records matching the request lead's stored email or normalized phone; results omit contact details and message text, and each lookup is audited. The lookup does not cover changed or missing identifiers, unrelated connected systems, or guarantee a complete person-wide inventory. Admin status transitions are audited and conditional; recording completion is an administrator attestation only. The product does not automatically verify identity or fulfill a subject-wide export/erasure. Follow the customer's approved privacy process and do not treat queue closure as legal-compliance proof.

Opt-outs apply to the contact across future leads matched by normalized email or phone. Before enabling this release on an existing deployment, pause API intake/outreach and the analysis worker event source. Run `python backend/scripts/backfill_customer_suppressions.py --leads-table leadrescue-leads --suppressions-table leadrescue-customer-suppressions --tenant-id <tenant> --region <region> --index-secret-arn <customer-index-secret-arn>` as a dry run, review the count, then repeat with `--apply` using a separate migration identity with scoped DynamoDB scan/write/delete and `secretsmanager:GetSecretValue` access to the exact index-key secret. Applying removes the prior readiness marker first, so an interrupted migration stays fail-closed. The API, webhook, and worker require both migration completion markers to match the active HMAC key; `/ready` stays `503` until customer-history indexes and opt-out markers are backfilled with that key. Resume intake and the worker only after both apply commands complete and `/ready` returns `200`. New opt-outs and state-changing workflows update the suppression registry transactionally. The registry is durable and has no TTL; removing an opt-out requires verified consent and a separately controlled process that is not yet implemented.

API Gateway throttling defaults to 50 requests per second with a burst of 100 per customer deployment. Tune `apiRateLimit` and `apiBurstLimit` for the customer's traffic profile; the analysis worker also has a separate concurrency cap.

Company settings must contain business rules only. Secret-like keys are rejected on updates, and legacy values are masked in API responses; store connector credentials in AWS Secrets Manager instead.

## Hackathon Context

- **Event:** First Commit — Bharat Builds Tour
- **Dates:** September 17–20, 2026
- **Tracks:** Ship It (deployed) + Best UI
- **AI Tools Used:** Antigravity

This section records the project origin. It is not a claim of production readiness, customer data integration, or live message delivery. Approval records human review only; no customer message is delivered until an outbound provider is configured. Production deployments must configure trusted origins and keep `DEMO_MODE=false`.

## License

MIT
