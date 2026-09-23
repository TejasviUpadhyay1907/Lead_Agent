import React from 'react';
import { History, ExternalLink } from 'lucide-react';
import { EmptyState } from './UI';
import { auditLayer, dateTime, humanize } from '../../api/presentation';

/**
 * Only a fixed, meaningful subset of detail keys is ever rendered.
 * Anything else (raw payloads, prompts, contact details, credentials) stays hidden.
 */
const DETAIL_WHITELIST = new Set([
    'status',
    'lifecycle_status',
    'response_status',
    'risk_status',
    'priority',
    'score',
    'intent',
    'action',
    'reason',
    'decision',
    'layer',
    'channel',
    'source',
    'simulated',
    'from',
    'to',
    'previous',
    'current',
    'previous_status',
    'new_status',
    'approved',
    'rejected',
    'edited',
    'followup_id',
    'due_at',
    'target',
    'target_minutes',
    'rule',
    'trigger',
    'privacy_request_type',
    'privacy_request_status',
    'privacy_request_id',
    'request_type',
    'admin_action_required',
]);

const SENSITIVE_KEY = /(secret|token|password|passwd|credential|api[_-]?key|private|auth|prompt|payload|raw|customer_email|customer_phone|phone|email|address|contact)/i;

function formatDetailValue(value) {
    if (value === null || value === undefined) return 'Not available';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'number') return String(value);
    if (typeof value === 'string') return value.trim() === '' ? 'Not available' : value;
    if (Array.isArray(value)) {
        const parts = value
            .filter(item => ['string', 'number', 'boolean'].includes(typeof item))
            .map(item => String(item));
        return parts.length ? parts.join(', ') : 'Not available';
    }
    return null;
}

function safeDetails(details) {
    if (!details || typeof details !== 'object' || Array.isArray(details)) return [];
    return Object.entries(details)
        .filter(([key]) => DETAIL_WHITELIST.has(String(key).toLowerCase()) && !SENSITIVE_KEY.test(key))
        .map(([key, value]) => ({ key, label: humanize(key), value: formatDetailValue(value) }))
        .filter(entry => entry.value !== null);
}

export function ActivityTimeline({ events, onSelectLead }) {
    if (!Array.isArray(events) || events.length === 0) {
        return (
            <EmptyState
                icon={History}
                title="No audit events recorded"
                description="Nothing has been logged for this record yet. Events appear here after the record is processed or updated."
            />
        );
    }

    return (
        <ol className="timeline">
            {events.map((event, index) => {
                const actor = typeof event?.actor === 'string' && event.actor.trim() ? event.actor.trim() : null;
                const layer = actor ? auditLayer(actor) : 'policy';
                const details = safeDetails(event?.details);
                const eventKey = event?.event_id || `${event?.timestamp || 'event'}-${index}`;
                const leadId = event?.lead_id;

                return (
                    <li className="timeline-item" key={eventKey}>
                        <span className={`timeline-marker ${layer}`} aria-hidden="true" />
                        <div className="timeline-body">
                            <div className="timeline-head">
                                <strong className="timeline-action">
                                    {event?.action ? humanize(event.action) : 'Action not recorded'}
                                </strong>
                                <span className="timeline-time">{dateTime(event?.timestamp)}</span>
                            </div>

                            <span className={`timeline-actor ${layer}`}>
                                {actor ? humanize(actor) : 'Actor not recorded'}
                            </span>

                            {details.length > 0 && (
                                <dl className="timeline-details">
                                    {details.map(entry => (
                                        <div className="detail-row" key={entry.key}>
                                            <dt className="detail-key">{entry.label}</dt>
                                            <dd className="detail-value">{entry.value}</dd>
                                        </div>
                                    ))}
                                </dl>
                            )}

                            {onSelectLead && leadId && (
                                <button
                                    type="button"
                                    className="btn-secondary btn-sm"
                                    onClick={() => onSelectLead(leadId)}
                                >
                                    <ExternalLink size={14} aria-hidden="true" /> Open lead
                                </button>
                            )}
                        </div>
                    </li>
                );
            })}
        </ol>
    );
}
