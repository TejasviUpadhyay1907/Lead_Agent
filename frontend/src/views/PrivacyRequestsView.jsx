import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, ShieldAlert, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { dateTime, humanize } from '../api/presentation';
import { EmptyState, ErrorState, Notice, PageHeader, Skeleton } from '../components/Common/UI';

function nextAction(request) {
    switch (request.status) {
        case 'pending_admin_review': return ['identity_verification_required', 'Require identity verification'];
        case 'identity_verification_required': return ['verified', 'Confirm identity verified'];
        case 'verified': return ['in_progress', 'Start manual review'];
        case 'in_progress': return ['completed', 'Record manual completion'];
        default: return null;
    }
}

function canReject(request) {
    return request.status === 'identity_verification_required';
}

export function PrivacyRequestsView({ onSelectLead }) {
    const [requests, setRequests] = useState([]);
    const [cursor, setCursor] = useState(null);
    const [loading, setLoading] = useState(true);
    const [busyId, setBusyId] = useState(null);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [filterStatus, setFilterStatus] = useState('open');
    const [recordPages, setRecordPages] = useState({});
    const [recordBusy, setRecordBusy] = useState('');
    const [recordErrors, setRecordErrors] = useState({});
    const loadVersion = useRef(0);

    const load = useCallback(async (nextCursor = null, append = false) => {
        const version = ++loadVersion.current;
        setLoading(true);
        setError('');
        try {
            const page = await api.getPrivacyRequestsPage({ cursor: nextCursor, status: filterStatus === 'all' ? null : filterStatus });
            if (version !== loadVersion.current) return;
            setRequests(current => append ? [...current, ...page.items] : page.items);
            setCursor(page.nextCursor);
        } catch (reason) {
            if (version !== loadVersion.current) return;
            setError(reason.status === 403
                ? 'This queue is restricted to company administrators.'
                : 'Privacy requests could not be loaded. Retry when the API is available.');
        } finally {
            if (version === loadVersion.current) setLoading(false);
        }
    }, [filterStatus]);

    useEffect(() => { load(); }, [load]);

    const advance = async (request, targetStatus = nextAction(request)?.[0], resolutionOverride = null) => {
        const status = targetStatus;
        if (!status) return;
        if (status === 'completed' && !window.confirm(
            'Confirm that your company’s approved identity, legal, and fulfillment steps are complete. This action only records your attestation; LeadRescue will not export or erase data.'
        )) return;
        setBusyId(request.request_id);
        setError('');
        setNotice('');
        try {
            const resolutionCode = status === 'completed'
                ? (request.request_type === 'erasure' ? 'erasure_completed' : 'access_provided')
                : resolutionOverride;
            const updatedRequest = await api.updatePrivacyRequestStatus(request.request_id, status, resolutionCode);
            const isClosed = ['completed', 'rejected'].includes(updatedRequest.status);
            const leavesFilter = (filterStatus === 'open' && isClosed)
                || (filterStatus === 'closed' && !isClosed)
                || (!['open', 'closed', 'all'].includes(filterStatus) && updatedRequest.status !== filterStatus);
            setRequests(current => leavesFilter
                ? current.filter(item => item.request_id !== updatedRequest.request_id)
                : current.map(item => item.request_id === updatedRequest.request_id ? updatedRequest : item));
            setNotice('Request status recorded. Any access or erasure work must be completed and verified through the company’s approved privacy process before marking it complete.');
        } catch (reason) {
            setError(reason.status === 409
                ? 'Another administrator updated this request. Refresh the queue before continuing.'
                : 'The status could not be recorded. Refresh and try again.');
        } finally {
            setBusyId(null);
        }
    };

    const discoverRecords = async (request, match, cursor = null) => {
        const key = `${request.request_id}:${match}`;
        setRecordBusy(key);
        setRecordErrors(current => ({ ...current, [key]: '' }));
        try {
            const page = await api.getPrivacyRequestRecordsPage(request.request_id, { match, cursor });
            setRecordPages(current => ({
                ...current,
                [key]: {
                    items: cursor ? [...(current[key]?.items || []), ...page.items] : page.items,
                    nextCursor: page.nextCursor,
                },
            }));
        } catch (reason) {
            setRecordErrors(current => ({
                ...current,
                [key]: reason.status === 409
                    ? 'Identity must be verified before record discovery.'
                    : 'Matching records could not be loaded. Retry the lookup.',
            }));
        } finally {
            setRecordBusy('');
        }
    };

    if (loading && requests.length === 0) return <Skeleton rows={5} label="Loading privacy request queue…" />;

    return <section className="privacy-queue">
        <PageHeader eyebrow="CUSTOMER DATA" title="Privacy requests" description="Review access and erasure requests. Verify identity and follow your company’s approved privacy process." >
            <button className="btn-secondary" onClick={() => load()} disabled={loading}><RefreshCw size={16} /> Refresh</button>
        </PageHeader>
        <Notice tone="warning">This queue tracks administrator review only. It does not export or delete customer data. Complete the approved process outside this screen before recording completion.</Notice>
        {notice && <Notice>{notice}</Notice>}
        <label className="privacy-filter">Show requests
            <select value={filterStatus} disabled={loading || Boolean(busyId)} onChange={event => { setFilterStatus(event.target.value); setRequests([]); setCursor(null); }}>
                <option value="open">Open requests</option>
                <option value="pending_admin_review">Pending review</option>
                <option value="identity_verification_required">Identity verification required</option>
                <option value="verified">Identity verified</option>
                <option value="in_progress">In progress</option>
                <option value="completed">Completed</option>
                <option value="rejected">Rejected</option>
                <option value="closed">Closed requests</option>
                <option value="all">All requests</option>
            </select>
        </label>
        {error && <ErrorState title="Privacy queue unavailable" description={error} onRetry={() => load()} />}
        {!error && requests.length === 0 && <EmptyState icon={ShieldAlert} title="No privacy requests" description="Explicitly detected access or erasure requests will appear here for administrator review." />}
        {requests.length > 0 && <div className="privacy-request-list">
            {requests.map(request => {
                const action = nextAction(request);
                const canDiscover = ['verified', 'in_progress'].includes(request.status);
                return <article className="privacy-request-card" key={request.request_id}>
                    <div className="privacy-request-heading">
                        <div><span className="eyebrow">{humanize(request.request_type)} request</span><h2>{humanize(request.status)}</h2></div>
                        <time dateTime={request.created_at}>{dateTime(request.created_at)}</time>
                    </div>
                    <p>Request ID <code>{request.request_id}</code></p>
                    <p>Lead ID <code>{request.lead_id}</code></p>
                    <div className="privacy-request-actions">
                        {onSelectLead && <button className="btn-secondary btn-sm" onClick={() => onSelectLead(request.lead_id)}>Open lead <ArrowUpRight size={14} /></button>}
                        {action && <button className="btn-primary btn-sm" disabled={Boolean(busyId)} onClick={() => advance(request)}>{busyId === request.request_id ? 'Saving…' : action[1]}</button>}
                        {canReject(request) && <button className="btn-secondary btn-sm" disabled={Boolean(busyId)} onClick={() => advance(request, 'rejected', 'identity_not_verified')}>Close: identity not verified</button>}
                        {request.status === 'completed' && <span className="privacy-completion-code">Recorded: {humanize(request.resolution_code || 'not specified')}</span>}
                    </div>
                    {canDiscover && <div className="privacy-record-discovery">
                        <p>After identity verification, find candidate records by contact identifier. Results omit contact details and message text; review each record before fulfilling the request.</p>
                        {['email', 'phone'].map(match => {
                            const key = `${request.request_id}:${match}`;
                            const page = recordPages[key];
                            return <div className="privacy-record-match" key={match}>
                                <button className="btn-secondary btn-sm" disabled={Boolean(recordBusy)} onClick={() => discoverRecords(request, match)}>
                                    {recordBusy === key ? 'Searching…' : `Find records by ${match}`}
                                </button>
                                {recordErrors[key] && <span role="alert" className="form-error">{recordErrors[key]}</span>}
                                {page && <div className="privacy-record-results" role="status">
                                    {page.items.length === 0
                                        ? <span>No matching records found for this identifier.</span>
                                        : page.items.map(record => <div className="privacy-record-result" key={record.lead_id}>
                                            <span><code>{record.lead_id}</code><small>{humanize(record.source)} · {humanize(record.lifecycle_status)} · {dateTime(record.created_at)}</small></span>
                                            {onSelectLead && <button className="btn-text" onClick={() => onSelectLead(record.lead_id)}>Review record</button>}
                                        </div>)}
                                    {page.nextCursor && <button className="btn-text" disabled={Boolean(recordBusy)} onClick={() => discoverRecords(request, match, page.nextCursor)}>Load more matches</button>}
                                </div>}
                            </div>;
                        })}
                    </div>}
                </article>;
            })}
            {cursor && <button className="btn-secondary" onClick={() => load(cursor, true)} disabled={loading}>{loading ? 'Loading…' : 'Load more requests'}</button>}
        </div>}
    </section>;
}
