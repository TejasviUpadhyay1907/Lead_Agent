import React, { useState } from 'react';
import {
    Inbox, Flame, AlertTriangle, Clock, CalendarClock, ChevronRight,
    Sparkles, Zap, TrendingUp, UserCheck, Activity,
} from 'lucide-react';
import { PriorityBadge, RiskBadge } from '../components/Common/Badge';
import { StatCard } from '../components/Common/StatCard';
import { OutcomeReport } from '../components/Common/OutcomeReport';
import {
    PageHeader, SectionHeader, WorkflowStrip, EmptyState, ErrorState, Notice, BusyLabel, Avatar,
} from '../components/Common/UI';
import { humanize, isPendingResponse, isAwaitingDelivery, dateTime, timeOnly, relativeDue, followupBucket, safeError } from '../api/presentation';

const normalize = value => (value == null ? '' : String(value).toLowerCase());
const scoreOf = lead => (typeof lead.score === 'number' ? lead.score : null);
const recencyOf = lead => {
    const time = lead.created_at ? new Date(lead.created_at).getTime() : NaN;
    return Number.isFinite(time) ? time : 0;
};
const byScoreThenRecency = (a, b) => {
    const diff = (scoreOf(b) ?? -1) - (scoreOf(a) ?? -1);
    return diff !== 0 ? diff : recencyOf(b) - recencyOf(a);
};
const truncate = (text, max = 150) => {
    if (!text) return '';
    return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
};

/** Backend decides risk, priority and score. This only ranks the returned values. */
function attentionRank(lead) {
    if (normalize(lead.risk_status) === 'at_risk') return 0;
    if (isPendingResponse(lead)) return 1;
    if (isAwaitingDelivery(lead) || normalize(lead.lifecycle_status) === 'new') return 2;
    return 3;
}
const attentionReason = lead => {
    if (normalize(lead.risk_status) === 'at_risk') return 'At risk';
    if (isPendingResponse(lead)) return 'Draft awaiting approval';
    if (isAwaitingDelivery(lead)) return 'Approved · not delivered';
    return 'New inquiry';
};
const priorityTone = key => (['hot', 'warm', 'cold'].includes(key) ? key : 'neutral');

export function DashboardView({
    leads = [],
    followups,
    onSelectLead,
    onSeedData,
    demoMode = false,
    onNavigate,
    now,
    followupsError,
    onRetryFollowups,
}) {
    const [seeding, setSeeding] = useState(false);
    const [seedError, setSeedError] = useState(null);

    const total = leads.length;
    const hot = leads.filter(lead => normalize(lead.priority) === 'hot').length;
    const atRisk = leads.filter(lead => normalize(lead.risk_status) === 'at_risk').length;
    const pending = leads.filter(isPendingResponse).length;

    const leadById = new Map(leads.map(lead => [lead.lead_id, lead]));
    const followupsKnown = Array.isArray(followups) && !followupsError;

    // "Due" is only meaningful with a clock and a returned follow-up list.
    const dueCount = followupsKnown && now
        ? followups.filter(followup => ['due', 'overdue'].includes(followupBucket(followup, leadById.get(followup.lead_id), now))).length
        : null;

    // Priority distribution — categories come from returned priorities only.
    const scoredLeads = leads.filter(lead => lead.priority);
    const unscored = total - scoredLeads.length;
    const priorityCounts = new Map();
    scoredLeads.forEach(lead => {
        const key = normalize(lead.priority);
        priorityCounts.set(key, (priorityCounts.get(key) || 0) + 1);
    });
    const knownOrder = ['hot', 'warm', 'cold'];
    const categories = [...priorityCounts.keys()].sort((a, b) => {
        const rankA = knownOrder.indexOf(a);
        const rankB = knownOrder.indexOf(b);
        return (rankA === -1 ? 99 : rankA) - (rankB === -1 ? 99 : rankB) || a.localeCompare(b);
    });

    const attention = leads
        .filter(lead => attentionRank(lead) < 3)
        .sort((a, b) => attentionRank(a) - attentionRank(b) || byScoreThenRecency(a, b));
    const attentionShown = attention.slice(0, 6);
    const approvalQueue = leads.filter(isPendingResponse).sort(byScoreThenRecency);

    const upcoming = followupsKnown
        ? followups
            .map(followup => ({ followup, lead: leadById.get(followup.lead_id), bucket: followupBucket(followup, leadById.get(followup.lead_id), now) }))
            .filter(item => ['upcoming', 'due', 'overdue'].includes(item.bucket))
            .sort((a, b) => (new Date(a.followup.due_at).getTime() || 0) - (new Date(b.followup.due_at).getTime() || 0))
        : [];

    const arrivals = leads
        .filter(lead => lead.created_at && Number.isFinite(new Date(lead.created_at).getTime()))
        .sort((a, b) => recencyOf(b) - recencyOf(a))
        .slice(0, 5);

    const handleSeed = async () => {
        if (!onSeedData) return;
        setSeeding(true);
        setSeedError(null);
        try {
            await onSeedData();
        } catch (error) {
            setSeedError(safeError(error, 'The demo leads could not be loaded. Check the API and try again.'));
        } finally {
            setSeeding(false);
        }
    };

    return (
        <div className="dashboard-view">
            <PageHeader
                eyebrow="OPERATIONS OVERVIEW"
                title="Every lead. In view."
                description="Priority, risk and scores are shown exactly as the API returns them."
            >
                <button type="button" className="btn-secondary" onClick={() => onNavigate?.('inbox')}>
                    Open lead inbox <ChevronRight size={16} />
                </button>
            </PageHeader>

            <WorkflowStrip />

            <OutcomeReport />

            {seedError && <Notice tone="error">{seedError}</Notice>}

            {total === 0 ? (
                <EmptyState
                    icon={Sparkles}
                    title="No leads in the workspace yet"
                    description={demoMode ? "The API returned an empty lead list. Load the synthetic examples to explore the workspace, or create your own from the inbox." : "New inquiries will appear here when they arrive through your configured channels. Add a lead from the inbox to get started."}
                >
                    {demoMode && <button type="button" className="btn-primary" onClick={handleSeed} disabled={seeding}>
                        {seeding ? <BusyLabel>Loading demo leads…</BusyLabel> : <><Sparkles size={16} /> Load demo leads</>}
                    </button>}
                </EmptyState>
            ) : (
                <>
                    <section className="metric-strip" aria-label="Operational metrics">
                        <StatCard label="Leads loaded" value={total} hint="Current server pages" icon={Inbox} tone="neutral" onClick={() => onNavigate?.('inbox')} />
                        <StatCard label="Hot leads" value={hot} hint="In loaded lead pages" icon={Flame} tone="hot" />
                        <StatCard label="At risk" value={atRisk} hint="In loaded lead pages" icon={AlertTriangle} tone="risk" />
                        <StatCard label="Pending approval" value={pending} hint="Drafts awaiting a person" icon={Clock} tone="pending" />
                        <StatCard
                            label="Follow-ups due"
                            value={dueCount === null ? 'Unavailable' : dueCount}
                            hint={dueCount === null ? 'Clock or follow-up data unavailable' : 'Due or overdue now'}
                            icon={CalendarClock}
                            tone="due"
                            unavailable={dueCount === null}
                        />
                    </section>

                    <div className="dashboard-grid">
                        <div className="dashboard-main">
                            <section className="panel">
                                <SectionHeader
                                    icon={Zap}
                                    title="Attention queue"
                                    subtitle="At risk first, then drafts and new inquiries"
                                    layer="policy"
                                >
                                    <span className="badge-sub">{attention.length} leads</span>
                                </SectionHeader>

                                {attentionShown.length === 0 ? (
                                    <p className="panel-note">Nothing needs attention right now.</p>
                                ) : (
                                    <ul className="attention-list">
                                        {attentionShown.map(lead => {
                                            const rank = attentionRank(lead);
                                            const state = rank === 0 ? 'is-at-risk' : rank === 1 ? 'is-pending' : 'is-new';
                                            return (
                                                <li key={lead.lead_id} className={`attention-item ${state}`}>
                                                    <Avatar name={lead.customer_name} />
                                                    <div className="attention-body">
                                                        <div className="attention-head">
                                                            <span className="attention-name">{lead.customer_name || 'Unnamed lead'}</span>
                                                            <PriorityBadge priority={lead.priority} />
                                                            <RiskBadge risk={lead.risk_status} />
                                                        </div>
                                                        <p className="attention-message">
                                                            {lead.raw_message ? truncate(lead.raw_message) : 'No message returned.'}
                                                        </p>
                                                        <div className="attention-meta">
                                                            <span className={`attention-reason ${state}`}>{attentionReason(lead)}</span>
                                                            {lead.intent && <span className="attention-intent">{humanize(lead.intent)}</span>}
                                                        </div>
                                                    </div>
                                                    <div className="attention-side">
                                                        {scoreOf(lead) !== null
                                                            ? <span className="attention-score">{lead.score}<small>/100</small></span>
                                                            : <span className="score-pending">Unscored</span>}
                                                        <button type="button" className="btn-secondary btn-sm" onClick={() => onSelectLead?.(lead.lead_id)}>
                                                            View <ChevronRight size={14} />
                                                        </button>
                                                    </div>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                )}

                                <div className="panel-footer">
                                    <button type="button" className="btn-secondary btn-sm" onClick={() => onNavigate?.('inbox')}>
                                        Open inbox <ChevronRight size={14} />
                                    </button>
                                </div>
                            </section>
                        </div>

                        <aside className="dashboard-side">
                            <section className="panel">
                                <SectionHeader
                                    icon={TrendingUp}
                                    title="Priority distribution"
                                    subtitle="Segments reflect returned priorities"
                                    layer="policy"
                                />
                                {scoredLeads.length === 0 ? (
                                    <p className="panel-note">No scored leads have been returned yet.</p>
                                ) : (
                                    <>
                                        <div
                                            className="distribution-bar"
                                            role="img"
                                            aria-label={categories.map(key => `${humanize(key)}: ${priorityCounts.get(key)}`).join(', ')}
                                        >
                                            {categories.map(key => (
                                                <span
                                                    key={key}
                                                    className={`distribution-segment seg-${priorityTone(key)}`}
                                                    style={{ width: `${(priorityCounts.get(key) / scoredLeads.length) * 100}%` }}
                                                />
                                            ))}
                                        </div>
                                        <ul className="distribution-legend">
                                            {categories.map(key => (
                                                <li key={key} className="legend-item">
                                                    <span className={`legend-swatch seg-${priorityTone(key)}`} aria-hidden="true" />
                                                    <span className="legend-label">{humanize(key)}</span>
                                                    <span className="legend-count">{priorityCounts.get(key)}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </>
                                )}
                                {unscored > 0 && (
                                    <p className="distribution-note">
                                        {unscored} {unscored === 1 ? 'lead is' : 'leads are'} unscored and excluded from this distribution.
                                    </p>
                                )}
                            </section>

                            <section className="panel">
                                <SectionHeader
                                    icon={UserCheck}
                                    title="Human approval"
                                    subtitle="Approval and WhatsApp delivery are separate audited actions"
                                    layer="human"
                                >
                                    <span className="badge-sub">{pending} pending approval · {leads.filter(isAwaitingDelivery).length} approved, not delivered</span>
                                </SectionHeader>

                                {approvalQueue.length === 0 ? (
                                    <p className="panel-note">No drafts are waiting for approval.</p>
                                ) : (
                                    <ul className="approval-list">
                                        {approvalQueue.slice(0, 4).map(lead => (
                                            <li key={lead.lead_id} className="approval-item">
                                                <button type="button" className="approval-link" onClick={() => onSelectLead?.(lead.lead_id)}>
                                                    <span className="approval-name">{lead.customer_name || 'Unnamed lead'}</span>
                                                    <span className="approval-meta">
                                                        {humanize(lead.response_status)} · {lead.priority ? humanize(lead.priority) : 'Unscored'}
                                                    </span>
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}

                                <div className="panel-footer">
                                    <button type="button" className="btn-secondary btn-sm" onClick={() => onNavigate?.('inbox')}>
                                        Review in inbox <ChevronRight size={14} />
                                    </button>
                                </div>
                            </section>

                            <section className="panel">
                                <SectionHeader
                                    icon={CalendarClock}
                                    title="Upcoming follow-ups"
                                    subtitle="Scheduled by the policy engine"
                                    layer="policy"
                                />
                                {followupsError ? (
                                    <ErrorState
                                        title="Follow-ups unavailable"
                                        description="The follow-up list did not load, so nothing is shown here."
                                        onRetry={onRetryFollowups}
                                    />
                                ) : upcoming.length === 0 ? (
                                    <p className="panel-note">No follow-ups are scheduled.</p>
                                ) : (
                                    <ul className="followup-mini-list">
                                        {upcoming.slice(0, 5).map(({ followup, lead }) => (
                                            <li key={followup.followup_id} className="followup-mini">
                                                <div className="followup-mini-body">
                                                    <span className="followup-mini-name">{lead?.customer_name || 'Unnamed lead'}</span>
                                                    <span className="followup-mini-action">
                                                        {followup.action ? humanize(followup.action) : 'Follow-up'}
                                                    </span>
                                                </div>
                                                <div className="followup-mini-time">
                                                    <span>{relativeDue(followup.due_at, now)}</span>
                                                    <small>{timeOnly(followup.due_at)}</small>
                                                </div>
                                                {lead && (
                                                    <button
                                                        type="button"
                                                        className="icon-button"
                                                        aria-label={`Open ${lead.customer_name || 'lead'}`}
                                                        onClick={() => onSelectLead?.(followup.lead_id)}
                                                    >
                                                        <ChevronRight size={16} />
                                                    </button>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                                <div className="panel-footer">
                                    <button type="button" className="btn-secondary btn-sm" onClick={() => onNavigate?.('followups')}>
                                        Open follow-ups <ChevronRight size={14} />
                                    </button>
                                </div>
                            </section>

                            <section className="panel">
                                <SectionHeader
                                    icon={Activity}
                                    title="Recent arrivals"
                                    subtitle="Newest inquiries by returned timestamp"
                                />
                                {arrivals.length === 0 ? (
                                    <p className="panel-note">No arrival timestamps were returned.</p>
                                ) : (
                                    <ul className="arrivals-list">
                                        {arrivals.map(lead => (
                                            <li key={lead.lead_id} className="arrival-item">
                                                <Avatar name={lead.customer_name} />
                                                <div className="arrival-body">
                                                    <span className="arrival-name">{lead.customer_name || 'Unnamed lead'}</span>
                                                    <span className="arrival-meta">
                                                        {lead.source ? humanize(lead.source) : 'Channel not returned'} · {dateTime(lead.created_at)}
                                                    </span>
                                                </div>
                                                <button
                                                    type="button"
                                                    className="icon-button"
                                                    aria-label={`Open ${lead.customer_name || 'lead'}`}
                                                    onClick={() => onSelectLead?.(lead.lead_id)}
                                                >
                                                    <ChevronRight size={16} />
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                                <div className="panel-footer">
                                    <button type="button" className="btn-secondary btn-sm" onClick={() => onNavigate?.('activity')}>
                                        View activity <ChevronRight size={14} />
                                    </button>
                                </div>
                            </section>
                        </aside>
                    </div>
                </>
            )}
        </div>
    );
}
