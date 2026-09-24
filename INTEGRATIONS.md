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

### Connector boundary to implement

Do not point a Zoho webhook directly at `POST /integrations/v1/leads` and call that a Zoho integration. The current endpoint requires an HMAC signature over a fresh timestamp, provider, idempotency key, and exact raw body. Zoho's configurable webhook body/headers are not evidence that it can generate this signature scheme. Confirm delivery/auth behavior in a Zoho sandbox before selecting the transport. A dedicated Zoho adapter or narrowly scoped relay should:

1. Authenticate the configured Zoho sender with a per-customer secret held in Secrets Manager; keep the shared secret out of Zoho field values and browser code. Rate-limit the route and compare tokens in constant time.
2. Accept only a documented allowlist of lead fields. Preserve the Zoho record ID, `Created_Time`, and `Modified_Time` as external source metadata; use record ID plus modification version for idempotency so retries collapse while subsequent edits remain distinct.
3. Map Zoho fields to LeadRescue fields through validated per-customer mapping. Preserve the original inquiry text and source channel; reject or quarantine malformed records rather than creating a misleading partial lead.
4. Persist a durable external-record mapping and connector state atomically with the event. Enforce a unique tenant/provider/external-record key so Zoho retries or simultaneous updates cannot create duplicate local leads. Define conflict ownership and field-level writeback rules before enabling CRM writes.
5. Add a scheduled or operator-triggered reconciliation path to find webhook failures and resynchronize modified records. Expose last-success, lag, retry, and error state without logging lead PII.
6. Use Zoho OAuth scopes limited to the required modules/actions. Store and rotate tokens server-side; revoke and delete them on customer disconnect. Validate account-specific API domain, sandbox/production org selection, token refresh, rate limits, and API credit behavior against vendor docs and the pilot account.

### WhatsApp delivery gates

The Zoho adapter is only the source/CRM side; it does not authorize outreach. A separate provider adapter must require recorded consent context for the WhatsApp channel, check durable suppression immediately before enqueue and again before send, require a human-approved rendered message/template, and use provider idempotency where available. Persist the provider message ID and distinguish accepted, sent, delivered, read, failed, and unknown states from provider webhooks. Retries and webhook replays must not create duplicate sends or claim that approval means delivery. Message-template selection, opt-in wording, supported categories, and any country-specific legal requirements must be reviewed with the pilot customer before live sending.

### Do not claim until verified

Zoho CRUD APIs, Zoho webhooks, the generic signed inbound webhook, and a WhatsApp developer sandbox each prove only a limited capability. Do not describe the product as bidirectionally synchronized or as sending WhatsApp messages until staging evidence shows OAuth connection/revocation, mapped record create/update, retry and reconciliation, consent denial, approved-template enforcement, real provider delivery receipts, opt-out enforcement, audit history, and CRM writeback behavior end to end.
