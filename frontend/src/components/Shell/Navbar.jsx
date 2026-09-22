import React, { useState } from 'react';
import { FastForward, RefreshCw, Clock3, Menu, ChevronRight, FlaskConical, Database, LogOut } from 'lucide-react';
import { api } from '../../api/client';
import { dateTime, timeOnly, safeError } from '../../api/presentation';
import { Modal, Notice, BusyLabel } from '../Common/UI';

const labels = { dashboard: 'Overview', inbox: 'Leads', detail: 'Lead workspace', followups: 'Follow-ups', activity: 'Activity', settings: 'Settings' };
export function Navbar({ currentView, onRefreshData, onMenu, clock, connected, refreshing, demoMode = false, onSignOut }) {
    const [showClock, setShowClock] = useState(false);
    const [action, setAction] = useState(null);
    const [notice, setNotice] = useState(null);
    const run = async kind => {
        if (action) return;
        setAction(kind); setNotice(null);
        try {
            if (kind === 'advance') await api.advanceDemoTime(20);
            else if (kind === 'reset') await api.resetDemoClock();
            else await api.seedDemoLeads();
            await onRefreshData();
            setNotice({ tone: 'success', text: kind === 'seed' ? 'Synthetic demo leads added. Open Leads to review them.' : 'Clock updated. Lead risk has been refreshed from the API.' });
        } catch (error) { setNotice({ tone: 'error', text: safeError(error, 'The demo action could not be confirmed. Refresh before retrying.') }); }
        finally { setAction(null); }
    };
    return <>
        <header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={onMenu}><Menu size={20} /></button><span className="breadcrumb-root">Workspace</span><ChevronRight size={13} /><strong>{labels[currentView] || 'Overview'}</strong></div><div className="topbar-actions"><span className={`connection-label ${connected ? 'connected' : ''}`}><i />{connected ? 'API connected' : 'API unavailable'}</span>{demoMode && <><span className="demo-label"><FlaskConical size={13} /> DEMO MODE</span><button className="clock-trigger" onClick={() => setShowClock(true)} title="Open demo clock controls"><Clock3 size={15} /><span>{clock?.effective_now ? timeOnly(clock.effective_now) : 'Demo clock'}</span></button></>}<button className="icon-button" title="Refresh workspace" aria-label="Refresh workspace" disabled={refreshing} onClick={() => onRefreshData()}><RefreshCw size={16} className={refreshing ? 'spin' : ''} /></button>{demoMode ? <span className="operator-avatar" title="Demo operator">OP</span> : <button className="icon-button" title="Sign out" aria-label="Sign out" onClick={onSignOut}><LogOut size={16} /></button>}</div></header>
        {showClock && <Modal title="Demo controls" description="Synthetic data. Simulated time. No external messages." onClose={() => setShowClock(false)} busy={!!action}><div className="view-stack"><div className="clock-display"><span className="eyebrow">SERVER EFFECTIVE TIME</span><strong>{dateTime(clock?.effective_now)}</strong><p>All time labels use this server snapshot, not your device clock.</p></div>{notice && <Notice tone={notice.tone}>{notice.text}</Notice>}<div className="action-grid"><button className="btn-primary" disabled={!!action || !clock} onClick={() => run('advance')}>{action === 'advance' ? <BusyLabel>Advancing…</BusyLabel> : <><FastForward size={16} /> Advance +20 min</>}</button><button className="btn-secondary" disabled={!!action || !clock} onClick={() => run('reset')}><RefreshCw size={15} /> Reset clock</button></div><p className="form-note">The policy engine re-evaluates risk. A lead already sent a simulated response is not an unanswered lead; use an unanswered lead to demonstrate rescue.</p><div className="seed-section"><div><strong>Add demo leads</strong><p>Add the canonical synthetic examples to the existing dataset.</p></div><button className="btn-secondary" disabled={!!action || !connected} onClick={() => run('seed')}><Database size={15} /> {action === 'seed' ? 'Adding…' : 'Seed leads'}</button></div></div></Modal>}
    </>;
}
