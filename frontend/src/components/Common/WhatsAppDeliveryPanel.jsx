import React from 'react';
import { CheckCheck, Clock3, MessageCircle, RefreshCw, Send, ShieldAlert } from 'lucide-react';
import { dateTime, humanize, isBlocked } from '../../api/presentation';
import { Notice, SectionHeader } from './UI';

const terminalOrAmbiguous = new Set(['submitting', 'unknown', 'accepted', 'sent', 'delivered', 'read', 'failed']);

export function WhatsAppDeliveryPanel({ lead, messages, config, busy, onRequestSend, onRefresh }) {
    const latest = messages[0];
    const consentMatches = Boolean(lead.whatsapp_consent?.recipient_phone_key && lead.customer_phone);
    const approved = lead.response_status === 'approved'
        && Boolean(lead.response_draft)
        && Boolean(lead.approved_draft_sha256)
        && Boolean(lead.approval_attested_at);
    const sameApproval = Boolean(latest
        && latest.approved_draft_sha256 === lead.approved_draft_sha256
        && latest.approval_attested_at === lead.approval_attested_at);
    const canRequest = !busy && !isBlocked(lead) && consentMatches && approved
        && config?.configured && config?.outbound_enabled && config?.template_body
        && (!sameApproval || !terminalOrAmbiguous.has(latest.status));
    const renderedPreview = config?.template_body?.replace('{{1}}', lead.response_draft || '');

    return <section className="panel whatsapp-delivery-panel">
        <SectionHeader icon={MessageCircle} title="WhatsApp delivery" subtitle="One human-approved attempt, with provider status receipts">
            <div className="delivery-header-actions">{latest && <span className="badge-sub">{humanize(latest.status)}</span>}<button className="btn-text" type="button" onClick={onRefresh}><RefreshCw size={13} /> Refresh status</button></div>
        </SectionHeader>
        <Notice tone={latest?.status === 'failed' ? 'warning' : latest?.status === 'unknown' || latest?.status === 'submitting' ? 'warning' : 'info'}>
            {isBlocked(lead)
                ? 'This lead is blocked from outreach.'
                : !consentMatches
                    ? 'Record verified permission for the current phone number before sending.'
                    : !config?.configured || !config?.outbound_enabled
                        ? 'WhatsApp provider delivery is not enabled for this deployment.'
                        : !approved
                        ? 'A current, human-approved response is required before sending.'
                        : sameApproval && (latest?.status === 'unknown' || latest?.status === 'submitting')
                            ? 'Provider outcome is uncertain. The system will not resend automatically; wait for a signed provider receipt or reconcile with the provider.'
                            : sameApproval && latest?.status === 'failed'
                                ? 'The provider rejected this attempt. Review the error and response, then revise and approve a new draft before another attempt.'
                                : sameApproval && latest
                                    ? 'This approved response already has a delivery attempt. The same approval cannot be sent again.'
                                    : 'The server rechecks consent, opt-out, privacy hold, current phone, and draft approval immediately before one template-based provider attempt.'}
        </Notice>
        {messages.map(message => <div className="whatsapp-delivery-record" key={message.message_id}>
            <span className="delivery-icon">{['sent', 'delivered', 'read'].includes(message.status) ? <CheckCheck size={17} /> : message.status === 'unknown' ? <ShieldAlert size={17} /> : <Clock3 size={17} />}</span>
            <span><strong>{humanize(message.status)}</strong><small>{dateTime(message.updated_at)} · {message.template_name} ({message.template_language})</small></span>
            {message.provider_message_id && <small className="delivery-reference">Provider receipt recorded</small>}
            <p className="delivery-copy">{message.rendered_message}</p>
        </div>)}
        {approved && config?.template_body && <div className="consent-evidence"><span><strong>Configured Meta template</strong>{config.template_name} ({config.template_language})</span><span><strong>Rendered message preview</strong>{renderedPreview}</span></div>}
        {!lead.customer_phone && <p className="form-note">Add a phone number in E.164 format before WhatsApp can be used.</p>}
        <button className="btn-primary" type="button" disabled={!canRequest} onClick={onRequestSend}>
            <Send size={15} /> {busy ? 'Submitting one attempt…' : 'Review and send approved response'}
        </button>
        <p className="form-note">Delivery is disabled unless this deployment has an explicitly enabled, customer-configured Meta provider secret.</p>
    </section>;
}
