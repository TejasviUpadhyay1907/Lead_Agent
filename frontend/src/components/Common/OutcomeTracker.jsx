import React, { useEffect, useRef, useState } from 'react';
import { BadgeCheck, Save } from 'lucide-react';
import { api } from '../../api/client';
import { humanize, safeError } from '../../api/presentation';
import { BusyLabel, Notice, SectionHeader } from './UI';

export function OutcomeTracker({ lead, onSaved }) {
    const [outcome, setOutcome] = useState(lead.sales_outcome || '');
    const [amount, setAmount] = useState(lead.sales_value ?? '');
    const [currency, setCurrency] = useState(lead.sales_currency || '');
    const [reason, setReason] = useState(lead.sales_outcome_reason || '');
    const [saving, setSaving] = useState(false);
    const [notice, setNotice] = useState(null);
    const onSavedRef = useRef(onSaved);

    useEffect(() => {
        onSavedRef.current = onSaved;
    }, [onSaved]);

    useEffect(() => {
        setOutcome(lead.sales_outcome || '');
        setAmount(lead.sales_value ?? '');
        setCurrency(lead.sales_currency || '');
        setReason(lead.sales_outcome_reason || '');
    }, [lead.lead_id, lead.sales_outcome, lead.sales_value, lead.sales_currency, lead.sales_outcome_reason]);

    useEffect(() => {
        if (lead.crm_sync_status !== 'pending') return undefined;
        let attempts = 0;
        const timer = window.setInterval(async () => {
            attempts += 1;
            try {
                const current = await api.getLead(lead.lead_id);
                onSavedRef.current(current);
                if (current.crm_sync_status !== 'pending' || attempts >= 12) window.clearInterval(timer);
            } catch {
                if (attempts >= 12) window.clearInterval(timer);
            }
        }, 5000);
        return () => window.clearInterval(timer);
    }, [lead.lead_id, lead.crm_sync_event_id, lead.crm_sync_status]);

    const blocked = lead.privacy_hold || lead.lifecycle_status === 'opted_out';
    const needsReason = ['lost', 'disqualified'].includes(outcome);
    const hasAmount = String(amount).trim() !== '';

    const submit = async event => {
        event.preventDefault();
        if (!outcome || saving || blocked) return;
        setSaving(true);
        setNotice(null);
        try {
            const payload = { outcome, reason: reason.trim() || null };
            if (hasAmount) {
                payload.sales_value = amount;
                payload.sales_currency = currency.trim().toUpperCase();
            }
            const updated = await api.updateSalesOutcome(lead.lead_id, payload);
            onSaved(updated);
            setNotice({ tone: 'success', text: updated.crm_sync_status === 'pending'
                ? 'Outcome recorded. Zoho CRM writeback is queued.'
                : 'Outcome recorded in the audit history.' });
        } catch (error) {
            setNotice({ tone: 'error', text: safeError(error, 'The outcome could not be saved. Refresh the lead before retrying.') });
        } finally {
            setSaving(false);
        }
    };

    return (
        <section className="panel outcome-panel">
            <SectionHeader icon={BadgeCheck} title="Sales outcome" subtitle="Operator-entered result for measuring business impact." />
            {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
            {lead.sales_outcome && (
                <p className="outcome-current">
                    Recorded as <strong>{humanize(lead.sales_outcome)}</strong>
                    {lead.sales_value != null && lead.sales_currency && <> · {lead.sales_currency} {lead.sales_value}</>}
                    {lead.sales_outcome_at && <> · {new Date(lead.sales_outcome_at).toLocaleString()}</>}
                </p>
            )}
            {lead.crm_sync_status && (
                <div className={`crm-sync-state crm-sync-${lead.crm_sync_status}`} role="status" aria-live="polite">
                    <strong>Zoho sync: {humanize(lead.crm_sync_status)}</strong>
                    {lead.crm_sync_error_code && <span>{humanize(lead.crm_sync_error_code.replaceAll('_', ' '))}. Review the CRM record and mapping before retrying.</span>}
                    {lead.crm_sync_updated_at && <small>Updated {new Date(lead.crm_sync_updated_at).toLocaleString()}</small>}
                </div>
            )}
            {blocked ? (
                <p className="form-note">Outcome changes are paused for this lead by a privacy or opt-out safeguard.</p>
            ) : (
                <form className="outcome-form" onSubmit={submit}>
                    <label className="field">
                        <span className="field-label">Result</span>
                        <select className="field-input" required value={outcome} onChange={event => setOutcome(event.target.value)}>
                            <option value="">Choose an outcome</option>
                            <option value="won">Won</option>
                            <option value="lost">Lost</option>
                            <option value="disqualified">Disqualified</option>
                        </select>
                    </label>
                    {outcome === 'won' && <div className="outcome-value-fields">
                        <label className="field">
                            <span className="field-label">Confirmed deal value <span className="field-optional">(optional)</span></span>
                            <input className="field-input" type="number" min="0" max="1000000000000000" step="0.0001" value={amount} onChange={event => setAmount(event.target.value)} />
                        </label>
                        <label className="field">
                            <span className="field-label">Currency</span>
                            <input className="field-input" type="text" inputMode="text" autoCapitalize="characters" pattern="[A-Za-z]{3}" maxLength={3} required={hasAmount} value={currency} onChange={event => setCurrency(event.target.value.toUpperCase())} placeholder="INR" />
                        </label>
                    </div>}
                    <label className="field">
                        <span className="field-label">Reason {needsReason ? <span className="required-mark">(required)</span> : <span className="field-optional">(optional)</span>}</span>
                        <textarea className="field-input outcome-reason" maxLength={500} required={needsReason} value={reason} onChange={event => setReason(event.target.value)} placeholder={needsReason ? 'Record why the opportunity was lost or disqualified.' : 'Add context for this result.'} />
                    </label>
                    <div className="form-actions">
                        <button type="submit" className="btn-secondary" disabled={saving || !outcome}>
                            {saving ? <BusyLabel>Saving outcome…</BusyLabel> : <><Save size={15} aria-hidden="true" /> Record outcome</>}
                        </button>
                    </div>
                    <p className="form-note">This result is operator-entered. If the linked Zoho record and writeback mapping are configured, the update is sent asynchronously; confirmed deal value is not independently verified revenue attribution.</p>
                </form>
            )}
        </section>
    );
}
