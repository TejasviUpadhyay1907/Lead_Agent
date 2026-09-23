# LeadRescue AI: product audit and next-chat handoff

**Audit date:** 2026-09-23  
**Repository:** `TejasviUpadhyay1907/Lead_Agent`  
**Product:** LeadRescue AI  
**Audience:** A new engineering/product chat continuing the industrial-readiness goal

> **Current-state note:** This handoff preserves an earlier audit snapshot and its repository/test details are historical. Use [CURRENT_AUDIT_2026-09-23.md](CURRENT_AUDIT_2026-09-23.md) as the source of truth for current commits, worktree, synthetic agent benchmark, opt-out guardrails, latest local test result, and remaining release gates. The 2026-09-24 current audit records published `main` at `3008e3344588c9857c1b1dbbed6001b674538516`, a clean worktree, local build/SAM validation, and 158 passing backend tests. No customer-like staging deployment has been proven; refresh live GitHub state before further edits.

## Executive assessment

LeadRescue is a credible, security-conscious prototype for helping small and medium businesses triage and rescue sales leads. Its strongest architectural decision is the boundary: AI interprets and drafts; deterministic code applies scoring, lifecycle, consent, and workflow rules; a human approves customer-facing action. The repository contains a real full-stack application, a substantial backend policy/workflow layer, AWS infrastructure-as-code, tests, migration scripts, and deployment/integration documentation.

It is **not yet a market-ready product that can honestly be sold as production software**. The repository itself labels the product a prototype. The main remaining gaps are proof in a real AWS staging environment, operational and security validation, a real CRM and messaging integration, complete privacy/data lifecycle handling, and customer evidence. A working codebase and passing local checks do not prove production reliability, legal suitability, connector compatibility, or customer ROI.

**Maturity estimate (judgment, not a measured score):** strong prototype / pre-pilot engineering. The application has meaningful production-oriented controls, but no evidenced production deployment, completed real-provider validation, customer pilot outcome, or production support capability. Describe it as “prototype with pilot foundations,” not “enterprise-ready” or “industry-leading.”

## What product we are building

LeadRescue targets SMB sales teams that receive inquiries from channels such as web forms, CRM systems, marketplaces, and other inbound sources, then lose revenue because response is slow, valuable opportunities are not prioritized, or follow-ups are forgotten.

The intended workflow is:

1. Accept a new lead from a user or a signed inbound webhook.
2. Analyze inquiry intent and context with a read-only AI agent.
3. Apply deterministic, explainable scoring and HOT/WARM/COLD classification.
4. Identify response risk and propose a suitable response or follow-up.
5. Let a human review, edit, approve, reject, or manage the workflow.
6. Record the lead, follow-up, and audit history; honor opt-outs across future matching contacts.
7. Help a manager see whether the team is responding and rescuing opportunities in time.

The product principle is **“AI understands. Software decides. Humans approve.”** AI does not calculate scores, override stop conditions, mutate workflow state, or send messages. A future commercial product must demonstrate measurable customer value (for example, faster first response, more qualified leads contacted, improved conversion, and fewer forgotten follow-ups) rather than only demonstrate that AI can generate drafts.

## Current technical baseline

- **Frontend:** React 18 + Vite single-page application with dashboard, lead inbox/detail, follow-up, activity, and settings views.
- **Authentication:** browser OIDC Authorization Code + PKCE; API validates RS256 bearer tokens, issuer, audience, scope, tenant, expiry/issued-at/subject, and role for protected reads/writes. Real identity-provider behavior still needs staging validation; browser tokens are memory-only, so full-page reload can require sign-in again.
- **Backend:** Python 3.12, FastAPI, Mangum, Strands Agents SDK, Amazon Bedrock.
- **Data and workflows:** DynamoDB repositories for leads, follow-ups, audit, config, durable analysis jobs, customer suppressions, and processed webhook event idempotency; SQS worker for durable lead analysis; tenant-scoped indexes and bounded pagination. Customer-history/suppression identifiers use HMAC pseudonyms from a per-deployment Secrets Manager key, with readiness gated on both migrations matching the active key fingerprint.
- **Infrastructure:** AWS SAM template for API Gateway, Lambda, DynamoDB, SQS/DLQ, Bedrock IAM, Secrets Manager webhook secret, CloudWatch alarms/log retention, and deployment parameters. Static frontend deployment is described as S3 + CloudFront.
- **Integrations:** vendor-neutral, HMAC-signed inbound webhook with replay protection, idempotency, and transactional writes. This is not a finished CRM connector and has no outbound CRM sync or message delivery.
- **Quality:** Python behavioral tests, frontend build, Python dependency lock, frontend npm lock, syntax checks, SAM lint validation, and a GitHub Actions quality workflow are present. CI branch protection, security scans, load tests, cloud integration tests, and verified staging deployment are not evidenced.

## What is implemented in the repository

### Product and agent behavior

- Structured lead analysis with Pydantic validation and a bounded read-only agent tool set.
- Deterministic scoring, priority classification, lead-risk rules, lifecycle rules, follow-up policy, and stop conditions.
- Human review flow for response drafts and lead actions.
- Durable analysis-job submission/polling for the browser, with request idempotency, queue retries, terminal failures, a dead-letter queue, and alarms; the older synchronous analyze endpoint remains for compatibility.
- A local/demo synthetic-data mode. Demo mode is disabled in SAM production defaults; demo endpoints are restricted to local/test use.

### Security, tenant controls, and data correctness

- OIDC API boundary and role checks, tenant-claim matching, tenant-scoped data access, and a first-release deployment model of one isolated stack per customer.
- Scoped IAM policies, configured CORS, API throttling, worker concurrency caps, and Bedrock call bounds.
- Transactional state changes for important lead/follow-up/config/audit workflows and conditional writes to reject stale concurrent edits.
- Signed inbound webhook uses timestamped HMAC, a Secrets Manager secret, replay checks, payload-bound idempotency for new events, and transactionally records lead/audit/deduplication state.
- Durable contact-wide email/phone opt-out suppression, transactional safeguards, fail-closed behavior, HMAC-derived lookup keys from a dedicated Secrets Manager secret, key-fingerprint-bound history and suppression migration markers/readiness gates, and dry-run-first backfill scripts.
- A helper that creates the HMAC key through Secrets Manager and prints only its ARN; key rotation requires a pause and both backfills.
- Tenant-scoped paginated lead/follow-up/audit access, per-lead admin export, no-store export response, and reduced PII in new audit events.
- Point-in-time recovery configured for core tables; log retention and CloudWatch alarms defined in SAM.

These are implementation claims based on current source and repository documentation. They do **not** mean that customer AWS infrastructure is deployed correctly or that controls have been proven under production conditions.

## Repository and Git state at audit time

- `HEAD` is `a8dc789e44791b2b79eed04970e5d0456042901a` (`feat: harden LeadRescue for customer pilots`) on local branch `main`.
- The local `origin/main` tracking ref also resolves to `a8dc789e44791b2b79eed04970e5d0456042901a`.
- A live `git ls-remote` check could not connect to GitHub over HTTPS in this environment. Therefore, the live GitHub branch was **not independently verified during this audit**. Earlier task context reported that this commit had been pushed successfully, but the present network check cannot reconfirm that.
- The worktree is **not clean**: latest check shows **34 modified tracked files and 11 untracked files** (`git status --short`). The changes cover backend/webhook and repository hardening, HMAC migration scripts and tests, the Bedrock profile preflight/IAM changes, approval/delivery state corrections, frontend copy and lifecycle presentation, and these audit/readiness documents. None of this local work is in `a8dc789` or confirmed on GitHub; inspect the complete `git status` and diff before committing or pushing.
- These local changes were made after `a8dc789`; they are not included in that commit and have not been committed or pushed. Do not assume the GitHub copy contains them.
- Current `MARKET_READINESS.md` is the most detailed source-of-truth gap register. `README.md`, `ARCHITECTURE.md`, `INTEGRATIONS.md`, and migration scripts provide supporting context.

## Key release gaps, ordered by customer and business risk

### P0: Prove one customer deployment end to end

There is no evidence in this workspace of a deployed staging stack exercised with a real identity provider and customer-like configuration. Validate OIDC discovery/JWKS/key rotation, exact audience and scope claims, role mapping, CORS/redirect settings, all required SAM parameters, Bedrock access, SNS alarm delivery, and frontend/API hosting. Document repeatable setup, rollback, smoke checks, and teardown. Keep the initial deployment isolated per customer.

### P0: Resolve and prove data migration/cutover procedures

Existing tables require tenant/history indexes and backfills. Existing opted-out contacts require the suppression backfill and completion marker before traffic is allowed. Customer-history and opt-out migrations now use the same HMAC key and both key-fingerprint markers must match before readiness returns success. The suppression apply migration writes new HMAC entries and removes the exact old tenant-prefixed SHA-256 key shape before it restores readiness. Scripts are present, but each migration needs a controlled staging rehearsal, count reconciliation, backup/restore plan, permissions review, failure/restart rehearsal, and signed-off cutover checklist. Never route customer traffic before the documented migration prerequisites pass.

### P0: Validate Bedrock IAM and data residency in staging

The template now requires an explicit geographic inference profile ID and its matching foundation-model ID. The API and worker roles authorize the exact profile and matching foundation-model ARN pattern, constrained to invocation through that profile. The prior implicit US Nova Lite profile default was removed because a US profile can route inquiry data across the US geography. AWS documents the three resource types involved for geographic profiles and notes that SCPs must allow destination regions. A read-only preflight script at `backend/scripts/validate_bedrock_profile.py` now verifies live profile status, model pairing, source Region, and the customer's destination-region allowlist. Remaining proof: run the preflight with customer-approved regions, confirm SCP compatibility, then exercise real Bedrock inference under the deployed Lambda role. The template currently supports geographic profiles; in-Region-only and global profile IAM need a separate design before use.

### P0: Reconcile legacy contact state before customer use

The approval defect is corrected in the current uncommitted worktree: approval records `APPROVED`, does not change lifecycle, recomputes SLA risk, and audits `delivery_status=not_configured`; only provider-confirmed `SENT` suppresses risk. Legacy `SIMULATED_SENT` records are treated as undelivered. UI and dashboard copy distinguish pending approval from approved-but-undelivered; legacy simulated/contacted rows display “Contact unverified”; repeat approval is idempotent. Backend tests and the frontend production build pass after the changes. A read-only inventory at `backend/scripts/audit_legacy_response_states.py` queries tenant lead and audit indexes, outputs lead IDs/timestamps only, and never modifies records; every classification still needs operator review because no prior lifecycle was captured. Run against an authorized staging tenant with an identity that has `dynamodb:Query` on the tenant lead GSI and tenant-lead audit GSI:

```powershell
python backend/scripts/audit_legacy_response_states.py `
  --leads-table leadrescue-leads `
  --audit-table leadrescue-audit `
  --tenant-id <tenant-id> `
  --region <deployment-region>
```

No outbound provider is configured.

Only a generic inbound webhook is implemented. No provider-specific CRM OAuth, field mapping, bidirectional sync, source status reconciliation, outbound email/SMS/WhatsApp delivery, delivery receipts, or provider retry reconciliation exists. With the approval semantics corrected, choose one ICP and one actual source system plus one outbound provider; implement consent-aware delivery with idempotency, retries, receipts, suppression checks, and human approval, then pilot with an authorized customer.

### P0: Privacy and compliance workflows

Per-lead export exists, but it is not a complete contact-wide data-subject export or deletion workflow. No retention/deletion automation, documented data processing terms, jurisdiction-specific legal review, incident response process, or customer key policy is evidenced. Existing historical audit rows still contain prior PII. Establish product data inventory, retention periods, access/deletion across linked records, legal basis/consent handling, subprocessors/data-region policy, incident process, and secure secret/key operations with qualified review appropriate to the target market.

### P1: Reliability, security, scale, and agent quality evidence

Define SLOs for availability, latency, job completion, and recovery; dashboards and trace/correlation IDs; on-call ownership; alarms with verified subscribers; backup/restore drills; incident/runbook procedures; and cost ceilings per tenant. Add security/dependency scanning and cloud integration tests. Load-test expected tenant volumes, query patterns, partitions, queue backlog, throttles, and recovery. Build a versioned agent evaluation set for extraction accuracy, groundedness, unsafe outreach, opt-out handling, language variation, and regression; track model/version, failures, latency, and cost without retaining unnecessary PII.

### P1: Commercial product and customer proof

Select an ideal customer profile, buyer, initial geography, supported lead source, measurable value proposition, onboarding model, service/support commitments, pricing and usage limits. Run a time-boxed pilot with consented/synthetic or customer-authorized data; define baseline and success metrics before launch. Gather operator feedback and prove a repeated workflow and positive ROI before claiming a broad market fit. Create trustworthy onboarding, admin/security documentation, customer support ownership, and clear integration boundaries.

### P2: SaaS expansion and polish

Shared multi-tenant SaaS is not implemented; current topology is one isolated deployment per customer. Do not build shared tenancy until customer demand justifies it. If pursuing it, design per-request tenant repository context, tenant-aware authorization and key/secret boundaries, noisy-neighbor controls, billing/usage accounting, tenant provisioning/deprovisioning, and adversarial cross-tenant tests. Continue improving dashboard usability based on observed sales workflows rather than calling visual polish a substitute for reliability or customer outcomes.

## Current verification evidence and limits

Latest local verification (2026-09-23):

- Backend behavioral suite: **106 passed, 1 warning** on a temporary Python 3.11 Windows environment. GitHub Actions also passed the checked-in Python 3.12 Linux dependency-lock verification, backend tests, syntax check, and SAM validation for the hardening commit. New regressions cover current-lead history exclusion, Bedrock PII redaction, webhook signatures/body limits/schema validation, atomic lead/audit/idempotency writes, and duplicate/reused event IDs. The webhook schema now rejects unknown fields and blank required text after tests exposed silent acceptance. Stored customer identifiers and common name/email/phone patterns in inquiry text are redacted before Bedrock; uncommon formats or other sensitive content may remain.
- Python syntax compilation: passed for the changed webhook, agent, privacy service, and tests; GitHub Actions syntax check also passed.
- `git diff --check`: passed.
- Frontend production build: passed locally and in GitHub Actions, producing Vite bundle `frontend/dist/assets/index-cpghZo6O.js`.
- SAM lint validation passed both locally and in GitHub Actions.
- The Actions workflow now pins Node 24-compatible action releases to immutable commit SHAs and uses Ubuntu 24.04 runners. Latest commit `da66771be462c0644135fcbf9504fc6f90e14e59` is on `main`; GitHub Actions run [35887460865](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35887460865) passed both jobs without Node-runtime or floating-runner notices. The hardening commit remains `c52c2e8`.
- No AWS staging or real provider test has been performed.

These checks prove source/build/CI consistency for the pushed commit; they do not prove cloud deployment, production identity integration, actual Bedrock IAM authorization, migration success against customer data, connector delivery, security posture, performance at load, restore capability, legal compliance, or customer ROI. No AWS staging invocation or IAM simulation was performed. The working tree was clean after the push; any future release change still requires review and verification.

## Recommended plan to reach a responsibly sellable first release

### Completed milestone: reviewed code baseline and CI publication

The hardening change set was reviewed, committed as `c52c2e864ecfc9bb0f391e96902bf40f7ccf043a`, and pushed to GitHub `main`. The CI workflow was subsequently pinned to Node 24-compatible immutable action SHAs and Ubuntu 24.04. Latest commit `da66771be462c0644135fcbf9504fc6f90e14e59` is verified on `main`; Actions run [35887460865](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35887460865) passed frontend production build, Python lock verification, backend tests, syntax checks, and SAM validation. This is source/build/CI evidence only; no cloud or real-provider validation was performed.

### Remaining plan

1. **Correct historical records.** Identify leads marked `SIMULATED_SENT`/`CONTACTED` by the old flow, define how to restore truthful lifecycle based on available evidence, and rehearse the correction on staging data with auditability.
2. **Pick the first customer profile and workflow.** Define buyer, current process, lead source, geography, and measurable baseline. Avoid broad “works for every company” scope.
3. **Close deployment blockers.** Run the Bedrock preflight with the approved routing geography, then validate the updated inference-profile IAM in staging; deploy isolated staging; validate OIDC roles and API/frontend config; verify alarm notifications and throttling.
4. **Rehearse migrations and recovery.** Create a dedicated Secrets Manager HMAC key; test tenant/history and suppression migrations from representative old data with that same key; validate marker behavior, count reconciliation, backups, rollback/cutover, and restore drills before any customer traffic. Rotate only to a new secret ARN with traffic paused and both migrations rerun.
5. **Deliver one real integration path.** Pilot one inbound CRM/form connector and one consent-aware outbound channel with deduplication, delivery state, retry/dead-letter handling, and visible human approval.
6. **Establish safety, privacy, and operations.** Implement data subject export/deletion/retention, define data processing/residency, security controls, incident response, observability, SLOs, support ownership, and per-tenant cost controls.
7. **Verify end to end.** Add/re-run automated tests plus staging integration, security, load, recovery, and agent-quality evaluations using approved data. Record results and known limitations.
8. **Run a measured pilot.** Agree success metrics and feedback cadence with a design partner; compare against baseline; fix reliability and workflow failures; only then decide whether to sell generally and what claims/support level are defensible.

“Top 1%” is not a verifiable engineering acceptance criterion. Replace it with measurable gates: no cross-tenant access, no outreach after suppression, all state changes/audit writes consistent, reliable idempotent integration delivery, documented SLO/restore performance, high task-specific agent evaluation quality, bounded cost, and proven customer ROI.

## Copy/paste prompt for a new chat

> Continue the LeadRescue AI industrial-readiness goal using `C:\Users\tejas\OneDrive\Desktop\TEST\Lead_Agent`; read `PROJECT_AUDIT_HANDOFF.md` and `MARKET_READINESS.md` first, then inspect the current Git status and live remote before editing. Latest verified GitHub `main` is `da66771be462c0644135fcbf9504fc6f90e14e59`; Actions run 35887460865 passed on pinned Node 24-compatible action SHAs and Ubuntu 24.04 runners. The product hardening baseline is `c52c2e864ecfc9bb0f391e96902bf40f7ccf043a`. LeadRescue is a React/Vite + FastAPI/Python 3.12 + Strands/Amazon Bedrock lead triage/rescue prototype built on “AI understands, deterministic software decides, humans approve.” It has OIDC/tenant controls, DynamoDB workflows, an SQS analysis worker, a signed inbound webhook, durable opt-out handling, audit/export, and SAM infrastructure. It is not production-ready or proven sellable. Approval records `APPROVED` without claiming delivery; only `SENT` clears SLA risk; legacy `SIMULATED_SENT` remains undelivered. The agent excludes its current lead from prior history and redacts stored identifiers/common name-email-phone patterns before Bedrock, but unusual PII may remain. The webhook rejects unknown fields and blank required text; 106 backend tests passed locally. Legacy simulated/contacted records still need evidence-based review; `backend/scripts/audit_legacy_response_states.py` is read-only and should be run only in authorized staging. Explicit Bedrock geographic profile/model selection, HMAC index/suppression keys, and migration readiness gates are implemented but not verified in AWS. Next, deploy an isolated AWS staging stack, validate OIDC and Bedrock IAM/region, rehearse migrations and restore, verify alarms, then integrate and pilot one actual CRM source plus consent-aware message delivery. Complete contact-wide privacy lifecycle, operational/security/load/agent-quality evidence, and a measurable design-partner pilot before claiming market readiness. Preserve secrets/customer data and keep the full industrial-readiness goal active until production evidence and customer value support release.

## Bottom line

There is a substantial engineered foundation, not a finished industrial product. The hardening baseline is pushed to GitHub with green source/build CI, but AWS staging, the Bedrock geography/IAM path, migrations/recovery, and real-provider delivery remain unverified. Approval no longer implies delivery, and historical false-contact records still need evidence-based correction. The next priority is an isolated customer-like staging deployment and migration rehearsal, followed by one actual CRM source plus consent-aware delivery workflow. A production sales claim should wait for staging evidence, migration/recovery proof, real delivery behavior, privacy/operations controls, and a pilot showing customer value.
