import React, { useState, useEffect, useRef } from 'react';
import { ArrowLeft, ArrowUpRight, Download, Mail, Phone, MessageSquare, History, LockKeyhole, LifeBuoy, BrainCircuit, UserRound, CheckCircle2 } from 'lucide-react';
import { api } from '../api/client';
import { dateTime, humanize, isBlocked, isOptedOut, isConfirmedSent, lifecyclePresentationStatus, safeError } from '../api/presentation';
import { LifecycleBadge } from '../components/Common/Badge';
import { SectionHeader, WorkflowStrip, Skeleton, ErrorState, Avatar, Notice, Modal, BusyLabel } from '../components/Common/UI';
import { AIAnalysisPanel, PolicyDecisionPanel, ResponseComposer } from '../components/Common/LeadPanels';
import { ActivityTimeline } from '../components/Common/ActivityTimeline';
import { OutcomeTracker } from '../components/Common/OutcomeTracker';
import { WhatsAppConsentPanel } from '../components/Common/WhatsAppConsentPanel';

export function LeadDetailView({ leadId, onBack, onRefreshLeads, revision, config, clock, followups, followupsError }) {
    const [lead, setLead] = useState(null);
    const [audit, setAudit] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [auditError, setAuditError] = useState(false);
    const [auditCursor, setAuditCursor] = useState(null);
    const [auditLoadingMore, setAuditLoadingMore] = useState(false);
    const [busy, setBusy] = useState(null);
    const [exportBusy, setExportBusy] = useState(false);
    const [notice, setNotice] = useState(null);
    const [text, setText] = useState('');
    const [editing, setEditing] = useState(false);
    const [reviewed, setReviewed] = useState(false);
    const [modal, setModal] = useState(null);
    const [retry, setRetry] = useState(0);
    const [showAllEvents, setShowAllEvents] = useState(false);
    const dirtyRef = useRef(false);
    const actionRef = useRef(false);
    const loadVersion = useRef(0);
    useEffect(() => {
        const version = ++loadVersion.current;
        setError(null);
        Promise.allSettled([api.getLead(leadId), api.getAudit(leadId)]).then(([record, events]) => {
            if (version !== loadVersion.current) return;
            if (record.status === 'fulfilled' && record.value?.lead_id) {
                setLead(record.value);
                if (!dirtyRef.current || isBlocked(record.value) || isConfirmedSent(record.value)) {
                    setText(record.value.response_draft || '');
                    dirtyRef.current = false;
                    setReviewed(false);
                }
            } else setError('The lead record could not be loaded. Refresh to see its current state.');
            if (events.status === 'fulfilled' && Array.isArray(events.value?.items)) { setAudit(events.value.items); setAuditCursor(events.value.nextCursor); setAuditError(false); }
            else { setAuditError(true); setAudit([]); setAuditCursor(null); }
            setLoading(false);
        });
        return () => { loadVersion.current++; };
    }, [leadId, revision, retry]);
    const perform = async action => {
        if (actionRef.current || !lead || isBlocked(lead)) return;
        if (action === 'approve' && (!reviewed || !text.trim())) return;
        actionRef.current = true; setBusy(action); setNotice(null);
        try {
            let result;
            if (action === 'analyze') result = await api.analyzeLead(leadId);
            else if (action === 'rescue') result = await api.rescueLead(leadId);
            else result = await api.respondToLead(leadId, action, action === 'reject' ? undefined : text, action === 'approve' && reviewed);
            dirtyRef.current = false; setEditing(false); setReviewed(false); setModal(null);
            if (result?.lead_id) { setLead(result); setText(result.response_draft || ''); }
            setNotice({ tone: action === 'rescue' && !result.rescued ? 'info' : 'success', text: action === 'rescue' ? result.rescued ? `Priority follow-up scheduled${result.due_at ? ` for ${dateTime(result.due_at)}` : ''}. Human review is still required; nothing was sent.` : `Rescue was not scheduled.${result.reason ? ` ${result.reason}` : ' The policy engine did not permit this action.'}` : action === 'analyze' ? 'Analysis returned. Review the extracted context and policy decision below.' : action === 'approve' ? 'Approval recorded. No message was sent; delivery is not configured.' : action === 'edit' ? 'Your edited draft was saved. Review it before approving.' : 'Response rejected. No message was sent.' });
            await onRefreshLeads();
            setRetry(value => value + 1);
        } catch (actionError) { setModal(null); setNotice({ tone: 'error', text: safeError(actionError, 'This action could not be confirmed. Refresh the lead and audit before retrying to avoid a duplicate action.') }); }
        finally { setBusy(null); actionRef.current = false; }
    };
    if (loading) return <Skeleton rows={5} label="Loading lead context and policy…" />;
    if (error || !lead) return <div className="view-stack"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to leads</button><ErrorState title="Unable to open this lead" description={error} onRetry={() => setRetry(value => value + 1)} /></div>;
    const optedOut = isOptedOut(lead);
    const leadFollowups = followups.filter(item => item.lead_id === leadId);
    const nextFollowup = leadFollowups.filter(item => ['scheduled', 'overdue'].includes(item.status)).sort((a, b) => new Date(a.due_at) - new Date(b.due_at))[0];
    const events = [...audit].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    const loadMoreAudit = async () => {
        if (!auditCursor || auditLoadingMore) return;
        setAuditLoadingMore(true);
        try {
            const page = await api.getAudit(leadId, auditCursor);
            setAudit(current => [...current, ...page.items]);
            setAuditCursor(page.nextCursor);
        } catch (loadError) {
            setNotice({ tone: 'error', text: safeError(loadError, 'Older audit events could not be loaded.') });
        } finally { setAuditLoadingMore(false); }
    };
    const exportRecord = async () => {
        if (exportBusy) return;
        setExportBusy(true);
        setNotice(null);
        try {
            await api.exportLeadData(leadId);
            setNotice({ tone: 'success', text: 'Record export downloaded and recorded in the audit history.' });
            setRetry(value => value + 1);
        } catch (exportError) {
            setNotice({ tone: 'error', text: exportError?.status === 403 ? 'Only a company admin can export customer records.' : safeError(exportError, 'This record could not be exported. Refresh and try again.') });
        } finally { setExportBusy(false); }
    };
    const dirty = text !== (lead.response_draft || '');
    return <div className="view-stack lead-detail">
        <div className="detail-navigation"><button className="back-link" onClick={onBack}><ArrowLeft size={16} /> All leads</button><span className="lead-reference">RECORD / {lead.lead_id.slice(0, 8)}</span></div>
        <div className="customer-header"><div className="customer-identity"><Avatar name={lead.customer_name} large /><div><div className="customer-title"><h1>{lead.customer_name || 'Unnamed lead'}</h1><LifecycleBadge status={lifecyclePresentationStatus(lead)} /></div><p><MessageSquare size={14} /> {humanize(lead.source)} <span className="meta-dot">·</span> Received {dateTime(lead.created_at)}</p></div></div><div className="header-actions"><button className="btn-secondary" disabled={exportBusy} onClick={exportRecord}>{exportBusy ? <BusyLabel>Preparing export…</BusyLabel> : <><Download size={15} /> Export record <span className="badge-sub">Admin</span></>}</button>{!lead.intent && !isBlocked(lead) && <button className="btn-ai" disabled={!!busy} onClick={() => perform('analyze')}>{busy === 'analyze' ? <BusyLabel>Analyzing context…</BusyLabel> : <><BrainCircuit size={16} /> Analyze lead</>}</button>}<a className="btn-secondary" href="#response-workspace" onClick={event => { event.preventDefault(); document.getElementById('response-workspace')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}>Response workspace <ArrowUpRight size={15} /></a></div></div>
        {lead.privacy_hold && <Notice tone="warning">This lead record contains a privacy request and remains outside sales analysis, response actions, and rescue. Record any separate new sales inquiry as a new lead. Erasure requests also suppress future outreach to the matched contact.</Notice>}
        {optedOut && <div className="safety-banner" role="status"><LockKeyhole size={26} /><div><span className="eyebrow">OPT-OUT SAFEGUARD TRIGGERED</span><h2>This customer's choice is protected.</h2><p>Customer requested opt-out. Sending, rescue and follow-up outreach are blocked. There is no override.</p></div><span className="badge-sub opt-out-label">Outreach blocked</span></div>}
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
        <WorkflowStrip compact />
        <div className="detail-columns"><div className="detail-main"><section className="panel source-panel"><SectionHeader icon={MessageSquare} title="The original message" subtitle="Customer-provided source evidence"><span className="badge-sub">{humanize(lead.source)}</span></SectionHeader><blockquote>{lead.raw_message || 'No message provided.'}</blockquote><div className="customer-contact">{lead.customer_email && <span><Mail size={14} /> {lead.customer_email}</span>}{lead.customer_phone && <span><Phone size={14} /> {lead.customer_phone}</span>}{lead.customer_stage && <span><UserRound size={14} /> {humanize(lead.customer_stage)} customer</span>}{!lead.customer_email && !lead.customer_phone && <span>No contact details supplied</span>}</div></section>
            <AIAnalysisPanel lead={lead} busy={!!busy} onAnalyze={() => perform('analyze')} />
            <ResponseComposer lead={lead} text={text} editing={editing} dirty={dirty} reviewed={reviewed} busy={!!busy} onReview={setReviewed} onChange={value => { setText(value); dirtyRef.current = true; setReviewed(false); }} onEdit={() => { setEditing(true); setReviewed(false); }} onCancel={() => { setText(lead.response_draft || ''); dirtyRef.current = false; setEditing(false); setReviewed(false); }} onSave={() => perform('edit')} onApprove={() => perform('approve')} onReject={() => setModal('reject')} />
            <WhatsAppConsentPanel lead={lead} onSaved={updated => { setLead(updated); setNotice({ tone: 'success', text: 'Verified WhatsApp consent evidence recorded. No message was sent.' }); setRetry(value => value + 1); onRefreshLeads(); }} />
            <OutcomeTracker lead={lead} onSaved={updated => { setLead(updated); setRetry(value => value + 1); onRefreshLeads(); }} />
        </div><aside className="detail-side"><PolicyDecisionPanel lead={lead} config={config} clock={clock} nextFollowup={nextFollowup} followupsError={followupsError} busy={!!busy} onRescue={() => setModal('rescue')} /><div className="trust-footnote"><ShieldIcon /><p><strong>Policy is authoritative.</strong> Scores and risk come from the server. AI cannot bypass your approval or customer consent.</p></div></aside></div>
        <section className="panel lead-audit"><SectionHeader icon={History} title="A clear record of every action" subtitle="Actual events returned by the audit API"><span className="badge-sub">{auditError ? 'Unavailable' : `${audit.length}${auditCursor ? '+' : ''} events loaded`}</span></SectionHeader>{auditError ? <ErrorState title="Audit history is unavailable" onRetry={() => setRetry(value => value + 1)} /> : <><ActivityTimeline events={showAllEvents ? events : events.slice(0, 5)} />{events.length > 5 && <button className="btn-text" onClick={() => setShowAllEvents(value => !value)}>{showAllEvents ? 'Show recent events' : `Show all ${events.length} loaded events`}</button>}{auditCursor && <button type="button" className="btn-secondary" disabled={auditLoadingMore} onClick={loadMoreAudit}>{auditLoadingMore ? 'Loading…' : 'Load older events'}</button>}</>}</section>
        {modal && <Modal title={modal === 'rescue' ? 'Review rescue action' : 'Reject this response?'} description={modal === 'rescue' ? 'The policy engine makes the final eligibility decision.' : 'The draft will be rejected. No external message will be sent.'} onClose={() => setModal(null)} busy={!!busy}><div className="view-stack">{modal === 'rescue' && <><div className="rescue-steps"><span>At-risk lead</span><span>Policy eligibility check</span><span>Priority follow-up</span><span>Human review</span></div><p>The server will schedule a rescue follow-up if this lead is eligible. This action does not send a message.</p></>}<div className="form-actions"><button className="btn-secondary" disabled={!!busy} onClick={() => setModal(null)}>Cancel</button><button className={modal === 'rescue' ? 'btn-rescue' : 'btn-primary'} disabled={!!busy} onClick={() => perform(modal)}>{busy ? <BusyLabel>Processing…</BusyLabel> : modal === 'rescue' ? <><LifeBuoy size={16} /> Rescue lead</> : 'Reject response'}</button></div></div></Modal>}
    </div>;
}
function ShieldIcon() { return <CheckCircle2 size={19} />; }
