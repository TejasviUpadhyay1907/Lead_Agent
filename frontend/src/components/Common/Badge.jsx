import React from 'react';
import { AlertTriangle, CheckCircle2, Flame, Snowflake, Sun, ShieldOff } from 'lucide-react';
import { humanize } from '../../api/presentation';

export function PriorityBadge({ priority }) {
    const key = priority?.toLowerCase();
    const icons = { hot: Flame, warm: Sun, cold: Snowflake };
    const Icon = icons[key];
    return <span className={`badge ${Icon ? `badge-${key}` : 'badge-normal'}`}>{Icon && <Icon size={12} />}{priority ? priority.toUpperCase() : 'Unscored'}</span>;
}
export function RiskBadge({ risk }) {
    const key = risk?.toLowerCase();
    const atRisk = ['at_risk', 'overdue'].includes(key);
    const Icon = atRisk ? AlertTriangle : key === 'normal' ? CheckCircle2 : null;
    return <span className={`badge ${atRisk ? 'badge-at-risk' : 'badge-normal'}`}>{Icon && <Icon size={12} />}{humanize(risk)}</span>;
}
export function LifecycleBadge({ status }) {
    return <span className={`badge-sub ${status === 'opted_out' ? 'opt-out-label' : ''}`}>{status === 'opted_out' && <ShieldOff size={12} />}{humanize(status)}</span>;
}
