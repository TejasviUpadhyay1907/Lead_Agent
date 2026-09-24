import React, { useState } from 'react';
import { CheckCircle2, MessageSquare, ShieldCheck } from 'lucide-react';
import { api } from '../../api/client';
import { dateTime, safeError } from '../../api/presentation';
import { BusyLabel, Notice, SectionHeader } from './UI';

const initialForm = {
    consented_at: '',
    source: 'website_form',
    evidence_ref: '',
    text_version: '',
    explicit_permission_verified: false,
};

export function WhatsAppConsentPanel({ lead, onSaved }) {
    const [form, setForm] = useState(initialForm);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const optedOut = lead.lifecycle_status === 'opted_out';
    const blocked = optedOut || Boolean(lead.privacy_hold);
    const canRecord = !blocked && Boolean(lead.customer_phone);

    const update = (key, value) => setForm(current => ({ ...current, [key]: value }));
    const submit = async event => {
        event.preventDefault();
        if (busy || !canRecord || !form.explicit_permission_verified) return;
        setBusy(true);
        setError('');
        try {
            const result = await api.recordWhatsAppConsent(lead.lead_id, {
                ...form,
                consented_at: new Date(form.consented_at).toISOString(),
            });
            onSaved(result);
            setForm(initialForm);
        } catch (cause) {
            setError(safeError(cause, 'Consent evidence could not be recorded. Refresh the lead and audit before retrying.'));
        } finally {
            setBusy(false);
        }
    };

    return <section className="panel whatsapp-consent-panel">
        <SectionHeader icon={MessageSquare} title="WhatsApp contact permission" subtitle="Consent is separate from a lead inquiry and human approval">
            {lead.whatsapp_consent && <span className="badge-sub"><CheckCircle2 size={13} /> Permission recorded</span>}
        </SectionHeader>
        <Notice tone={blocked ? 'warning' : 'info'}>
            {optedOut
                ? 'This contact is suppressed. Consent cannot override an opt-out.'
                : lead.privacy_hold
                    ? 'Consent changes are paused while this privacy request is reviewed.'
                    : 'Do not infer permission from a phone number or inquiry. Record only explicit WhatsApp permission you verified in the referenced source. Permission is only one prerequisite; sending also requires a separate human action and an enabled Meta configuration.'}
        </Notice>
        {lead.whatsapp_consent && <div className="consent-evidence">
            <span><strong>Source</strong>{lead.whatsapp_consent.source.replaceAll('_', ' ')}</span>
            <span><strong>Permission date</strong>{dateTime(lead.whatsapp_consent.consented_at)}</span>
            <span><strong>Evidence reference</strong>{lead.whatsapp_consent.evidence_ref}</span>
            <span><strong>Text version</strong>{lead.whatsapp_consent.text_version}</span>
        </div>}
        {!lead.customer_phone && <p className="form-note">Add a valid E.164 phone number before recording WhatsApp permission.</p>}
        {canRecord && <form className="consent-form" onSubmit={submit}>
            <label className="filter-field">Consent source
                <select className="field-input" value={form.source} onChange={event => update('source', event.target.value)} disabled={busy}>
                    <option value="website_form">Website form</option>
                    <option value="zoho_crm">Zoho CRM evidence</option>
                    <option value="inbound_whatsapp">Inbound WhatsApp</option>
                    <option value="signed_document">Signed document</option>
                    <option value="other_verified_record">Other verified record</option>
                </select>
            </label>
            <label className="filter-field">Consent date and time
                <input className="field-input" type="datetime-local" required value={form.consented_at} onChange={event => update('consented_at', event.target.value)} disabled={busy} />
            </label>
            <label className="filter-field">Evidence reference
                <input className="field-input" required maxLength={256} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}" value={form.evidence_ref} onChange={event => update('evidence_ref', event.target.value)} placeholder="Form entry ID or CRM record reference" disabled={busy} />
            </label>
            <label className="filter-field">Consent wording version
                <input className="field-input" required maxLength={128} pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}" value={form.text_version} onChange={event => update('text_version', event.target.value)} placeholder="For example, wa-opt-in-v2" disabled={busy} />
            </label>
            <label className="consent-attestation">
                <input type="checkbox" checked={form.explicit_permission_verified} onChange={event => update('explicit_permission_verified', event.target.checked)} disabled={busy} />
                <span>I verified the source evidence. It clearly identifies the company, describes follow-up messages, and records permission to contact <strong>{lead.customer_phone}</strong> on WhatsApp.</span>
            </label>
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="btn-secondary" type="submit" disabled={busy || !form.explicit_permission_verified}>
                {busy ? <BusyLabel>Recording consent…</BusyLabel> : <><ShieldCheck size={15} /> Record verified consent</>}
            </button>
        </form>}
    </section>;
}
