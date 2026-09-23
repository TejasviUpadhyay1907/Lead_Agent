# LeadRescue AI — Current Product and Release Audit

**Audit date:** 2026-09-23
**Purpose:** Transferable state-of-project briefing and next-goal definition
**Workspace:** `C:\Users\tejas\OneDrive\Desktop\TEST\Lead_Agent`

## Executive assessment

LeadRescue AI is a technically substantial, pre-pilot prototype for rescuing inbound sales leads. It is designed to receive and triage leads, calculate deterministic priority and risk, generate a response draft, and let a human decide what happens. Its strongest architectural decision is: **AI understands; deterministic software decides; humans approve.**

It is **not yet a market-ready industrial product**. Source code and CI show meaningful engineering controls, but there is no verified customer-like AWS deployment, real identity-provider sign-in, successful Bedrock invocation in the intended account/region, completed existing-data migration, real CRM write/read integration, outbound message delivery, recovery drill, security/load evidence, or measured customer ROI. Those gaps are deployment and product evidence, not things a README or passing unit suite can prove.

Do not describe it as production-ready, fully integrated with company data, autonomous outreach, compliant, or top 1% based on the current evidence. The credible near-term target is a **single-customer isolated pilot** with one lead source and one approved communication workflow. Shared multi-tenant SaaS is a later product decision, not a prerequisite for that first topology.

## What the product is for

Small and medium-sized sales teams often receive leads from forms, marketplaces, email, messaging, or other sources and lose revenue through slow replies, poor prioritization, and forgotten follow-ups. LeadRescue is intended to make that workflow visible and repeatable:

1. Accept a lead and record its source and inquiry.
2. Analyze intent, urgency, product, quantity, location, and customer stage using a bounded agent, with structured output validation.
3. Apply explainable deterministic scoring, priority, lifecycle, risk, and follow-up rules.
4. Show the lead and a proposed response/action to an operator.
5. Record the operator's decision and follow-up activity in an audit timeline.
6. Eventually deliver an approved message through a real provider and reflect provider-confirmed delivery accurately.

The commercial promise should ultimately be measured as faster first response, fewer missed high-value leads, better follow-up completion, and incremental conversion/revenue—not “AI” alone.

## What is implemented in the current source

### Product and frontend

- React 18 and Vite single-page application with dashboard, lead inbox/detail, follow-ups, activity, and settings views.
- Browser OIDC Authorization Code with PKCE flow and in-memory access-token handling.
- Lead review/actions, status/risk/priority presentation, analysis-job submission and polling, and API pagination.
- The browser experience is implemented, but visual polish or a successful build does not establish usability with real sales teams; OIDC setup and user research remain unverified.

### Backend and agent

- Python 3.12-targeted FastAPI application deployed through Mangum/Lambda.
- Strands Agents SDK and Amazon Bedrock integration with Pydantic-validated structured analysis and bounded read-only tools.
- Deterministic scoring, priority, risk, lifecycle, follow-up, and guardrail logic.
- Stored contact identifiers and common name/email/phone patterns are redacted from model context; the original inquiry remains in company storage. This does not establish complete detection of unusual identifiers or other sensitive content.
- Browser lead analysis uses durable SQS jobs and authenticated status polling, with idempotency, bounded retries, terminal job state, a DLQ, and alarms. A synchronous analyze endpoint remains for compatibility.
- Local/demo mode uses synthetic in-memory repositories; production SAM defaults disable demo mode.

### Data, identity, and safety controls

- OIDC token validation, audience/scope/tenant checks, role-gated customer data access, and tenant-scoped repository queries.
- Current first-customer design is one isolated deployment per customer, not a shared SaaS control plane.
- Important lead, follow-up, response-review, lifecycle, and business-configuration changes are transactionally paired with audit events and use conditional writes against stale updates.
- Inbound integration endpoint accepts a bounded, schema-validated HMAC-signed webhook with timestamp/replay checking, payload-bound idempotency, duplicate handling, and transactional lead/audit/event persistence.
- Email/phone opt-outs are represented by a durable suppression registry, checked across future activity, with transactional safeguards and fail-closed migration/readiness markers.
- Contact-history and suppression indexes use HMAC-derived values from a per-deployment Secrets Manager key; dry-run-first migration/backfill scripts are present.
- A company-admin endpoint exports one lead with its follow-ups and audit history, records the export, and marks the response no-store.
- Approval records `APPROVED`; it does not claim contact or delivery. Only a provider-confirmed `SENT` status clears SLA risk. Historical records created under old simulated behavior need a reviewed correction plan.
- Privacy lifecycle remains incomplete: no demonstrated contact-wide export/deletion/retention workflow, verified consent synchronization, or customer-specific data-processing review.

### Infrastructure and delivery pipeline

- AWS SAM template provisions API Gateway, Lambda, DynamoDB tables/indexes, SQS/DLQ, Bedrock invocation IAM, Secrets Manager references, CloudWatch alarms/log retention, and deployment parameters. Static frontend hosting is described as S3 + CloudFront.
- Core tables enable point-in-time recovery; API throttling and worker concurrency limits are configurable. Bedrock requires an explicit geographic inference profile/model pair.
- GitHub Actions quality workflow builds the frontend, verifies the Python dependency lock, runs backend tests, checks Python syntax, and validates SAM. Actions are pinned to immutable SHAs and jobs use Ubuntu 24.04.
- GitHub Actions run [35889677117](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35889677117) passed both jobs for the benchmark commit. CI is source/build evidence; it is not AWS deployment, IAM authorization, data migration, or production-readiness evidence.
- Security/dependency scanning, branch-protection enforcement, cloud integration tests, an actual staging deploy, verified SNS/on-call delivery, dashboards/tracing/SLOs, and operational recovery exercises are not evidenced.

## Audit evidence and current checkout state

- Snapshot below records the state at publication of the first benchmark, followed by the 2026-09-24 continuation and publication evidence.
- At the start of the 2026-09-24 continuation, local `main` was `4ff4df5d87d96ed0e5a6edd5a40902c7b884a9cb` (`docs: sync audit with published benchmark`). This commit had previously been verified on GitHub `main`, and its CI run [35889942567](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35889942567) passed.
- The 2026-09-24 continuation added two exact-response prompt-injection canaries, narrow response-policy language, regression tests, and updated benchmark notes. Commit `0960d9066c4ac774821472b16b5f2ae87760f3c1` is pushed and verified as live GitHub `main`; Actions run [35910999823](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35910999823) passed both frontend and backend/SAM jobs. The worktree was clean immediately after push.
- The older `PROJECT_AUDIT_HANDOFF.md` contains older audit-time details. Its top note points to this file as current source of truth; prefer the checkout facts above.
- `MARKET_READINESS.md` is the broad gap register; `README.md`, `ARCHITECTURE.md`, `INTEGRATIONS.md`, `template.yaml`, and backend migration scripts provide more detailed claims and procedures.
- Verification: the first benchmark commit passed 110 local tests and CI. Current ten-case/two-canary continuation passes **114 backend tests with 1 upstream deprecation warning** on Python 3.11; Python syntax compilation, dataset JSON/uniqueness checks, and `git diff --check` also passed. GitHub CI run 35910999823 passed frontend production build, Python lock verification, backend tests, syntax checks, and SAM validation. Live Bedrock inference has not been run because no configured model/account credentials were provided. These synthetic canaries test literal marker non-disclosure only and are not evidence of general prompt-injection robustness.

## Readiness by evidence category

| Category | Current position | What is still needed |
|---|---|---|
| Source architecture | Strong prototype foundation | Independent design/security review and architecture decisions based on one real customer's constraints |
| Automated source checks | Useful baseline; documented green CI | Branch protection, security/dependency scanning, cloud integration coverage, reliability and regression gates |
| Frontend/UX | Main workflow screens exist | Real operator walkthroughs, accessibility review, usability findings, validated OIDC/session behavior |
| Agent quality | Structured agent plus deterministic fallback/policy; a ten-case synthetic benchmark with structured-field scoring and two literal response canaries is in source, but it has not been run against Bedrock | Broader representative set, prompt-injection and groundedness evaluation, safety/accuracy thresholds calibrated with a customer, latency/cost monitoring, model/version regression evidence |
| Authentication/tenant isolation | OIDC and tenant/role controls implemented; isolated deployment design | Real IdP staging proof, adversarial isolation checks, key rotation procedures and review |
| AWS deployment | SAM infrastructure described in source | Isolated staging deployment with complete parameters, approved model geography, working IAM, alarms, CORS, rollback and teardown evidence |
| Existing data/cutover | Tenant/history and suppression migrations exist | Backup, dry run, apply/reconciliation, interruption/restart rehearsal, readiness proof and signed cutover procedure |
| Inbound integration | Generic signed webhook exists | Connect and validate one real CRM/form source, mapping/retry behavior, support ownership and connector health |
| Outbound communication | No real provider; approval is accurately separated from delivery | One consent-aware provider, delivery receipts, idempotency, retries/DLQ, opt-out enforcement, human approval rules and audit proof |
| Privacy/security | Several controls exist | Full retention/deletion/export lifecycle, consent and data-processing terms, encryption/key policy, incident procedures, threat model and penetration review |
| Operations/reliability | Some alarms, retention, PITR and limits in template | Verified on-call, SLOs/dashboards/traces, restore and incident drills, queue recovery, capacity/load tests, cost ceilings |
| Commercial evidence | No documented design-partner ROI | ICP/buyer/use case, baseline, measurable pilot outcomes, onboarding/support/pricing and honest product claims |

### Release proximity

A single percentage would give false precision. The repository is reasonably far along as a **feature-rich code prototype**, but early as a **customer-operable service**. Passing CI and having infrastructure code reduce implementation uncertainty; they do not close operational, integration, privacy, or market-fit gates. It should be treated as **pre-staging / pre-pilot**, not ready for general sale. A carefully scoped design-partner pilot becomes reasonable only after the P0 staging, migration, identity, model, provider, privacy, and operations gates below pass.

## Blocking work, in order

### P0 — Make one isolated staging deployment real and safe

Choose one target customer profile, geography, IdP, AWS region, approved Bedrock inference geography/model, lead source, and communication channel. Deploy an isolated staging stack. Validate browser sign-in and roles, API origin/CORS, SAM parameters, Bedrock IAM and bounded inference, webhook secret access, SNS alarm arrival to a real owner, throttling, and clean rollback/teardown. Record commands, versions, evidence, and failure recovery.

### P0 — Rehearse data migrations and truthful historical state

Use representative synthetic/staging data. Take and verify a backup; exercise dry-run/apply of tenant/history indexes and opt-out suppression using the same HMAC key; reconcile counts and key markers; test interruption/restart and restore. Investigate old `SIMULATED_SENT`/`CONTACTED` records with the read-only audit script and approve a defensible correction procedure before any customer cutover.

### P0 — Complete one complete business workflow

Connect one real inbound source through the generic webhook or a dedicated adapter and map actual fields. Implement one outbound provider only after consent/opt-out and approval behavior are defined. Verify provider receipts, duplicate/retry semantics, failure/DLQ recovery, no send after opt-out, human approval, audit accuracy, and customer-visible status end to end. Current inbound acceptance alone is not a complete CRM integration.

### P0 — Establish customer data and privacy controls

Specify what goes to the model, customer-approved processing geography, retention, encryption/key ownership/rotation, access logging, breach response, contact-wide access/export/deletion, and deletion of linked follow-ups/audit/derived state where legally and operationally appropriate. Review jurisdiction and contracts with qualified owners; source code does not make legal compliance claims true.

### P1 — Prove quality, reliability, and cost

Expand and version the initial ten-case synthetic benchmark with realistic language variation, multilingual inputs, ambiguities, opt-outs, richer prompt-injection attacks, and no-evidence cases. The runner scores intent/urgency/customer-stage and product/quantity/location, refuses deterministic fallback results, requires explicit billed-inference confirmation, checks two literal response canaries, and excludes raw messages/generated drafts/canary values from reports. A canary pass does not prove general prompt-injection resistance. Its initial thresholds are not validated release gates. Score grounded response drafts, unsafe claims, and suppression behavior; run it against the approved staging model and calibrate acceptance with a design partner. Add model/version, latency, error, token/cost metrics without collecting unnecessary PII. Load-test expected tenant volume and queue/backlog/throttle behavior. Exercise PITR restore, worker retries/DLQ replay, alarm delivery, and incident runbooks. Define SLOs, RPO/RTO, and per-customer spend limits and measure them.

### P1 — Run a measured design-partner pilot

Select ICP, buyer, initial geography, workflow, supported integration, and operator. Before use, agree a baseline and target metrics (response time, lead-contact rate, follow-up completion, conversion or qualified pipeline, and operator time). Time-box the pilot; obtain authorized data/consent; review safety and reliability weekly; record failures and ROI; fix issues before broad sale. Define setup, support, pricing, service expectations, and data offboarding from observed customer work.

### P2 — Decide whether to expand to shared SaaS

Only after customer pull: design tenant provisioning, per-request data/key isolation, billing/usage, noisy-neighbor controls, support/admin boundaries, deletion/offboarding, and hostile cross-tenant tests. The existing isolated-stack topology can serve a first customer without pretending shared tenancy already exists.

## What “top 1%” should mean here

“Top 1%” is not a verifiable acceptance criterion. Use release gates the buyer can observe and the team can demonstrate:

- no unauthorized cross-tenant data access in adversarial tests;
- no outreach after opt-out and no approval reported as delivery;
- consistent state/audit behavior under retries and concurrent edits;
- representative agent quality above explicitly agreed thresholds, with unsafe/un-grounded outputs measured;
- documented and tested SLO, restore objectives, incident ownership, and bounded per-customer cost;
- reliable real integration behavior with receipts, retries, and replay evidence;
- customer pilot shows a measurable improvement against the agreed baseline;
- onboarding, support, privacy, limitations, and offboarding are documented and usable.

## Recommended next milestone

**Milestone name:** `Customer-like staging proof for one isolated LeadRescue deployment`.

**Definition of done:** an isolated AWS staging stack is deployed from the checked-in SAM template; a real OIDC test tenant can sign in with correct roles; Bedrock performs bounded analysis only through a customer-approved geographic profile and IAM path; one actual inbound lead source is ingested idempotently; an approved message is delivered through one consent-aware provider and status is based on provider receipt; opt-out blocks delivery; migrations and historical-state handling are rehearsed and reconciled; alarms reach an owned on-call destination; restore and failure-recovery exercises pass; privacy/retention boundaries are documented; quality/load/security checks have recorded results; no unresolved P0 issue remains. This is a pilot-readiness gate, not general-market readiness.

After that milestone, run a time-boxed design-partner pilot with pre-agreed ROI measures. General sale should remain gated on pilot evidence and operational support readiness.

## Copy/paste brief for the next chat

> Continue the industrial-readiness goal for LeadRescue AI in `C:\Users\tejas\OneDrive\Desktop\TEST\Lead_Agent`. First read `CURRENT_AUDIT_2026-09-23.md`, `MARKET_READINESS.md`, and `PROJECT_AUDIT_HANDOFF.md`; then inspect fresh `git status`, current commit, and live GitHub `main`. This is a React/Vite + FastAPI/Python 3.12 + Strands/Amazon Bedrock lead triage/rescue prototype built around “AI understands, deterministic software decides, humans approve.” It has structured lead analysis, deterministic scoring/risk/follow-up policy, OIDC/tenant/role controls, tenant-scoped DynamoDB data, durable SQS analysis jobs, a signed idempotent inbound webhook, durable contact opt-outs, audit/export, AWS SAM infrastructure, and green documented CI. It is pre-staging/pre-pilot and not generally sellable: no verified AWS staging, real IdP/Bedrock IAM invocation, rehearsed migrations/restore, vendor CRM read/write integration, outbound messaging provider/receipts, full privacy lifecycle, operational/load/security proof, or customer ROI. The opt-in ten-case synthetic evaluation runner scores six structured fields and checks two literal response canaries; commit `0960d9066c4ac774821472b16b5f2ae87760f3c1` is published, CI run 35910999823 passed, but the live benchmark has not been run on Bedrock and canaries do not prove general injection resistance. Local tests pass 114/114 with one deprecation warning. Next goal: complete and prove one isolated customer-like staging workflow end to end, including approved Bedrock geography, real identity, one inbound source, one consent-aware outbound provider, opt-out, migrations, alarm/on-call, recovery, privacy boundaries, and recorded quality/load/security evidence. Do not claim “top 1%”; define measurable gates and proceed autonomously through reversible source work, but do not use real customer data or external services without the necessary credentials/authorization. Then run a measured design-partner pilot and prove ROI before general sale. Keep the goal active until those evidence-backed gates are met.
