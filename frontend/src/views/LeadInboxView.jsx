import React, { useEffect, useMemo, useState } from 'react';
import { Search, Plus, ChevronRight, ChevronLeft, Eye, Inbox } from 'lucide-react';
import { PriorityBadge, RiskBadge, LifecycleBadge } from '../components/Common/Badge';
import { PageHeader, EmptyState, Notice, BusyLabel, Avatar, Modal } from '../components/Common/UI';
import { humanize, isPendingResponse, isOptedOut, lifecyclePresentationStatus, relativeDue, timeOnly, safeError } from '../api/presentation';

/** Channel values accepted by the create endpoint (existing API contract). */
const CHANNELS = [
    { value: 'whatsapp', label: 'WhatsApp' },
    { value: 'website', label: 'Website' },
    { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' },
    { value: 'marketplace', label: 'Marketplace' },
    { value: 'manual', label: 'Manual' },
];

const PAGE_SIZES = [15, 25];
const TABS = [
    { id: 'all', label: 'All' },
    { id: 'at_risk', label: 'At risk' },
    { id: 'pending', label: 'Pending approval' },
    { id: 'opted_out', label: 'Opted out' },
];

const normalize = value => (value == null ? '' : String(value).toLowerCase());
const truncate = (text, max = 120) => (!text ? '' : text.length > max ? `${text.slice(0, max).trimEnd()}…` : text);
const uniqueValues = values => [...new Set(values.filter(Boolean).map(value => normalize(value)))].sort();

function CustomerCell({ lead }) {
    return (
        <div className="cell-customer">
            <Avatar name={lead.customer_name} />
            <span className="customer-text">
                <span className="customer-name">{lead.customer_name || 'Unnamed lead'}</span>
                <span className="customer-contact">{lead.customer_email || lead.customer_phone || 'No contact returned'}</span>
            </span>
            {lead.source && <span className="channel-chip">{humanize(lead.source)}</span>}
        </div>
    );
}

function MessageCell({ lead }) {
    return (
        <div className="cell-message">
            <p className="message-text">{lead.raw_message ? truncate(lead.raw_message) : 'No message returned.'}</p>
            {lead.intent && (
                <span className="intent-line">
                    <span className="intent-label">AI intent</span>{humanize(lead.intent)}
                </span>
            )}
        </div>
    );
}

function ScoreCell({ lead }) {
    return (
        <div className="cell-score">
            {typeof lead.score === 'number'
                ? <span className="score-value">{lead.score}<small>/100</small></span>
                : <span className="score-pending">Unscored</span>}
            <PriorityBadge priority={lead.priority} />
        </div>
    );
}

function StatusCell({ lead }) {
    return (
        <div className="cell-status">
            <RiskBadge risk={lead.risk_status} />
            <LifecycleBadge status={lifecyclePresentationStatus(lead)} />
        </div>
    );
}

function FollowupCell({ entry, now }) {
    if (!entry) return <span className="muted-cell">None scheduled</span>;
    return (
        <div className="cell-followup">
            <span>{relativeDue(entry.followup.due_at, now)}</span>
            <small>{timeOnly(entry.followup.due_at)}</small>
        </div>
    );
}

export function LeadInboxView({ leads = [], followups, onSelectLead, onCreateLead, now, initialFilter, hasMore = false, loadingMore = false, onLoadMore, loadMoreError }) {
    const [tab, setTab] = useState(() => (TABS.some(item => item.id === initialFilter) ? initialFilter : 'all'));
    const [search, setSearch] = useState('');
    const [priorityFilter, setPriorityFilter] = useState('all');
    const [sourceFilter, setSourceFilter] = useState('all');
    const [lifecycleFilter, setLifecycleFilter] = useState('all');
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);

    const [showCreate, setShowCreate] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState(null);
    const [form, setForm] = useState({ customer_name: '', customer_email: '', customer_phone: '', source: 'whatsapp', raw_message: '' });

    const query = normalize(search).trim();

    const priorityOptions = useMemo(() => uniqueValues(leads.map(lead => lead.priority)), [leads]);
    const sourceOptions = useMemo(() => uniqueValues(leads.map(lead => lead.source)), [leads]);
    const lifecycleOptions = useMemo(() => uniqueValues(leads.map(lifecyclePresentationStatus)), [leads]);

    const tabCounts = useMemo(() => ({
        all: leads.length,
        at_risk: leads.filter(lead => normalize(lead.risk_status) === 'at_risk').length,
        pending: leads.filter(isPendingResponse).length,
        opted_out: leads.filter(isOptedOut).length,
    }), [leads]);

    const nextFollowupByLead = useMemo(() => {
        const map = new Map();
        if (!Array.isArray(followups)) return map;
        followups.forEach(followup => {
            if (!followup || followup.lead_id == null) return;
            if (['completed', 'cancelled', 'canceled', 'stopped', 'skipped'].includes(followup.status)) return;
            const time = followup.due_at ? new Date(followup.due_at).getTime() : NaN;
            if (!Number.isFinite(time)) return;
            const existing = map.get(followup.lead_id);
            if (!existing || time < existing.time) map.set(followup.lead_id, { time, followup });
        });
        return map;
    }, [followups]);

    const filtered = useMemo(() => leads.filter(lead => {
        if (tab === 'at_risk' && normalize(lead.risk_status) !== 'at_risk') return false;
        if (tab === 'pending' && !isPendingResponse(lead)) return false;
        if (tab === 'opted_out' && !isOptedOut(lead)) return false;
        if (priorityFilter !== 'all' && normalize(lead.priority) !== priorityFilter) return false;
        if (sourceFilter !== 'all' && normalize(lead.source) !== sourceFilter) return false;
        if (lifecycleFilter !== 'all' && normalize(lifecyclePresentationStatus(lead)) !== lifecycleFilter) return false;
        if (query) {
            const haystack = [
                lead.customer_name,
                lead.raw_message,
                lead.product,
                lead.location,
                lead.customer_email,
                lead.customer_phone,
            ].filter(Boolean).join(' ').toLowerCase();
            if (!haystack.includes(query)) return false;
        }
        return true;
    }), [leads, tab, priorityFilter, sourceFilter, lifecycleFilter, query]);

    useEffect(() => { setPage(1); }, [tab, query, priorityFilter, sourceFilter, lifecycleFilter, pageSize]);

    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const currentPage = Math.min(page, totalPages);
    const start = (currentPage - 1) * pageSize;
    const rows = filtered.slice(start, start + pageSize);
    const hasFilters = Boolean(query) || tab !== 'all' || priorityFilter !== 'all' || sourceFilter !== 'all' || lifecycleFilter !== 'all';

    const clearFilters = () => {
        setSearch('');
        setTab('all');
        setPriorityFilter('all');
        setSourceFilter('all');
        setLifecycleFilter('all');
    };

    const closeCreate = () => { if (!submitting) setShowCreate(false); };
    const canSubmit = Boolean(form.customer_name.trim() && form.raw_message.trim());

    const handleCreateSubmit = async event => {
        event.preventDefault();
        const customerName = form.customer_name.trim();
        const rawMessage = form.raw_message.trim();
        if (!customerName || !rawMessage) {
            setFormError('Customer name and incoming message are required.');
            return;
        }

        const payload = { customer_name: customerName, source: form.source, raw_message: rawMessage };
        const email = form.customer_email.trim();
        const phone = form.customer_phone.trim();
        if (email) payload.customer_email = email;
        if (phone) payload.customer_phone = phone;

        setSubmitting(true);
        setFormError(null);
        try {
            await onCreateLead(payload);
            setForm({ customer_name: '', customer_email: '', customer_phone: '', source: 'whatsapp', raw_message: '' });
            setShowCreate(false);
        } catch (error) {
            setFormError(safeError(error, 'The lead could not be created. Review the form and try again.'));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="inbox-view">
            <PageHeader
                eyebrow="LEAD WORKSPACE"
                title="Lead inbox"
                description="Search and filter the loaded lead records. Continue loading pages to reach older inquiries."
            >
                {hasMore && <button type="button" className="btn-secondary" onClick={onLoadMore} disabled={loadingMore}>{loadingMore ? <BusyLabel>Loading…</BusyLabel> : 'Load next 50'}</button>}
                <button type="button" className="btn-primary" onClick={() => { setFormError(null); setShowCreate(true); }}>
                    <Plus size={16} /> New lead
                </button>
            </PageHeader>

            {loadMoreError && <Notice tone="error">{loadMoreError}</Notice>}

            <section className="panel inbox-panel">
                <div className="inbox-toolbar">
                    <label className="inbox-search">
                        <Search size={16} aria-hidden="true" />
                        <span className="sr-only">Search leads</span>
                        <input
                            type="search"
                            value={search}
                            onChange={event => setSearch(event.target.value)}
                            placeholder="Search name, message, product, location or contact"
                        />
                    </label>

                    <div className="inbox-filters">
                        <label className="filter-field">
                            <span className="sr-only">Filter by priority</span>
                            <select value={priorityFilter} onChange={event => setPriorityFilter(event.target.value)}>
                                <option value="all">All priorities</option>
                                {priorityOptions.map(value => <option key={value} value={value}>{humanize(value)}</option>)}
                            </select>
                        </label>
                        <label className="filter-field">
                            <span className="sr-only">Filter by channel</span>
                            <select value={sourceFilter} onChange={event => setSourceFilter(event.target.value)}>
                                <option value="all">All channels</option>
                                {sourceOptions.map(value => <option key={value} value={value}>{humanize(value)}</option>)}
                            </select>
                        </label>
                        <label className="filter-field">
                            <span className="sr-only">Filter by lifecycle</span>
                            <select value={lifecycleFilter} onChange={event => setLifecycleFilter(event.target.value)}>
                                <option value="all">All lifecycle stages</option>
                                {lifecycleOptions.map(value => <option key={value} value={value}>{humanize(value)}</option>)}
                            </select>
                        </label>
                    </div>
                </div>

                <div className="inbox-tabs" role="group" aria-label="Lead quick filters">
                    {TABS.map(item => (
                        <button
                            key={item.id}
                            type="button"
                            className={`inbox-tab ${tab === item.id ? 'is-active' : ''}`}
                            aria-pressed={tab === item.id}
                            onClick={() => setTab(item.id)}
                        >
                            {item.label}<span className="tab-count">{tabCounts[item.id]}</span>
                        </button>
                    ))}
                </div>

                {leads.length === 0 ? (
                    <EmptyState
                        icon={Inbox}
                        title="No leads yet"
                        description="The API returned an empty lead list. Create the first lead to get started."
                    >
                        <button type="button" className="btn-primary" onClick={() => { setFormError(null); setShowCreate(true); }}>
                            <Plus size={16} /> New lead
                        </button>
                    </EmptyState>
                ) : filtered.length === 0 ? (
                    <EmptyState
                        icon={Search}
                        title="No leads match these filters"
                        description="Adjust the search or filters to see more leads."
                    >
                        {hasFilters && (
                            <button type="button" className="btn-secondary" onClick={clearFilters}>Clear filters</button>
                        )}
                    </EmptyState>
                ) : (
                    <>
                        <div className="inbox-table-wrap">
                            <table className="data-table inbox-table">
                                <thead>
                                    <tr>
                                        <th scope="col">Customer</th>
                                        <th scope="col">Message &amp; intent</th>
                                        <th scope="col">Score &amp; priority</th>
                                        <th scope="col">Risk &amp; lifecycle</th>
                                        <th scope="col">Next follow-up</th>
                                        <th scope="col"><span className="sr-only">Actions</span></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map(lead => (
                                        <tr key={lead.lead_id}>
                                            <td><CustomerCell lead={lead} /></td>
                                            <td><MessageCell lead={lead} /></td>
                                            <td><ScoreCell lead={lead} /></td>
                                            <td><StatusCell lead={lead} /></td>
                                            <td><FollowupCell entry={nextFollowupByLead.get(lead.lead_id)} now={now} /></td>
                                            <td className="cell-action">
                                                <button type="button" className="btn-secondary btn-sm" onClick={() => onSelectLead?.(lead.lead_id)}>
                                                    <Eye size={14} /> View
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        <ul className="inbox-cards">
                            {rows.map(lead => (
                                <li key={lead.lead_id} className="inbox-card">
                                    <div className="inbox-card-head"><CustomerCell lead={lead} /></div>
                                    <MessageCell lead={lead} />
                                    <div className="inbox-card-meta">
                                        <ScoreCell lead={lead} />
                                        <StatusCell lead={lead} />
                                    </div>
                                    <div className="inbox-card-foot">
                                        <FollowupCell entry={nextFollowupByLead.get(lead.lead_id)} now={now} />
                                        <button type="button" className="btn-secondary btn-sm" onClick={() => onSelectLead?.(lead.lead_id)}>
                                            <Eye size={14} /> View
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>

                        <div className="pagination">
                            <span className="pagination-info">
                                Showing {start + 1}–{Math.min(start + pageSize, filtered.length)} of {filtered.length} loaded
                            </span>
                            <label className="page-size">
                                <span className="sr-only">Rows per page</span>
                                <select value={pageSize} onChange={event => setPageSize(Number(event.target.value))}>
                                    {PAGE_SIZES.map(size => <option key={size} value={size}>{size} per page</option>)}
                                </select>
                            </label>
                            <div className="pagination-controls">
                                <button
                                    type="button"
                                    className="btn-secondary btn-sm"
                                    onClick={() => setPage(value => Math.max(1, value - 1))}
                                    disabled={currentPage <= 1}
                                >
                                    <ChevronLeft size={14} /> Previous
                                </button>
                                <span className="pagination-page">Page {currentPage} of {totalPages}</span>
                                <button
                                    type="button"
                                    className="btn-secondary btn-sm"
                                    onClick={() => setPage(value => Math.min(totalPages, value + 1))}
                                    disabled={currentPage >= totalPages}
                                >
                                    Next <ChevronRight size={14} />
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </section>

            {showCreate && (
                <Modal
                    title="New lead"
                    description="Record an incoming inquiry. It is analysed once created."
                    onClose={closeCreate}
                    busy={submitting}
                >
                    <form className="modal-form" onSubmit={handleCreateSubmit}>
                        {formError && <Notice tone="error">{formError}</Notice>}

                        <div className="form-field">
                            <label className="field-label" htmlFor="lead-name">
                                Customer name <span className="required-mark" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="lead-name"
                                type="text"
                                required
                                autoComplete="name"
                                value={form.customer_name}
                                onChange={event => setForm({ ...form, customer_name: event.target.value })}
                            />
                        </div>

                        <div className="form-grid">
                            <div className="form-field">
                                <label className="field-label" htmlFor="lead-email">
                                    Email <span className="field-optional">optional</span>
                                </label>
                                <input
                                    id="lead-email"
                                    type="email"
                                    autoComplete="email"
                                    value={form.customer_email}
                                    onChange={event => setForm({ ...form, customer_email: event.target.value })}
                                />
                            </div>
                            <div className="form-field">
                                <label className="field-label" htmlFor="lead-phone">
                                    Phone <span className="field-optional">optional</span>
                                </label>
                                <input
                                    id="lead-phone"
                                    type="tel"
                                    autoComplete="tel"
                                    value={form.customer_phone}
                                    onChange={event => setForm({ ...form, customer_phone: event.target.value })}
                                />
                            </div>
                        </div>

                        <div className="form-field">
                            <label className="field-label" htmlFor="lead-source">Channel</label>
                            <select
                                id="lead-source"
                                value={form.source}
                                onChange={event => setForm({ ...form, source: event.target.value })}
                            >
                                {CHANNELS.map(channel => <option key={channel.value} value={channel.value}>{channel.label}</option>)}
                            </select>
                        </div>

                        <div className="form-field">
                            <label className="field-label" htmlFor="lead-message">
                                Incoming message <span className="required-mark" aria-hidden="true">*</span>
                            </label>
                            <textarea
                                id="lead-message"
                                rows={4}
                                required
                                placeholder="Paste the customer's message exactly as received"
                                value={form.raw_message}
                                onChange={event => setForm({ ...form, raw_message: event.target.value })}
                            />
                        </div>

                        <div className="modal-actions">
                            <button type="button" className="btn-secondary" onClick={closeCreate} disabled={submitting}>Cancel</button>
                            <button type="submit" className="btn-primary" disabled={submitting || !canSubmit}>
                                {submitting ? <BusyLabel>Creating…</BusyLabel> : 'Create lead'}
                            </button>
                        </div>
                    </form>
                </Modal>
            )}
        </div>
    );
}
