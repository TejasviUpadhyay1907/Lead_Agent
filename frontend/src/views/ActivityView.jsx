import React, { useEffect, useMemo, useState } from 'react';
import { Activity, History, Search, ExternalLink } from 'lucide-react';
import { api } from '../api/client';
import { PageHeader, SectionHeader, EmptyState, ErrorState, Skeleton, Avatar } from '../components/Common/UI';
import { ActivityTimeline } from '../components/Common/ActivityTimeline';
import { humanize, safeError } from '../api/presentation';

/**
 * Audit inspection is scoped to a single lead at a time.
 * The audit endpoint is per-lead, so the view never issues a fan-out query across all leads.
 * Navigation to the lead detail record stays with the parent via onSelectLead.
 */
export function ActivityView({ leads, revision, onSelectLead }) {
    const [selectedLeadId, setSelectedLeadId] = useState(null);
    const [search, setSearch] = useState('');
    const [events, setEvents] = useState([]);
    const [nextCursor, setNextCursor] = useState(null);
    const [loadingMore, setLoadingMore] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [attempt, setAttempt] = useState(0);

    const leadList = Array.isArray(leads) ? leads : [];

    const selectedLead = useMemo(
        () => leadList.find(lead => lead.lead_id === selectedLeadId) || null,
        [leadList, selectedLeadId]
    );

    useEffect(() => {
        if (!selectedLeadId) {
            setEvents([]);
            setNextCursor(null);
            setError(null);
            setLoading(false);
            return undefined;
        }

        let cancelled = false;
        setLoading(true);
        setError(null);

        (async () => {
            try {
                const data = await api.getAudit(selectedLeadId);
                if (cancelled) return;
                if (!data || !Array.isArray(data.items)) {
                    setEvents([]);
                    setError('The server returned an audit response in an unexpected format.');
                    return;
                }
                setEvents(data.items);
                setNextCursor(data.nextCursor);
            } catch (auditError) {
                if (cancelled) return;
                setEvents([]);
                setError(safeError(auditError, 'The audit trail could not be loaded for this lead.'));
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();

        return () => { cancelled = true; };
    }, [selectedLeadId, revision, attempt]);

    const loadMore = async () => {
        if (!nextCursor || loadingMore) return;
        setLoadingMore(true);
        try {
            const page = await api.getAudit(selectedLeadId, nextCursor);
            setEvents(current => [...current, ...page.items]);
            setNextCursor(page.nextCursor);
        } catch (auditError) {
            setError(safeError(auditError, 'The next audit page could not be loaded.'));
        } finally {
            setLoadingMore(false);
        }
    };

    const filteredLeads = useMemo(() => {
        const term = search.trim().toLowerCase();
        if (!term) return leadList;
        return leadList.filter(lead => {
            const name = typeof lead.customer_name === 'string' ? lead.customer_name.toLowerCase() : '';
            const id = typeof lead.lead_id === 'string' ? lead.lead_id.toLowerCase() : '';
            return name.includes(term) || id.includes(term);
        });
    }, [leadList, search]);

    return (
        <div className="view-stack">
            <PageHeader
                eyebrow="Operations"
                title="Activity & Audit"
                description="Inspect the recorded audit trail for one lead. Only events returned by the server are displayed."
            >
                {selectedLead && onSelectLead && (
                    <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => onSelectLead(selectedLead.lead_id)}
                    >
                        <ExternalLink size={15} aria-hidden="true" /> Open lead detail
                    </button>
                )}
            </PageHeader>

            <div className="activity-layout">
                <aside className="panel activity-picker">
                    <SectionHeader
                        icon={History}
                        title="Select a lead"
                        subtitle="One lead is queried at a time."
                    />

                    <div className="field">
                        <label className="field-label" htmlFor="activity-lead-search">Search leads</label>
                        <div className="input-with-icon">
                            <Search size={15} aria-hidden="true" />
                            <input
                                id="activity-lead-search"
                                type="search"
                                className="field-input"
                                placeholder="Customer name or lead ID"
                                value={search}
                                onChange={event => setSearch(event.target.value)}
                            />
                        </div>
                    </div>

                    {leadList.length === 0 ? (
                        <EmptyState
                            icon={Activity}
                            title="No leads available"
                            description="Load or seed leads before inspecting the audit trail."
                        />
                    ) : filteredLeads.length === 0 ? (
                        <EmptyState
                            icon={Search}
                            title="No leads match this search"
                            description="Clear the search to see all leads again."
                        />
                    ) : (
                        <ul className="lead-select-list">
                            {filteredLeads.map(lead => {
                                const isActive = lead.lead_id === selectedLeadId;
                                return (
                                    <li key={lead.lead_id}>
                                        <button
                                            type="button"
                                            className={`lead-select-item ${isActive ? 'active' : ''}`}
                                            aria-pressed={isActive}
                                            onClick={() => setSelectedLeadId(lead.lead_id)}
                                        >
                                            <Avatar name={lead.customer_name} />
                                            <span className="lead-select-main">
                                                <span className="lead-select-name">{lead.customer_name || 'Unnamed lead'}</span>
                                                <span className="lead-select-meta">{humanize(lead.lifecycle_status)}</span>
                                            </span>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                <section className="panel activity-trail">
                    <SectionHeader
                        icon={Activity}
                        title={selectedLead ? `${selectedLead.customer_name || 'Lead'} — audit trail` : 'Audit trail'}
                        subtitle={selectedLead ? `Lead ID ${selectedLead.lead_id}` : 'Select a lead to load its recorded events.'}
                    />

                    {!selectedLeadId ? (
                        <EmptyState
                            icon={History}
                            title="No lead selected"
                            description="Choose a lead from the list to inspect its recorded audit trail."
                        />
                    ) : loading ? (
                        <Skeleton rows={4} label="Loading audit trail…" />
                    ) : error ? (
                        <ErrorState
                            title="Unable to load audit trail"
                            description={error}
                            onRetry={() => setAttempt(value => value + 1)}
                        />
                    ) : (
                        <>
                            <ActivityTimeline events={events} onSelectLead={onSelectLead} />
                            {nextCursor && <button type="button" className="btn-secondary" disabled={loadingMore} onClick={loadMore}>{loadingMore ? 'Loading…' : 'Load older events'}</button>}
                        </>
                    )}
                </section>
            </div>
        </div>
    );
}
