# LeadRescue AI — Architecture

## Core Principle

> **AI understands. Software decides. Humans approve.**

---

## System Architecture

```
                         LEADRESCUE AI
                              │
                              ▼
                     React / Vite SPA
                              │
                       S3 + CloudFront
                              │
                              ▼
                       API Gateway
                              │
                              ▼
                    Lambda + FastAPI + Mangum
                              │
              ┌───────────────┴────────────────┐
              │                                │
              ▼                                ▼
       STRANDS AGENT                  DETERMINISTIC
       (read-only)                    POLICY ENGINE
              │                                │
       ┌──────┼──────┐              ┌─────────┼─────────┐
       ▼      ▼      ▼              ▼         ▼         ▼
     Lead   History Rules         Scoring    Risk     Follow-up
     Tool    Tool   Tool          Engine    Engine     Engine
              │                                │
              ▼                                ▼
        Amazon Bedrock                     DynamoDB
              │                          ┌────┬────┬────┬────┐
              ▼                          │    │    │    │    │
       Structured                      Leads Fups Audit Config Events
       AI Result
              │                        Human Approval UI
              └───── → Pydantic ────→  [Approve] [Edit] [Reject]
                      Validation
                                      CloudWatch (logs)
```

The API gateway exposes two ingress paths: OIDC bearer-authenticated `/api/*` product routes and `/integrations/v1/leads`, which uses timestamp-bound HMAC verification and transactional idempotency. The webhook secret is read from Secrets Manager; event keys expire after 30 days.

## AI vs Deterministic Boundary

| Responsibility | Owner |
|---|---|
| Understand lead message | AI Agent |
| Extract intent, urgency, entities | AI Agent |
| Summarize customer context | AI Agent |
| Generate response draft | AI Agent |
| Recommend action | AI Agent |
| Calculate lead score (0–100) | Deterministic Engine |
| Assign HOT/WARM/COLD | Deterministic Engine |
| Enforce stop conditions | Deterministic Engine |
| Enforce follow-up timing | Deterministic Engine |
| Calculate at-risk time | Deterministic Engine |
| Detect at-risk state | Deterministic Engine |
| Execute rescue workflow | Deterministic Engine |
| Persist records | Deterministic Engine |
| Maintain audit trail | Deterministic Engine |
| Require human approval | Deterministic Engine |

## Agent Architecture

The Strands Agent is **read-only**. It has 3 tools:

| Tool | Purpose |
|---|---|
| `get_lead()` | Read lead from DynamoDB |
| `get_customer_history()` | Read past interactions |
| `get_business_rules()` | Read business config |

The agent returns structured JSON. Pydantic validates the output. The agent cannot:
- Generate scores
- Assign priorities
- Mutate database records
- Send messages
- Override policies

## Scoring Engine (max = 100)

| Signal | Max Points |
|---|---|
| Intent | 25 |
| Urgency | 20 |
| Quantity | 20 |
| Product | 15 |
| Location | 5 |
| Customer stage | 5 |
| Recency | 5 |
| Value | 5 |
| **Total** | **100** |

Classification: 80–100=HOT, 50–79=WARM, 0–49=COLD

## Three Separate Status Concepts

| Concept | Values |
|---|---|
| Priority | HOT / WARM / COLD |
| Lifecycle | new / analyzed / contacted / follow_up / resolved / opted_out |
| Risk | normal / at_risk |

## AWS Service Responsibilities

| Service | Responsibility |
|---|---|
| CloudFront | Frontend delivery + HTTPS |
| S3 | Static frontend storage |
| API Gateway | API entry point |
| Lambda | Backend execution |
| Bedrock | Foundation model inference |
| DynamoDB | Leads, follow-ups, audit, config, and processed webhook events |
| Secrets Manager | HMAC secret for signed inbound source-system webhooks |
| CloudWatch | Observability |
| IAM | Least-privilege access |
| SAM | Infrastructure-as-code |

## Security Model

- No secrets in code — environment variables only
- IAM least-privilege — scoped per DynamoDB table
- Agent is read-only — no mutation authority
- Human approval required for customer-facing actions
- Synthetic/demo data only

### Production Access Boundary

- Every `/api` route requires an OIDC RS256 bearer access token with the configured issuer, audience, API scope, and tenant claim.
- The deployment checks the token tenant claim against `TENANT_ID`; the initial commercial topology is one isolated stack per customer. A shared SaaS runtime that chooses tenant context per request is not implemented.
- Lead, follow-up, and audit records store tenant keys and are read through tenant-scoped GSIs; lead/follow-up writes enforce tenant ownership. Existing records require the documented backfill before new query paths can see them.
- Lead and follow-up writes require the configured operator or admin role. Business configuration changes require the configured admin role.
- Demo mode is limited to local/test environments; production always requires authentication and disables seed/clock endpoints.
- CORS origins, OIDC issuer/JWKS, audience, scope, tenant, and role claim values must be set for the customer's environment.
- Browser sign-in uses OIDC Authorization Code with PKCE; access tokens are memory-only and sign-out redirects to the provider when supported. Configure the provider's allowed origins/redirect URI and validate token refresh behavior in staging before production rollout.
- Pydantic validation on all inputs and agent outputs
