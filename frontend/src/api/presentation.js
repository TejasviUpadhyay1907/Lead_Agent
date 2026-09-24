/** Presentation helpers only. Scores, risk, priorities and eligibility remain API-owned. */
export const humanize = value => value == null || value === '' ? 'Not available' : String(value).replace(/[_-]/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
export const isBlocked = lead => Boolean(lead?.privacy_hold) || ['opted_out', 'resolved'].includes(lead?.lifecycle_status);
export const isOptedOut = lead => lead?.lifecycle_status === 'opted_out';
export const isPendingResponse = lead => !isBlocked(lead) && ['draft', 'edited'].includes(lead?.response_status);
export const isAwaitingDelivery = lead => !isBlocked(lead) && ['approved', 'simulated_sent'].includes(lead?.response_status);
export const isConfirmedSent = lead => lead?.response_status === 'sent';
export const lifecyclePresentationStatus = lead => lead?.response_status === 'simulated_sent' && lead?.lifecycle_status === 'contacted' ? 'contact_unverified' : lead?.lifecycle_status;
export const dateTime = value => value && Number.isFinite(new Date(value).getTime()) ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : 'Not available';
export const timeOnly = value => value && Number.isFinite(new Date(value).getTime()) ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : 'Unavailable';
export function relativeDue(value, now) {
    if (!value || !Number.isFinite(new Date(value).getTime()) || !now) return 'Time unavailable';
    const minutes = Math.ceil((new Date(value).getTime() - new Date(now).getTime()) / 60000);
    if (minutes === 0) return 'Due now';
    const absolute = Math.abs(minutes);
    const amount = absolute < 60 ? `${absolute} min` : absolute < 1440 ? `${Math.floor(absolute / 60)}h ${absolute % 60}m` : `${Math.floor(absolute / 1440)}d ${Math.floor(absolute % 1440 / 60)}h`;
    return minutes < 0 ? `Overdue by ${amount}` : `Due in ${amount}`;
}
/** Group the API's scheduled timestamps for display. Never write inferred states back. */
export function followupBucket(followup, lead, now) {
    if (followup.status === 'completed') return 'completed';
    if (['cancelled', 'canceled', 'stopped', 'skipped'].includes(followup.status) || (lead && isBlocked(lead))) return 'stopped';
    if (followup.status === 'overdue') return 'overdue';
    if (followup.status !== 'scheduled') return 'other';
    if (!now || !followup.due_at) return 'other';
    const delta = new Date(followup.due_at).getTime() - new Date(now).getTime();
    if (!Number.isFinite(delta)) return 'other';
    return delta < 0 ? 'overdue' : delta === 0 ? 'due' : 'upcoming';
}
export function auditLayer(actor) {
    const value = String(actor || '').toLowerCase();
    if (/human|operator|user/.test(value)) return 'human';
    if (/agent|ai|bedrock|llm/.test(value)) return 'ai';
    return 'policy';
}
export function safeError(error, fallback = 'The request could not be completed. Please try again.') {
    if (error?.detail && [400, 409, 422, 503].includes(error.status)) return error.detail;
    if (error?.status === 404) return 'This record was not found. Refresh the list and try again.';
    if (error?.status === 409) return 'The record changed or this action is no longer allowed. Refresh before trying again.';
    if (error?.status === 403) return 'The server has blocked this action. Check the current safeguards and permissions.';
    if (error?.status === 422) return 'The server could not accept these values. Review the form and try again.';
    return fallback;
}
