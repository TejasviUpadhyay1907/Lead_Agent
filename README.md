# LeadRescue AI

> AI-powered lead rescue system for small and medium businesses.

**Built for:** WeMakeDevs × AWS First Commit — Bharat Builds Tour 2026

**Current Phase:** Phase 1 — Foundation

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
| Database | DynamoDB (4 tables) |
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
npm install
npm run dev
```

## Environment Variables

Copy `.env.example` to `.env` and fill in values:

```
AWS_REGION=<your-region>
BEDROCK_MODEL_ID=<active-model-id>
DEMO_MODE=true
```

## Hackathon Context

- **Event:** First Commit — Bharat Builds Tour
- **Dates:** September 17–20, 2026
- **Tracks:** Ship It (deployed) + Best UI
- **AI Tools Used:** Antigravity

## License

MIT
