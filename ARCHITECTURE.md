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
              │                          ┌────┬────┬────┐
              ▼                          │    │    │    │
       Structured                      Leads Fups Audit Config
       AI Result
              │                        Human Approval UI
              └───── → Pydantic ────→  [Approve] [Edit] [Reject]
                      Validation
                                       CloudWatch (logs)
```

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
| DynamoDB | Application data (4 tables) |
| CloudWatch | Observability |
| IAM | Least-privilege access |
| SAM | Infrastructure-as-code |

## Security Model

- No secrets in code — environment variables only
- IAM least-privilege — scoped per DynamoDB table
- Agent is read-only — no mutation authority
- Human approval required for customer-facing actions
- Synthetic/demo data only
- Pydantic validation on all inputs and agent outputs
