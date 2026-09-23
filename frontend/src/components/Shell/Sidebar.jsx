import React from 'react';
import { LayoutDashboard, Inbox, CalendarClock, Settings2, Activity, ArrowUpRight, ShieldCheck, LifeBuoy, X, ChevronDown } from 'lucide-react';

export function Sidebar({ currentView, setView, leadCount, dueCount, open, onClose, businessName, demoMode = false }) {
    const items = [
        ['dashboard', 'Overview', LayoutDashboard], ['inbox', 'Leads', Inbox, leadCount],
        ['followups', 'Follow-ups', CalendarClock, dueCount], ['activity', 'Activity', Activity], ['settings', 'Settings', Settings2],
    ];
    return <>
        {open && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={onClose} />}
        <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Main navigation">
            <a href="#/overview" className="brand" onClick={onClose}><span className="brand-symbol"><LifeBuoy size={25} strokeWidth={2} /></span><span>LeadRescue <b>AI</b></span></a>
            <button className="icon-button sidebar-close" aria-label="Close navigation" onClick={onClose}><X size={18} /></button>
            <div className="workspace-label"><span className="workspace-monogram">LR</span><div><strong title={businessName || (demoMode ? 'Demo workspace' : 'Company workspace')}>{businessName || (demoMode ? 'Demo workspace' : 'Company workspace')}</strong><small>Lead operations</small></div><ChevronDown size={14} /></div>
            <p className="nav-caption">WORKSPACE</p>
            <nav>{items.map(([id, label, Icon, count]) => <button key={id} className={`nav-item ${currentView === id ? 'active' : ''}`} aria-current={currentView === id ? 'page' : undefined} onClick={() => { setView(id); onClose(); }}><Icon size={18} /><span>{label}</span>{count != null && <span className="nav-count">{count}</span>}</button>)}</nav>
            <div className="sidebar-bottom"><div className="trust-card"><ShieldCheck size={20} /><strong>Intelligence, with guardrails.</strong><p>AI understands.<br />Software decides.<br />Human approves.</p><button onClick={() => { setView('settings'); onClose(); }}>Explore system trust <ArrowUpRight size={14} /></button></div><div className="workspace-footer"><span className="demo-dot" /><span>{demoMode ? 'Demo workspace' : 'Company workspace'}<small>{demoMode ? 'Synthetic data · No external messages' : 'Company data · Delivery not connected'}</small></span></div></div>
        </aside>
    </>;
}
