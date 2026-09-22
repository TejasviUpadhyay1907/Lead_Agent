import React, { useEffect, useRef, useId } from 'react';
import { ArrowRight, BrainCircuit, ShieldCheck, UserCheck, X, AlertCircle, Inbox, LoaderCircle, CheckCircle2 } from 'lucide-react';

export function PageHeader({ eyebrow, title, description, children }) {
    return <div className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{children && <div className="header-actions">{children}</div>}</div>;
}
export function SectionHeader({ icon: Icon, title, subtitle, children, layer }) {
    return <div className="section-header"><div className="section-heading">{Icon && <span className={`section-icon ${layer || ''}`}><Icon size={18} /></span>}<div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div></div>{children}</div>;
}
export function WorkflowStrip({ compact = false }) {
    return <div className={`workflow-strip ${compact ? 'compact' : ''}`} aria-label="AI understands. Software decides. Human approves.">{[
        [BrainCircuit, 'ai', 'AI understands', 'Intent, context & a factual draft'],
        [ShieldCheck, 'policy', 'Software decides', 'Priority, SLA & safeguards'],
        [UserCheck, 'human', 'Human approves', 'Your review. Your control.'],
    ].map(([Icon, layer, title, subtitle], index) => <React.Fragment key={layer}>{index > 0 && <ArrowRight className="workflow-arrow" size={16} />}<div className={`workflow-step ${layer}`}><span className="layer-icon"><Icon size={18} /></span><div><strong>{title}</strong>{!compact && <small>{subtitle}</small>}</div></div></React.Fragment>)}</div>;
}
export function EmptyState({ icon: Icon = Inbox, title, description, children }) {
    return <div className="empty-state"><span className="empty-icon"><Icon size={24} /></span><h3>{title}</h3><p>{description}</p>{children}</div>;
}
export function ErrorState({ title = 'Unable to load this view', description = 'The API did not respond. Check your connection and try again.', onRetry }) {
    return <div className="error-state" role="alert"><AlertCircle size={20} /><div><strong>{title}</strong><p>{description}</p></div>{onRetry && <button className="btn-secondary btn-sm" onClick={onRetry}>Try again</button>}</div>;
}
export function Notice({ children, tone = 'success' }) {
    const Icon = tone === 'error' ? AlertCircle : CheckCircle2;
    return <div className={`notice ${tone}`} role={tone === 'error' ? 'alert' : 'status'}><Icon size={18} /><div>{children}</div></div>;
}
export function Skeleton({ rows = 4, label = 'Loading workspace…' }) {
    return <div className="skeleton-group" role="status" aria-label={label}><span className="sr-only">{label}</span><div className="skeleton skeleton-title" />{Array.from({ length: rows }, (_, index) => <div className="skeleton skeleton-row" key={index} />)}</div>;
}
export function BusyLabel({ children }) { return <><LoaderCircle className="spin" size={16} />{children}</>; }
export function Avatar({ name, large = false }) {
    const initials = (name || '?').split(/\s+/).slice(0, 2).map(part => part[0]).join('');
    return <span className={`avatar ${large ? 'large' : ''}`} aria-hidden="true">{initials}</span>;
}
export function Modal({ title, description, onClose, children, busy = false }) {
    const ref = useRef(null);
    const titleId = useId();
    useEffect(() => {
        const previous = document.activeElement;
        const dialog = ref.current;
        dialog.showModal();
        return () => { dialog.close(); previous?.focus(); };
    }, []);
    return <dialog ref={ref} className="modal" aria-labelledby={titleId} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} onClick={event => { if (event.target === ref.current && !busy) onClose(); }}><div className="modal-content"><div className="modal-header"><div><h2 id={titleId}>{title}</h2>{description && <p>{description}</p>}</div><button className="icon-button" aria-label="Close dialog" disabled={busy} onClick={onClose}><X size={18} /></button></div>{children}</div></dialog>;
}
