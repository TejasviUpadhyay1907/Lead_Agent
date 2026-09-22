import React, { useMemo, useState } from 'react';
import { CalendarClock, Check, ChevronRight, AlertTriangle, RefreshCw, Inbox } from 'lucide-react';
import { PriorityBadge } from '../components/Common/Badge';
import { PageHeader, EmptyState, ErrorState, Notice, Skeleton, BusyLabel } from '../components/Common/UI';
import { api } from '../api/client';
import { followupBucket, relativeDue, dateTime, humanize, isBlocked, safeError } from '../api/presentation';

/** Tabs mirror the API-owned follow-up states. Nothing is inferred from names or ordering. */
const TABS = [
    { id: 'all', label: 'All' },
    { id: 'due', label: 'Due' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'upcoming', label: 'Upcoming' },
    { id: 'completed', label: 'Completed' },
    { id: 'stopped', label: 'Stopped' },
];

const TAB_BUCKETS = {
    due: ['due', 'overdue'],
    overdue: ['overdue'],
    upcoming: ['upcoming'],
    completed: ['completed'],
    stopped: ['stopped'],
};

const EMPTY_COPY = {
    all: 'No follow-ups are available yet. Scheduled outreach appears here once the policy engine creates it.',
    due: 'No follow-ups are due or overdue right now.',
    overdue: 'No follow-ups are currently overdue.',
    upcoming: 'No follow-ups are scheduled for later.',
    completed: 'No follow-ups have been completed yet.',
    stopped: 'No follow-ups are stopped or cancelled.',
};

export function FollowupsView({ followups, leads, onSelectLead, onRefreshLeads, now, error, onRetry, hasMore = false, loadingMore = false, onLoadMore, loadMoreError }) {
    const [activeTab, setActiveTab] = useState('all');
    const [pendingId, setPendingId] = useState(null);
    const [refreshing, setRefreshing] = useState(false);
    const [notice, setNotice] = useState(null);
    const [actionError, setActionError] = useState(null);

    const ready = Array.isArray(followups) && Array.isArray(leads);

    /** One pass over the data: resolve the lead (if known) and bucket the follow-up. */
    const rows = useMemo(() => {
        if (!ready) return [];
        const leadsById = new Map(leads.map(lead => [lead.lead_id, lead]));
        return followups.map(followup => {
            const lead = leadsById.get(followup.lead_id) || null;
            return {
                followup,
                lead,
                leadKnown: Boolean(lead),
                bucket: followupBucket(followup, lead, now),
            };
        });
    }, [followups, leads, now, ready]);

    const counts = useMemo(() => {
        const totals = { all: rows.length, due: 0, overdue: 0, upcoming: 0, completed: 0, stopped: 0 };
        rows.forEach(({ bucket }) => {
            if (bucket === 'overdue') {
                totals.overdue += 1;
                totals.due += 1;
            } else if (bucket === 'due') {
                totals.due += 1;
            } else if (Object.prototype.hasOwnProperty.call(totals, bucket)) {
                totals[bucket] += 1;
            }
        });
        return totals;
    }, [rows]);

    const visibleRows = useMemo(() => {
        if (activeTab === 'all') return rows;
        const allowed = TAB_BUCKETS[activeTab] || [];
        return rows.filter(row => allowed.includes(row.bucket));
    }, [rows, activeTab]);

    const headerDescription = 'Scheduled outreach created by the policy engine. Only scheduled or overdue follow-ups on known, unblocked leads can be actioned.';

    const handleRefresh = async () => {
        if (!onRefreshLeads) return;
        setRefreshing(true);
        setActionError(null);
        setNotice(null);
        try {
            await onRefreshLeads();
            setNotice({ tone: 'success', text: 'Follow-ups refreshed from the server.' });
        } catch (refreshError) {
            setActionError(safeError(refreshError, 'The follow-up list could not be refreshed.'));
        } finally {
            setRefreshing(false);
        }
    };

    const handleComplete = async (followupId, leadName) => {
        setPendingId(followupId);
        setActionError(null);
        setNotice(null);
        try {
            await api.updateFollowup(followupId, 'completed', 'Marked completed from the Follow-ups view');
            if (onRefreshLeads) await onRefreshLeads();
            setNotice({ tone: 'success', text: `Follow-up${leadName ? ` for ${leadName}` : ''} marked completed.` });
        } catch (updateError) {
            setActionError(safeError(updateError, 'The follow-up could not be updated. Refresh the list and try again.'));
        } finally {
            setPendingId(null);
        }
    };

    if (!ready) {
        return (
            <div className="view-stack">
                <PageHeader eyebrow="Operations" title="Follow-ups" description={headerDescription} />
                <Skeleton rows={5} label="Loading follow-ups…" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="view-stack">
                <PageHeader eyebrow="Operations" title="Follow-ups" description={headerDescription} />
                <ErrorState
                    title="Unable to load follow-ups"
                    description={typeof error === 'string' ? error : safeError(error)}
                    onRetry={onRetry}
                />
            </div>
        );
    }

    return (
        <div className="view-stack">
            <PageHeader eyebrow="Operations" title="Follow-ups" description={headerDescription}>
                <span className="badge-sub">{counts.due} due or overdue</span>
                {onRefreshLeads && (
                    <button type="button" className="btn-secondary" onClick={handleRefresh} disabled={refreshing}>
                        {refreshing ? <BusyLabel>Refreshing…</BusyLabel> : <><RefreshCw size={15} aria-hidden="true" /> Refresh</>}
                    </button>
                )}
                {hasMore && <button type="button" className="btn-secondary" onClick={onLoadMore} disabled={loadingMore}>{loadingMore ? <BusyLabel>Loading…</BusyLabel> : 'Load next 50'}</button>}
            </PageHeader>

            {loadMoreError && <Notice tone="error">{loadMoreError}</Notice>}

            <div className="tabs" role="tablist" aria-label="Filter follow-ups by state">
                {TABS.map(tab => (
                    <button
                        key={tab.id}
                        type="button"
                        role="tab"
                        id={`followups-tab-${tab.id}`}
                        aria-selected={activeTab === tab.id}
                        aria-controls="followups-panel"
                        className={`tab ${activeTab === tab.id ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                    >
                        {tab.label}
                        <span className="tab-count">{counts[tab.id]}</span>
                    </button>
                ))}
            </div>

            {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
            {actionError && <Notice tone="error">{actionError}</Notice>}

            <section className="panel" id="followups-panel" role="tabpanel" aria-labelledby={`followups-tab-${activeTab}`}>
                {visibleRows.length === 0 ? (
                    <EmptyState icon={Inbox} title="Nothing in this view" description={EMPTY_COPY[activeTab]} />
                ) : (
                    <ul className="followup-list">
                        {visibleRows.map(({ followup, lead, leadKnown, bucket }) => {
                            const isOverdue = bucket === 'overdue';
                            const isActionable = leadKnown && !isBlocked(lead) && (bucket === 'due' || bucket === 'overdue');
                            const canOpen = Boolean(onSelectLead && followup.lead_id);
                            const reason = !leadKnown
                                ? 'Lead record not loaded — action unavailable'
                                : isBlocked(lead)
                                    ? `Lead is ${humanize(lead.lifecycle_status).toLowerCase()} — outreach blocked`
                                    : null;

                            return (
                                <li className="followup-card" key={followup.followup_id}>
                                    <button
                                        type="button"
                                        className="followup-open"
                                        onClick={() => canOpen && onSelectLead(followup.lead_id)}
                                        disabled={!canOpen}
                                    >
                                        <span className="followup-icon" aria-hidden="true"><CalendarClock size={18} /></span>

                                        <span className="followup-main">
                                            <span className="followup-title">
                                                <span className="followup-name">{leadKnown ? (lead.customer_name || 'Unnamed lead') : 'Unknown lead'}</span>
                                                {lead?.priority && <PriorityBadge priority={lead.priority} />}
                                                <span className="badge-sub">{humanize(followup.status)}</span>
                                                {isOverdue && (
                                                    <span className="badge badge-hot"><AlertTriangle size={12} aria-hidden="true" /> Overdue</span>
                                                )}
                                            </span>
                                            <span className="followup-action">{humanize(followup.action)}</span>
                                            {followup.notes && <span className="followup-notes">{followup.notes}</span>}
                                        </span>

                                        <span className="followup-side">
                                            <span className="due-label">Due</span>
                                            <span className={`due-value ${isOverdue ? 'overdue' : ''}`}>{relativeDue(followup.due_at, now)}</span>
                                            <span className="due-absolute">{dateTime(followup.due_at)}</span>
                                        </span>

                                        <ChevronRight className="followup-chevron" size={18} aria-hidden="true" />
                                    </button>

                                    <div className="followup-actions">
                                        {isActionable ? (
                                            <button
                                                type="button"
                                                className="btn-secondary btn-sm followup-complete"
                                                disabled={pendingId === followup.followup_id}
                                                onClick={() => handleComplete(followup.followup_id, lead.customer_name)}
                                            >
                                                {pendingId === followup.followup_id
                                                    ? <BusyLabel>Completing…</BusyLabel>
                                                    : <><Check size={14} aria-hidden="true" /> Complete</>}
                                            </button>
                                        ) : reason ? (
                                            <span className="followup-blocked">{reason}</span>
                                        ) : null}
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </section>
        </div>
    );
}
