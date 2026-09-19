import React from 'react';
import { AlertTriangle, CheckCircle, Flame, Snowflake, Sun } from 'lucide-react';

export function PriorityBadge({ priority }) {
    if (!priority) return null;
    const p = priority.toLowerCase();

    if (p === 'hot') {
        return (
            <span className="badge badge-hot">
                <Flame size={12} /> HOT
            </span>
        );
    }
    if (p === 'warm') {
        return (
            <span className="badge badge-warm">
                <Sun size={12} /> WARM
            </span>
        );
    }
    return (
        <span className="badge badge-cold">
            <Snowflake size={12} /> COLD
        </span>
    );
}

export function RiskBadge({ risk }) {
    if (!risk) return null;
    const r = risk.toLowerCase();

    if (r === 'at_risk') {
        return (
            <span className="badge badge-at-risk">
                <AlertTriangle size={12} /> AT RISK
            </span>
        );
    }
    return (
        <span className="badge badge-normal">
            <CheckCircle size={12} /> NORMAL
        </span>
    );
}

export function LifecycleBadge({ status }) {
    if (!status) return null;
    const s = status.toLowerCase();

    const labels = {
        new: 'NEW',
        analyzed: 'ANALYZED',
        contacted: 'CONTACTED',
        follow_up: 'FOLLOW-UP',
        resolved: 'RESOLVED',
        opted_out: 'OPTED OUT',
    };

    return (
        <span className="badge-sub">
            {labels[s] || s.toUpperCase()}
        </span>
    );
}
