# Inbound lead webhook

LeadRescue now accepts signed lead events at `POST /integrations/v1/leads`. This is a vendor-neutral inbound connector for CRMs, web forms, and automation tools that can send HTTPS webhooks. It creates a lead and audit event; it does not write back to the source CRM or send customer messages.

## Configure

1. Create a high-entropy HMAC secret in AWS Secrets Manager for this customer deployment. Store it as the secret string, or as JSON with a `secret` field.
2. Set the SAM `WebhookSecretArn` parameter to that secret's ARN. The Lambda role receives `secretsmanager:GetSecretValue` only for that ARN.
3. Deploy the `ProcessedEventsTable`, then verify the API is in production mode and the lead/audit tenant indexes and data backfill are ready.
4. Configure the source system to send the JSON body and headers below. The sender signs each retry using a fresh timestamp and the same idempotency key.

Keep the HMAC secret in a server-side connector or automation. Never embed it in a browser application or public form page.

## Request format

JSON body (maximum 256 KB):

```json
{
  "customer_name": "Asha Rao",
  "customer_email": "asha@example.com",
  "customer_phone": "+91-9000000000",
  "source": "website",
  "message": "Please send a quote for 20 units."
}
```

Required headers:

- `X-Webhook-Timestamp`: Unix time in seconds; requests older/newer than five minutes are rejected.
- `X-Webhook-Provider`: short provider identifier, such as `hubspot` or `website`.
- `Idempotency-Key`: stable source event ID, reused on retries.
- `X-Webhook-Signature`: `sha256=` followed by the lowercase HMAC-SHA256 hex digest.

The signed bytes are:

```text
timestamp + "." + provider + "." + idempotency_key + "." + raw_request_body
```

The signature is `HMAC-SHA256(secret, signed_bytes)`. Sign the exact serialized body bytes sent over HTTP; do not parse and reserialize JSON between signing and sending.

Example in Python:

```python
import hashlib, hmac, json, time, requests

body = json.dumps(payload, separators=(",", ":")).encode()
timestamp = str(int(time.time()))
provider = "website"
event_id = "form-submission-18429"
canonical = timestamp.encode() + b"." + provider.encode() + b"." + event_id.encode() + b"." + body
signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
response = requests.post(
    endpoint,
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Provider": provider,
        "Idempotency-Key": event_id,
        "X-Webhook-Signature": "sha256=" + signature,
    },
    timeout=10,
)
```

## Delivery behavior

- First accepted delivery returns `201` with `accepted: true`, `duplicate: false`, and the new `lead_id`.
- A repeated provider/idempotency key returns `200` with the original `lead_id`; no second lead or audit event is created.
- Reusing a new-format idempotency key with a different raw request body returns `409`. Retries must use the same serialized body and key, with a fresh timestamp and signature.
- Signature, timestamp, schema, and payload errors return `4xx`. Retry transient `503` responses with the same event ID, a fresh timestamp, and a new signature.
- Lead, audit, and deduplication records are committed in one DynamoDB transaction. Deduplication markers expire after 30 days.
- Markers written before payload-digest enforcement are deduplicated during their remaining TTL but cannot be checked for body reuse; new markers enforce payload matching.
- Opt-out wording is checked before the lead is persisted. A tenant-scoped email/phone suppression key is stored in the same transaction and blocks outreach actions across future matching leads. The sender must still synchronize consent/opt-out state with its own CRM; no outbound message is sent.

This generic webhook is the first integration adapter. Vendor OAuth sync, source-system field mapping, bidirectional updates, delivery receipts, and connector health dashboards remain separate work.

## Recommended first-pilot connector: Zoho CRM + WhatsApp Business Platform

This is the current default for an India-based SMB pilot, subject to confirmation by the design partner. It is a working candidate, not a claim that either integration exists in the application. Zoho CRM exposes OAuth 2.0 delegated access and webhook configuration for record events; Zoho webhooks can send dynamic CRM fields and configured custom headers. See the [OAuth overview](https://www.zoho.com/crm/developer/docs/api/v8/oauth-overview.html) and [webhook configuration API](https://www.zoho.com/crm/developer/docs/api/v8/create-webhook.html). WhatsApp Business Platform provides a test/sandbox path and webhooks, while its [current messaging policy](https://whatsappbusiness.com/policy/) requires recipient permission, opt-out compliance, and approved templates to initiate conversations.

### Zoho CRM lead-create intake (implemented; staging validation still required)

`POST /integrations/v1/zoho/leads` accepts a strict mapped JSON body and a dedicated `X-LeadRescue-Token` header. Set `ZohoWebhookSecretArn` at deployment to a separate Secrets Manager secret containing a random token of at least 32 characters (plain secret string or JSON `{"token":"..."}`). Leave the parameter empty to disable this route; do not reuse the generic HMAC webhook secret. The Lambda role receives read access only to the configured Zoho secret. Rotate by updating the secret and account for the one-minute in-process cache before removing the old token.

Configure a Zoho CRM webhook with method `POST`, raw JSON body, and a custom header named `X-LeadRescue-Token`. A representative mapping is:

```json
{
  "record_id": "${!Leads.Id}",
  "customer_name": "${!Leads.Full_Name}",
  "customer_email": "${!Leads.Email}",
  "customer_phone": "${!Leads.Phone}",
  "source": "website",
  "message": "${!Leads.Description}"
}
```

Set the `source` value to one supported LeadRescue source for that workflow. Map `message` to a required field that contains the actual inquiry; do not use an invented placeholder, since that would mislead analysis and operators. Configure the Zoho workflow rule to trigger only when a lead is created. The API permanently deduplicates by tenant + Zoho record ID: identical retries return the original local lead, while a changed payload for the same ID returns `409` and never creates a second lead. This route ingests a new lead; it does not import updates to an existing Zoho lead, write changes back to Zoho, or provide OAuth-based connection management. Do not enable the route in production until the mapped webhook body, field escaping, secret rotation, retry behavior, and event behavior have been observed against the pilot's Zoho sandbox.

### Meta WhatsApp consent, delivery, and receipts (code implemented; sandbox evidence pending)

Operators record evidence through `PUT /api/leads/{lead_id}/whatsapp-consent`. The API requires an E.164 number, timezone-aware consent time, controlled source, evidence reference, consent-text version, and explicit operator verification. It stores a tenant-keyed HMAC of the current phone number. The write and audit event are atomic, identical evidence is idempotent, and privacy holds or durable opt-outs block consent capture. Human approval stores the exact draft hash, approver, and timestamp; edits/rejection invalidate that binding.

`POST /api/leads/{lead_id}/whatsapp-messages` is a separate, explicit operator action and requires `{"send_confirmed": true}` plus the non-secret fingerprint of the exact account, API version, template, language, and body preview shown in the UI. The server rejects a stale preview, verifies current phone-HMAC binding, consent, durable suppression, privacy hold, lead state, and current approved-draft hash both before persisting an attempt and immediately before the external request. It renders and displays the configured template with the approved draft, persists the exact rendered message and hashes, then makes one fixed-host HTTPS request. Deterministic attempt IDs and a conditional DynamoDB insert prevent duplicate network sends for the same approval/evidence/template/account fingerprint. A repeat request returns the existing status. A definite provider rejection becomes `failed`; a timeout or ambiguous response becomes `unknown`; ambiguous attempts are never automatically resent. `accepted` means Meta accepted the API request, not that the customer received the message.

The authenticated operator view uses `GET /api/whatsapp/configuration` for a secret-free template preview and `GET /api/leads/{lead_id}/whatsapp-messages` for delivery history. The provider secret is configured only by Secrets Manager through `WhatsAppSecretArn`, as JSON with `access_token`, `phone_number_id`, `app_secret`, `verify_token`, `api_version`, `template_name`, `template_language`, and `template_body`. `template_body` must match the pilot-approved Meta template and contain exactly one `{{1}}` body parameter. The API reveals only template metadata/body to signed-in operators; never put tokens in environment variables, Zoho fields, or frontend config. `WhatsAppOutboundEnabled` defaults to `false`; local/test demo mode always blocks external sends.

`GET /integrations/v1/whatsapp/webhook` implements Meta's verification challenge. The POST endpoint verifies `X-Hub-Signature-256` against the exact raw body, correlates provider statuses using opaque callback data/provider IDs, and applies idempotent, timestamp-ordered `sent`, `delivered`, `read`, and `failed` updates with audit records. When a callback includes opaque attempt data, the handler now refuses to replace a different provider message ID already bound to that attempt; a first callback can still bind the provider ID if it arrives before the send response. Text and quick-reply opt-out phrases (including exact `STOP`) create a durable tenant phone suppression, even when no local lead exists; matching existing leads receive idempotent per-lead audit events. The inbound opt-out parser is currently English phrase-based and does not handle all languages, media, or every future message type.

The exact rendered message is stored in the WhatsApp message table and included in the company-admin lead export. This is personal/business communication data; retention, subject-wide export/deletion across provider and CRM systems, key ownership, and legal-hold policy still require customer-specific design and deployment proof. Delivery history currently exposes the latest 50 attempts in the operator view, while the admin export reads all pages.

This code has not been exercised with Meta test credentials, an approved pilot template, or a deployed callback URL. No WhatsApp credential is configured in this repository and the SAM outbound switch is off by default. The operator must verify the source evidence and consent wording; these fields are an auditable operator attestation, not legal validation. Meta's current [opt-in requirements](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in/) require permission and clear business/communication expectations. Because LeadRescue does not track the 24-hour customer-service window, this implementation always uses a pre-approved template; the pilot owner must approve its category/content. See the [message/window rules](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages) and [webhook signature guidance](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint/).

### Connector boundary to implement

Do not point a Zoho webhook directly at `POST /integrations/v1/leads` and call that a Zoho integration. The current endpoint requires an HMAC signature over a fresh timestamp, provider, idempotency key, and exact raw body. Zoho's configurable webhook body/headers are not evidence that it can generate this signature scheme. Confirm delivery/auth behavior in a Zoho sandbox before selecting the transport. A dedicated Zoho adapter or narrowly scoped relay should:

1. Authenticate the configured Zoho sender with a per-customer secret held in Secrets Manager; keep the shared secret out of Zoho field values and browser code. Rate-limit the route and compare tokens in constant time.
2. Accept only a documented allowlist of lead fields. Preserve the Zoho record ID, `Created_Time`, and `Modified_Time` as external source metadata; use record ID plus modification version for idempotency so retries collapse while subsequent edits remain distinct.
3. Map Zoho fields to LeadRescue fields through validated per-customer mapping. Preserve the original inquiry text and source channel; reject or quarantine malformed records rather than creating a misleading partial lead.
4. Persist a durable external-record mapping and connector state atomically with the event. Enforce a unique tenant/provider/external-record key so Zoho retries or simultaneous updates cannot create duplicate local leads. Define conflict ownership and field-level writeback rules before enabling CRM writes.
5. Add a scheduled or operator-triggered reconciliation path to find webhook failures and resynchronize modified records. Expose last-success, lag, retry, and error state without logging lead PII.
6. Use Zoho OAuth scopes limited to the required modules/actions. Store and rotate tokens server-side; revoke and delete them on customer disconnect. Validate account-specific API domain, sandbox/production org selection, token refresh, rate limits, and API credit behavior against vendor docs and the pilot account.

### WhatsApp delivery gates

The Zoho adapter is only the source/CRM side; it does not authorize outreach. Core consent, approval, send, and signed receipt code now exists, but production readiness still requires a real pilot account. Validate exact Meta template content, test-number delivery, callback challenge/signature, reordered/replayed callbacks, opt-out suppression, provider timeout reconciliation, and role/access behavior in isolated AWS staging. Document message retention and data-subject fulfillment across LeadRescue, Zoho, and Meta; obtain customer/privacy/legal approval for consent wording, template category, retention, and country-specific obligations before enabling the kill switch. Zoho webhook field interpolation/retries also require sandbox evidence.

### Do not claim until verified

Zoho CRUD APIs, Zoho webhooks, the generic signed inbound webhook, and a WhatsApp developer sandbox each prove only a limited capability. Do not describe the product as bidirectionally synchronized or as sending WhatsApp messages until staging evidence shows OAuth connection/revocation, mapped record create/update, retry and reconciliation, consent denial, approved-template enforcement, real provider delivery receipts, opt-out enforcement, audit history, and CRM writeback behavior end to end.
