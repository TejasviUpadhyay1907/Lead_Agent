import React from 'react';
import { BrainCircuit, ShieldCheck, UserCheck, Send, Pencil, CheckCircle2, LockKeyhole, LifeBuoy, Clock3, ArrowRight, X } from 'lucide-react';
import { SectionHeader, EmptyState, BusyLabel } from './UI';
import { PriorityBadge, RiskBadge, LifecycleBadge } from './Badge';
import { dateTime, humanize, isBlocked, isOptedOut, isConfirmedSent, isAwaitingDelivery, lifecyclePresentationStatus, relativeDue } from '../../api/presentation';

export function AIAnalysisPanel({ lead, onAnalyze, busy }) {
    const optedOut = isOptedOut(lead);
    return <section className="panel analysis-panel"><SectionHeader icon={BrainCircuit} title="AI understanding" subtitle="Extracted context, not business policy" layer="ai"><span className="layer-label ai">01 / UNDERSTAND</span></SectionHeader>
        {optedOut ? <div className="quiet-message"><LockKeyhole size={20} /><div><strong>Outreach analysis is not actionable</strong><p>The customer's opt-out takes precedence over any prior analysis or draft.</p></div></div> : !lead.intent ? <EmptyState icon={BrainCircuit} title="Ready to understand this lead" description="Analyze the original message to extract intent and context, and prepare a response for your review."><button className="btn-ai" disabled={busy || isBlocked(lead)} onClick={onAnalyze}>{busy ? <BusyLabel>Analyzing lead context…</BusyLabel> : <><BrainCircuit size={16} /> Analyze lead</>}</button></EmptyState> : <>
            <dl className="ai-facts">{[['Intent', humanize(lead.intent)], ['Urgency', humanize(lead.urgency)], ['Product', lead.product], ['Quantity', lead.quantity], ['Location', lead.location], ['Customer stage', humanize(lead.customer_stage)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? 'Not specified'}</dd></div>)}</dl>
            <div className="analysis-summary"><span className="eyebrow">CONTEXT SUMMARY</span><p>{lead.ai_summary || 'No summary returned.'}</p></div>
            {lead.key_entities?.length > 0 && <div className="entity-list">{lead.key_entities.map((entity, index) => <span key={index} className="entity">{entity}</span>)}</div>}
            {lead.recommended_action && <div className="recommendation"><BrainCircuit size={16} /><div><strong>Suggested next step</strong><p>{lead.recommended_action}</p><small>AI recommendation · Review before acting</small></div></div>}
        </>}
    </section>;
}

export function PolicyDecisionPanel({ lead, config, clock, nextFollowup, followupsError, onRescue, busy }) {
    const optedOut = isOptedOut(lead);
    const sent = isConfirmedSent(lead);
    const atRisk = lead.risk_status === 'at_risk';
    const rescueAvailable = atRisk && !isBlocked(lead) && !sent;
    const elapsed = clock?.effective_now && lead.created_at ? Math.floor((new Date(clock.effective_now) - new Date(lead.created_at)) / 60000) : null;
    return <section className="panel policy-panel"><SectionHeader icon={ShieldCheck} title="System decision" subtitle="Deterministic policy · independent of AI" layer="policy"><span className="layer-label policy">02 / DECIDE</span></SectionHeader>
        {optedOut ? <div className="safety-policy"><LockKeyhole size={26} /><h3>Consent comes first.</h3><p>Scoring and outreach are not actionable for this lead. Any previously stored priority is not shown as a current decision.</p><span className="badge-sub opt-out-label">Policy blocked</span></div> : <>
            <div className="score-summary"><div><span className="eyebrow">POLICY SCORE</span><div className="score-number">{lead.score ?? '—'}<span>/ 100</span></div></div><div className="score-priority"><PriorityBadge priority={lead.priority} /><small>{lead.score == null ? 'Awaiting evaluation' : 'Returned by policy engine'}</small></div></div>
            <div className="score-track" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, lead.score || 0))}%` }} /></div>
            <dl className="policy-facts"><div><dt>Response target</dt><dd>{config?.response_target_minutes != null ? `${config.response_target_minutes} min` : 'Unavailable'}</dd></div><div><dt>Recorded SLA deadline</dt><dd>{lead.at_risk_at ? dateTime(lead.at_risk_at) : 'Not returned'}</dd></div><div><dt>Server time</dt><dd>{clock?.effective_now ? dateTime(clock.effective_now) : 'Unavailable'}</dd></div><div><dt>Elapsed since arrival</dt><dd>{elapsed == null || !Number.isFinite(elapsed) ? 'Unavailable' : elapsed < 0 ? 'Before arrival on server clock' : `${elapsed} min`}</dd></div><div><dt>Risk state</dt><dd><RiskBadge risk={lead.risk_status} /></dd></div><div><dt>Lifecycle</dt><dd><LifecycleBadge status={lifecyclePresentationStatus(lead)} /></dd></div><div><dt>Next follow-up</dt><dd>{followupsError ? 'Unavailable' : nextFollowup ? dateTime(nextFollowup.due_at) : 'None scheduled'}</dd></div></dl>
            {atRisk && !sent && !isBlocked(lead) && <div className="risk-callout"><div><Clock3 size={17} /><strong>Response needs attention</strong></div><p>{lead.at_risk_at && clock?.effective_now ? relativeDue(lead.at_risk_at, clock.effective_now) : 'The backend has flagged this lead as at risk.'}</p><button className="btn-rescue" disabled={!rescueAvailable || busy} onClick={onRescue}><LifeBuoy size={16} /> Review rescue <ArrowRight size={14} /></button><small>Policy checks eligibility. No automatic outreach.</small></div>}
            {sent && <p className="form-note"><CheckCircle2 size={14} /> Provider-confirmed message delivery recorded. This response satisfies the SLA.</p>}
            {Object.keys(lead.score_breakdown || {}).length > 0 && <details className="score-breakdown"><summary>Inspect score breakdown</summary><dl>{Object.entries(lead.score_breakdown).map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{value} pts</dd></div>)}</dl><p>All points are supplied by the backend. No score is calculated in the browser.</p></details>}
        </>}
    </section>;
}

export function ResponseComposer({ lead, text, onChange, editing, onEdit, onCancel, onSave, onApprove, onReject, busy, reviewed, onReview, dirty }) {
    const blocked = isBlocked(lead);
    const sent = isConfirmedSent(lead);
    const approved = isAwaitingDelivery(lead);
    const needsApproval = ['draft', 'edited'].includes(lead.response_status);
    const canRespond = needsApproval || approved;
    return <section className="panel response-panel" id="response-workspace"><SectionHeader icon={UserCheck} title="Response workspace" subtitle="AI prepares the draft. You control what happens next." layer="human"><span className="layer-label human">03 / APPROVE</span></SectionHeader>
        {blocked ? <div className="blocked-composer"><LockKeyhole size={22} /><strong>{isOptedOut(lead) ? 'Outreach blocked by opt-out safeguard' : 'This lead is resolved'}</strong><p>No send, rescue or follow-up action is available.</p><button className="btn-primary" disabled><LockKeyhole size={15} /> Approval unavailable</button></div> : !lead.response_draft ? <EmptyState icon={Send} title="A thoughtful response starts with context" description="Run lead analysis to generate a draft for review. Approval does not send a message." /> : <>
            {sent && <div className="approval-success" role="status"><CheckCircle2 size={25} /><div><strong>Message delivery confirmed</strong><p>The provider confirmed delivery. Current lifecycle: {humanize(lead.lifecycle_status)}.</p></div></div>}
            {approved && <div className="approval-success" role="status"><CheckCircle2 size={25} /><div><strong>{lead.response_status === 'simulated_sent' ? 'Legacy simulated status · delivery unconfirmed' : 'Approval recorded · not delivered'}</strong><p>No delivery provider is configured. This lead remains unanswered until delivery is confirmed.</p></div></div>}
            <div className="draft-meta"><span><BrainCircuit size={14} /> AI RESPONSE DRAFT</span><span className={`badge-sub ${sent ? 'success-label' : ''}`}>{humanize(lead.response_status)}{dirty ? ' · Unsaved changes' : ''}</span></div>
            <label className="sr-only" htmlFor="response-draft">Response draft</label><textarea id="response-draft" className={`draft-editor ${editing ? 'editing' : ''}`} rows={5} value={text} readOnly={!editing || busy || sent} onChange={event => onChange(event.target.value)} />
            <div className="draft-disclaimer"><LockKeyhole size={13} /><span>Approval records review only. No WhatsApp or email message is delivered.</span></div>
            {!sent && canRespond && <>{needsApproval && <label className="review-check"><input type="checkbox" checked={reviewed} onChange={event => onReview(event.target.checked)} disabled={busy} /><span>I reviewed this draft. Record my approval; do not send it.</span></label>}<div className="composer-actions"><div className="button-group">{editing ? <><button className="btn-secondary" onClick={onCancel} disabled={busy}>Cancel edit</button><button className="btn-secondary" disabled={busy || !dirty || !text.trim()} onClick={onSave}>Save draft</button></> : <button className="btn-secondary" onClick={onEdit} disabled={busy}><Pencil size={14} /> Edit draft</button>}<button className="btn-text reject" disabled={busy} onClick={onReject}><X size={14} /> Reject</button></div>{needsApproval && <button className="btn-primary" disabled={busy || !reviewed || !text.trim()} onClick={onApprove}>{busy ? <BusyLabel>Processing…</BusyLabel> : <><UserCheck size={16} /> Record approval</>}</button>}</div></>}
            {!sent && !canRespond && <p className="form-note">This response is {humanize(lead.response_status).toLowerCase()}. Sending is unavailable in the current state.</p>}
        </>}
    </section>;
}
