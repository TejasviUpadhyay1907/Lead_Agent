# LeadRescue AI — Phase 1 Verification Report

Date: September 19, 2026

## 1. Environment Verification

| Tool | Installed Version | Status |
|---|---|---|
| OS | Windows 11 (AMD64) | PASS |
| Python | 3.12.10 | PASS |
| Node.js | v22.22.2 | PASS |
| npm | 10.9.7 | PASS |
| Virtual Environment | `.venv` initialized in `backend/` | PASS |
| AWS CLI | `aws-cli/2.36.49` | **PASS** (Installed via winget) |
| AWS SAM CLI | `SAM CLI v1.166.2` | **PASS** (Installed via winget) |

---

## 2. AWS Identity & Region

| Item | Result | Status |
|---|---|---|
| AWS Identity (`aws sts get-caller-identity`) | `NoCredentials` | ⚠️ **BLOCKED** (Requires `aws configure`) |
| Configured Region | Awaiting user configuration | ⚠️ **BLOCKED** |
| AWS Account Access | Awaiting credentials | ⚠️ **BLOCKED** |

---

## 3. Bedrock & Strands Verification

| Item | Status | Details |
|---|---|---|
| Strands SDK (`strands-agents`) | PASS | Installed in Python virtual environment |
| Model Discovery & Access | ⚠️ **BLOCKED** | Requires AWS credentials and region selection |
| Strands + Bedrock Smoke Test | ⚠️ **BLOCKED** | Requires active AWS credentials |

---

## 4. Infrastructure & Builds

| Check | Result | Status |
|---|---|---|
| `sam validate --region us-east-1` | `template.yaml is a valid SAM Template` | **PASS** |
| FastAPI Health Check (`pytest tests/`) | `1 passed in 0.44s` (`GET /health` → 200 OK) | **PASS** |
| Frontend Build (`npm run build`) | `built in 734ms` → output in `frontend/dist/` | **PASS** |

---

## 5. Architectural Nuances & Decisions

### A. Routing Architecture (Option A)
CloudFront serves the React static SPA from S3. The SPA calls API Gateway directly using a configurable API base URL. This avoids complex CloudFront routing behaviors while keeping the architecture serverless.

### B. Customer Declined Lifecycle Mapping
When a customer declines outreach, `lifecycle_status` becomes `resolved`, with audit log details recording `reason: "customer_declined"`. This preserves the clean 6-value lifecycle enum (`new`, `analyzed`, `contacted`, `follow_up`, `resolved`, `opted_out`).

### C. Response Status & At-Risk Condition
Response status transitions: `draft → approved → simulated_sent`. An approved response must be `simulated_sent` to prevent at-risk triggering. If a response remains `approved` without sending and `effective_now() >= at_risk_at`, the lead will still trigger `at_risk`.

### D. Response Draft Guardrail Policy
Strict facts-only prompt policy: the AI response draft must only cite facts present in the raw lead message or explicit business rules. Invented prices, delivery dates, inventory numbers, or unauthorized discounts will be rejected.

### E. Agent Schema Strict Validation
The Pydantic `AgentAnalysisResult` model uses `extra = "forbid"`. Any attempt by the LLM to output `score`, `priority`, `lifecycle_status`, `risk_status`, or database mutation fields will cause validation failure and fallback.

---

## 6. Summary of Blockers

1. **AWS Credentials**: User must run `aws configure` (or set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) to grant local environment access to AWS.
2. **Bedrock Model Access**: User must verify that Bedrock model access (e.g. Anthropic Claude models or Nova models) is enabled in their selected AWS region console.

---

## 7. Final Verification Status

```text
PHASE 1 — BLOCKED ON AWS CREDENTIALS CONFIGURATION
```

(All software tools, CLI binaries, builds, SAM templates, and unit tests are PASS. Live Bedrock inference requires AWS credentials.)
