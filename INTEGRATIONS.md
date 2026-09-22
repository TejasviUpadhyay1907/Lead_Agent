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
