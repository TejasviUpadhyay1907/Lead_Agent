# LeadRescue AI — Current Product and Release Audit

**Audit date:** 2026-09-24 (worktree continuation)
**Purpose:** Transferable state-of-project briefing and next-goal definition
**Workspace:** `C:\Users\tejas\OneDrive\Desktop\TEST\Lead_Agent`

### Continuation update — 2026-09-24: protect WhatsApp provider identity binding

- Tightened the signed Meta status callback path: if a callback references a known opaque attempt ID but carries a provider message ID different from the one already bound to that attempt, the callback is ignored for that attempt. This prevents a callback from rewriting an established provider identity. A first valid callback can still bind the provider ID when it arrives before the outbound API response is persisted.
- Published as `049f47fbb081661b76bbb2de25683d7f89a792c9`. GitHub Quality Gates run [35986971922](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35986971922) and CodeQL run [35986971986](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35986971986) passed for this commit. No Meta sandbox callback was exercised, so provider behavior remains unproven.

## Executive assessment

LeadRescue AI is a technically substantial, pre-pilot prototype for rescuing inbound sales leads. It is designed to receive and triage leads, calculate deterministic priority and risk, generate a response draft, and let a human decide what happens. Its strongest architectural decision is: **AI understands; deterministic software decides; humans approve.**

It is **not yet a market-ready industrial product**. Source code now includes an outbound WhatsApp attempt path, but there is no verified customer-like AWS deployment, real identity-provider sign-in, successful Bedrock invocation in the intended account/region, completed existing-data migration, live CRM write/read integration, verified Meta delivery, recovery drill, security/load evidence, or measured customer ROI. Those gaps are deployment and product evidence, not things a README or passing unit suite can prove.

Do not describe it as production-ready, fully integrated with company data, autonomous outreach, compliant, or top 1% based on the current evidence. The credible near-term target is a **single-customer isolated pilot** with one lead source and one approved communication workflow. Shared multi-tenant SaaS is a later product decision, not a prerequisite for that first topology.

## Current repository snapshot (2026-09-24)

- **Latest implementation commit:** `50e4336d6bae8c172835cbf6e8ccd80f1b38e49d` follows the WhatsApp delivery implementation. Local verification on this worktree: **178 backend tests passed**, Python compilation passed, frontend production build passed, SAM lint validation passed, and `git diff --check` passed. The preceding published commit's Quality Gates run [35985825920](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35985825920) failed because its four new WhatsApp tests still used the old request/model constructors; commit `50e4336` fixes those fixtures and tightens template confirmation. New GitHub checks remain pending publication. Source checks do not establish cloud deployment or runtime behavior.
- The latest code change makes factual-claim verification a server-enforced prerequisite for approving a response draft. Approval requests must include strict boolean `claims_verified: true`; the API rejects missing/false attestations and records the attestation in the approval audit event. The UI sends the explicit operator checkbox value. Approval still does not send a message. Existing API clients that approve without this field now receive HTTP 400 and must update.
- Zoho intake remains create-only at `POST /integrations/v1/zoho/leads`, with a dedicated optional Secrets Manager token, strict mapping, and permanent source-record dedupe. It does not sync edits or write back to Zoho; exact Zoho interpolation/retries remain unverified in a sandbox.
- WhatsApp now has a distinct operator send action, one durable attempt per exact approval/evidence/template/account fingerprint, an explicit preview-bound confirmation, and no blind network retry. Signed Meta callbacks correlate and record accepted/sent/delivered/read/failed/unknown states; inbound English STOP/quick replies create durable suppression and per-lead audit records. Exact rendered messages are retained and included in admin exports. Outbound is disabled in local/demo and defaults off in SAM. There are no Meta credentials or sandbox/staging proofs; message-retention and subject-wide erasure still need customer policy and implementation.
- A read-only GitHub API check confirms `main` has no branch-protection rules. A read-only AWS STS probe found no usable AWS credentials in this local environment; this does not prove the company has no AWS account or staging stack.
- Local verification on the outcome-capture plus outcome-report change: full backend suite **166 passed** (two upstream deprecation warnings); frontend `npm run build` passed; focused report tests pass; `git diff --check` passes. GitHub quality and CodeQL passed on the published report change.

The entries below this snapshot include chronological history from earlier points in the review; use the latest verified publication and later continuation updates as current state.

- The review began from `3d0d1403003a882361c8b18d4bd8904063afcb7b`; this privacy-review implementation and its verification were published as `3008e3344588c9857c1b1dbbed6001b674538516` on `main` and `origin/main`. The worktree is clean after publication.
- The pre-publication change set covered 30 modified tracked files and 4 new files. It added a metadata-only admin privacy-request queue, audited status transitions, intake detection, a per-lead processing hold across AI analysis/response/follow-up/rescue, regression tests, and admin-only paginated candidate lookup over matching email/phone indexes after identity is marked verified.
- At the earlier privacy-review checkpoint, frontend build, Python compilation, backend suite (158 passed), and SAM lint validation passed. Those historical results do not describe the current suite count. The current outcome-capture change passed the local checks listed in the repository snapshot above; neither set of checks establishes deployed AWS behavior, real OIDC/Bedrock, IAM, or vendor integrations.
- Privacy request completion is an administrator attestation. The new lookup returns candidate lead records matching the request lead's stored email or normalized phone, only after identity is marked verified; it cannot guarantee a complete person-wide inventory across changed identifiers or other connected systems. The product still does not automatically verify identity, fulfill subject-wide access/erasure, manage retention/legal holds, or prove legal deadlines. An erasure request triggers durable contact suppression; lead and related data remain stored pending a controlled fulfillment process.
- Current maturity remains advanced prototype / pilot preparation, pre-staging and not generally sellable. Company outcome reporting now gives a bounded UTC lead-created cohort, paginated totals, decided-lead win rate, and won amounts separated by currency; it is based on operator-entered outcomes and DynamoDB's eventually consistent index, not CRM attribution or recovered revenue. The next product step is to select a customer and first CRM/channel, then close that integration loop. The release milestone remains customer-like staging proof for one isolated deployment, including real identity, approved Bedrock geography, a real lead source and consent-aware delivery, migrations, monitoring, restore/recovery, security/load/quality evidence, and an operational owner.
- **Pilot integration assumption:** until a design partner identifies its actual stack, use Zoho CRM + Meta WhatsApp Business Platform as the candidate first path for an India-based SMB. Confirm the partner, Zoho edition/region and lead fields, WhatsApp Business account/sandbox, opt-in provenance and approved templates, and operational owner before enabling the route or extending the connector.
- **Integration implementation update:** a dedicated Zoho CRM lead-create intake route now accepts a strict field-mapped payload, authenticates with a separate optional Secrets Manager token, and permanently deduplicates a Zoho record ID; a changed payload for that ID fails with conflict instead of creating a second lead. This is inbound create-event intake only. Zoho edit synchronization, OAuth connection lifecycle, CRM writeback, WhatsApp sending/receipts, and real Zoho sandbox evidence remain open. Confirm dynamic-field escaping and retry behavior in the design partner's Zoho sandbox before enabling it.

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
- The browser styling and responsive layout were corrected and checked in a local synthetic session; neither this check nor a successful build establishes usability with real sales teams. OIDC provider setup, complete accessibility review, and user research remain unverified.

### Backend and agent

- Python 3.12-targeted FastAPI application deployed through Mangum/Lambda.
- Strands Agents SDK and Amazon Bedrock integration with Pydantic-validated structured analysis and bounded read-only tools.
- Deterministic scoring, priority, risk, lifecycle, follow-up, and guardrail logic.
- Stored contact identifiers and common name/email/phone patterns are redacted from model context; the original inquiry remains in company storage. This does not establish complete detection of unusual identifiers or other sensitive content.
- Browser lead analysis uses durable SQS jobs and authenticated status polling, with idempotency, bounded retries, terminal job state, a DLQ, and alarms. A synchronous analyze endpoint remains for compatibility.
- Local/demo mode uses synthetic in-memory repositories; production SAM defaults disable demo mode.
- Frontend design audit (2026-09-24): the local browser initially proved that `main.jsx` did not import the existing stylesheet, so no CSS loaded in any view. Corrected the entry point and added the missing shared shell/view/responsive styles, focus-visible treatment, and reduced-motion handling; removed the remote Google Fonts import. Local synthetic demo browser checks verified the main sales routes and desktop/mobile inbox/detail layout. Full screenshot-based visual review and sales-user usability/accessibility review remain open. See [FRONTEND_DESIGN_AUDIT.md](FRONTEND_DESIGN_AUDIT.md).

### Data, identity, and safety controls

- OIDC token validation, audience/scope/tenant checks, role-gated customer data access, and tenant-scoped repository queries.
- Current first-customer design is one isolated deployment per customer, not a shared SaaS control plane.
- Important lead, follow-up, response-review, lifecycle, and business-configuration changes are transactionally paired with audit events and use conditional writes against stale updates.
- Operators can record `won`, `lost`, or `disqualified` outcomes on a lead. Won outcomes may include exact numeric value and a three-letter currency code; lost/disqualified outcomes require a reason. The API resolves the lifecycle, applies privacy/opt-out checks, and transactionally records the lead and actor-attributed audit event. Lead detail labels the entry manual and unsynced. This captures data only; no company-wide outcome report or revenue attribution is implemented.
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
- A separate immutable-SHA CodeQL workflow now analyzes frontend and backend source on pull requests, `main` pushes, and weekly; its first sensitive-logging finding was fixed and GitHub marks it resolved. No open CodeQL alerts remain.
- GitHub Actions run [35889677117](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35889677117) passed both jobs for the benchmark commit. CI is source/build evidence; it is not AWS deployment, IAM authorization, data migration, or production-readiness evidence.
- Security/dependency scanning, branch-protection enforcement, cloud integration tests, an actual staging deploy, verified SNS/on-call delivery, dashboards/tracing/SLOs, and operational recovery exercises are not evidenced.

## Audit evidence and current checkout state

### Continuation update — 2026-09-24: auditable sales outcomes

- Added a sales-outcome endpoint and lead-detail UI for operator-entered `won`, `lost`, and `disqualified` results, with optional won amount/currency, required reasons for loss/disqualification, timestamps, lifecycle resolution, optimistic concurrency, and audit history. Privacy-held and opted-out/suppressed records reject updates.
- Deal values use decimal validation and are stored as DynamoDB numeric values; a repository regression check verifies exact decimal serialization. Outcome reporting and conversion attribution across the company remain unimplemented.
- Local full backend suite passes **164 tests** and focused API tests pass **12 tests**. Frontend production build succeeds. GitHub quality and CodeQL runs [35975052139](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35975052139) and [35975052123](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35975052123) passed on code commit `8add9fa4e38fe2a062c98750bdbe682bac654b51`. No AWS staging or CRM integration was exercised.

### Continuation update — 2026-09-24: unsupported draft-claim reduction

- Removed the deterministic demo fallback's unsupported promises of a technical specialist, response “shortly,” and guaranteed specs/pricing. The live model prompt now prohibits unconfigured response-time, date, availability, price, or specialist commitments.
- Added a visible operator reminder to verify factual claims—especially price, availability, delivery dates, and promises—before approval. The approval checkbox records review only; nothing is sent. This is a human review aid, not a deterministic validator of live Bedrock output or a guarantee against hallucinations.
- Regression coverage asserts the fallback avoids those claims and the system prompt states the no-commitment rule. Full backend suite: **167 passed** (two upstream deprecation warnings); frontend build passed. Published in `c83623be9d6451e66276d5a13bb56af98b5feaa8`. GitHub quality passed; CodeQL completed successfully with the processing annotation captured in the current repository snapshot. No live Bedrock evaluation or customer review was performed.

### Continuation update — 2026-09-24

- Identified the original opt-out detector's narrow literal phrase list as a customer-safety gap. Expanded deterministic English phrase normalization and coverage for common stop-contact, unsubscribe, remove/delete, and future-message requests. Matching uses punctuation/case/Unicode-apostrophe normalization and includes negative/informational regression examples to reduce false suppressions.
- Follow-up privacy gap: explicit English access/erasure wording now creates metadata-only tenant-scoped records at manual and signed-webhook intake, atomically with lead and initial audit persistence. The admin queue supports tenant pagination, staged status transitions, and audit-linked conditional updates; lead timelines expose the request ID/status. A persisted per-lead hold blocks analysis, response actions, and rescue for that record; erasure requests also trigger contact suppression. A separate future sales inquiry must arrive as a new lead. The queue does not verify identity, discover all contact records, fulfill exports/erasure, or manage retention/legal holds. Local checks pass, but the source change has not been deployed.
- Added privacy workflow regression coverage for explicit/negative request phrases, lead hold and blocked sales actions, audited request transitions, metadata minimization, and erasure contact suppression. The tests exposed a mutable in-memory repository read that caused every status update to self-conflict; memory reads now return deep copies. The suite also added the explicit wording “I want a copy of my data” to access detection. This remains phrase-based English handling, not a semantic or multilingual classifier.
- Added an admin-only candidate-record discovery route, gated on manually attested identity verification. It pages records through existing HMAC-keyed email/phone GSIs, emits only lead ID/date/source/lifecycle (no contact details or message), and audits the matched record IDs per page. This is identifier-based discovery inside the LeadRescue lead store, not a full subject export or cross-system inventory; DynamoDB GSI consistency and legacy-index cutover must be validated in staging.
- The same `check_opt_out` policy is applied at manual lead creation, inbound signed webhook intake, policy analysis, and subsequent durable suppression handling. New tests validate direct guardrail behavior and API intake lifecycle outcomes. This does not replace provider-authoritative consent events or multilingual review.
- Synchronous analysis and durable analysis-job submission both reject suppressed contacts before inference; the analysis core rechecks at worker execution to cover a job queued before an opt-out. Regression coverage verifies the sync and queued entry points.
- The new worker regression exposed a model-schema defect: `analyze_lead_core` read/wrote `last_analysis_job_id`, but that field was missing from `Lead` (it was only on `LeadUpdate`). Added it to the persisted lead schema with a `None` default so current rows remain readable; tests cover completed SQS redelivery not repeating model inference.
- Added direct worker and job-repository tests for idempotency, claim/retry/lease recovery, job success, duplicate delivery, terminal and retryable errors, opt-out handling, and DLQ worker crashes.
- Full backend suite passes **149 tests with 1 upstream deprecation warning** on Python 3.11 after the queue lifecycle test expansion.
- Local full npm audit reported **0 vulnerabilities**. Hashed-lock Python audit reported **no known vulnerabilities** with `pip-audit --disable-pip --require-hashes`; a resolver-based audit was incompatible with this Linux-targeted lock on Windows, so it was rerun directly against the hashed lock. GitHub Actions run [35914056333](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35914056333) passed both dependency audits and frontend build, backend tests, syntax, and SAM validation on commit `7eb1754`.
- Opt-out hardening is committed as `e568489881a5c5ffe3c336a4c37b31045848ebe0`; GitHub Actions [35912050383](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35912050383) passed.
- Worker idempotency schema fix is committed as `4e6063a89cf35dfb9ba4bb365fb4067c593b102d`; it was verified as live GitHub `main`, and Actions [35912622730](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35912622730) passed. The worktree was clean after its push. Staging queue behavior and Bedrock inference remain unverified.

- Snapshot below records the state at publication of the first benchmark, followed by the 2026-09-24 continuation and publication evidence.
- At the start of the 2026-09-24 continuation, local `main` was `4ff4df5d87d96ed0e5a6edd5a40902c7b884a9cb` (`docs: sync audit with published benchmark`). This commit had previously been verified on GitHub `main`, and its CI run [35889942567](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35889942567) passed.
- The 2026-09-24 continuation added two exact-response prompt-injection canaries, narrow response-policy language, regression tests, and updated benchmark notes. Commit `0960d9066c4ac774821472b16b5f2ae87760f3c1` is pushed and verified as live GitHub `main`; Actions run [35910999823](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35910999823) passed both frontend and backend/SAM jobs. The worktree was clean immediately after push.
- The older `PROJECT_AUDIT_HANDOFF.md` contains older audit-time details. Its top note points to this file as current source of truth; prefer the checkout facts above.
- `MARKET_READINESS.md` is the broad gap register; `README.md`, `ARCHITECTURE.md`, `INTEGRATIONS.md`, `template.yaml`, and backend migration scripts provide more detailed claims and procedures.
- Agent-evaluation update (2026-09-24): the synthetic corpus is now version `2026-09-24.1` with 20 cases and four literal injection canaries, including Hinglish, returning-customer, non-sales, urgency, and support cases. The scorer checks forbidden fragments across product/location/entities/summary/recommendation/response text, while keeping model-authored text and canary values out of reports. The runner still requires explicit permission for potentially billed inference and rejects heuristic fallback. Python compilation and the complete local backend suite pass (**160 passed**, one third-party Mangum deprecation warning). Live Bedrock inference remains unrun; labels/thresholds are exploratory, not customer-calibrated, and literal canaries do not demonstrate broad prompt-injection resistance.
- Publication verification (2026-09-24): commit `ba9c949c2c508c06fdfece904562dd09085ea324` is present on local `main`, `origin/main`, and GitHub `main`; the working tree is clean. GitHub Actions run [35921915821](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35921915821) completed successfully: frontend production build and backend/SAM validation both passed. No AWS staging deployment or live customer integration was performed.
- Security-analysis improvement (2026-09-24): added `.github/workflows/codeql.yml` to analyze JavaScript/TypeScript and Python on pull requests, pushes to `main`, and weekly using immutable action SHAs. The first scan found high-severity clear-text logging of the Secrets Manager ARN; the helper now omits the ARN from stdout. Follow-up CodeQL run [35922904976](https://github.com/TejasviUpadhyay1907/Lead_Agent/actions/runs/35922904976) passed both language analyses, and GitHub now marks the finding fixed with zero open code-scanning alerts. A Node 20 deprecation in the initial checkout pin was also corrected. CodeQL is one static-analysis layer, not a complete security review; repository branch protection remains unchecked.

## Readiness by evidence category

| Category | Current position | What is still needed |
|---|---|---|
| Source architecture | Strong prototype foundation | Independent design/security review and architecture decisions based on one real customer's constraints |
| Automated source checks | Useful baseline; documented green CI | Branch protection, security/dependency scanning, cloud integration coverage, reliability and regression gates |
| Frontend/UX | Main workflow screens exist | Real operator walkthroughs, accessibility review, usability findings, validated OIDC/session behavior |
| Agent quality | Structured agent plus deterministic fallback/policy; a 20-case synthetic benchmark scores six structured fields and checks four literal canaries across all model-authored text. Local tests pass, but the live benchmark has not been run against Bedrock and labels/thresholds remain exploratory. | Broaden and review realistic and adversarial cases, score groundedness and unsafe claims, calibrate acceptance thresholds with a customer, run on the approved staging model, and collect model/version, latency, error, and token/cost regression evidence. |
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

Continue the versioned 20-case synthetic benchmark with broader language, ambiguous/no-evidence, opt-out, and adversarial prompt-injection cases; review labels with a sales domain expert. The runner scores intent/urgency/customer-stage and product/quantity/location, refuses deterministic fallback results, requires explicit billed-inference confirmation, checks canaries in every model-authored text field, and excludes raw messages/generated text/canary values from reports. A canary pass does not prove general prompt-injection resistance. Current labels and thresholds are exploratory, not release gates. Score grounded response drafts, unsafe claims, and suppression behavior; run against the approved staging model and calibrate acceptance with a design partner. Add model/version, latency, error, token/cost metrics without collecting unnecessary PII. Load-test expected tenant volume and queue/backlog/throttle behavior. Exercise PITR restore, worker retries/DLQ replay, alarm delivery, and incident runbooks. Define SLOs, RPO/RTO, and per-customer spend limits and measure them.

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

> Continue the industrial-readiness goal for LeadRescue AI in `C:\Users\tejas\OneDrive\Desktop\TEST\Lead_Agent`. Read `CURRENT_AUDIT_2026-09-23.md`, `MARKET_READINESS.md`, and `INTEGRATIONS.md`, then inspect the current Git state. This React/Vite + FastAPI/Python 3.12 + Strands/Bedrock lead-triage system has deterministic scoring/policy, OIDC and isolated tenant controls, DynamoDB, SQS analysis, Zoho create-only intake, outcome reporting, privacy workflows, and an opt-in Meta WhatsApp path. Commit `50e4336d6bae8c172835cbf6e8ccd80f1b38e49d` has 178 local backend tests passing plus frontend build, Python compilation, SAM lint, and diff checks; GitHub checks are pending after the earlier `7ef67c8` quality failure was repaired. WhatsApp send requires evidence-backed current-phone consent, exact-draft human approval, signed-in separate confirmation tied to the current template/account preview, and a durable one-attempt record. Signed callbacks and inbound STOP suppression are implemented; actual Meta/Zoho sandbox and AWS staging are not. Zoho has no OAuth/edit sync/writeback. Product is pre-staging and not generally sellable. Next milestone: run the Zoho and Meta flows in a design-partner sandbox, then prove the full guarded send/receipt/STOP/replay/ambiguous-outcome workflow in isolated AWS staging; resolve retention, subject-wide privacy fulfillment, legacy status correction, real IdP/Bedrock deployment, restore/security/load evidence, and measured ROI before sale. The recommended pilot is Zoho CRM + Meta WhatsApp Business Platform for an India SMB, subject to partner confirmation. Keep the whole industrial-readiness goal active and do not claim “top 1%” without measured evidence.
