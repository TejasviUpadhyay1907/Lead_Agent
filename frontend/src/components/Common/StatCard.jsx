import React from 'react';

/**
 * StatCard — a single operational metric.
 * Values are supplied by the caller from API data. When a metric cannot be
 * derived (for example follow-ups without a clock), pass `unavailable` and a
 * plain value such as "Unavailable" so the card never implies a false zero.
 */
export function StatCard({ label, value, hint, icon: Icon, tone = 'neutral', onClick, unavailable = false }) {
    const className = `stat-card tone-${tone}${unavailable ? ' is-unavailable' : ''}`;

    const content = (
        <>
            <span className="stat-body">
                <span className="stat-label">{label}</span>
                <span className="stat-value">{value}</span>
                {hint && <span className="stat-hint">{hint}</span>}
            </span>
            {Icon && <span className="stat-icon" aria-hidden="true"><Icon size={20} /></span>}
        </>
    );

    if (onClick) {
        return (
            <button type="button" className={`${className} is-clickable`} onClick={onClick}>
                {content}
            </button>
        );
    }

    return <div className={className}>{content}</div>;
}
