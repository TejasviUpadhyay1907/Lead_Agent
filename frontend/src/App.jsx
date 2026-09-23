import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Navbar } from './components/Shell/Navbar';
import { Sidebar } from './components/Shell/Sidebar';
import { DashboardView } from './views/DashboardView';
import { LeadInboxView } from './views/LeadInboxView';
import { LeadDetailView } from './views/LeadDetailView';
import { FollowupsView } from './views/FollowupsView';
import { ActivityView } from './views/ActivityView';
import { SettingsView } from './views/SettingsView';
import { PrivacyRequestsView } from './views/PrivacyRequestsView';
import { ErrorState, Skeleton, Notice } from './components/Common/UI';
import { api } from './api/client';
import { followupBucket } from './api/presentation';
import { useAuth } from './auth/AuthContext';
import { demoMode, hasRole } from './auth/oidc';

const paths = { dashboard: 'overview', inbox: 'leads', followups: 'followups', activity: 'activity', settings: 'settings', privacy: 'privacy' };
function readRoute() {
    const [path, id] = window.location.hash.replace(/^#\/?/, '').split('/');
    if (path === 'leads' && id) return { view: 'detail', leadId: id };
    return { view: Object.keys(paths).find(key => paths[key] === path) || 'dashboard', leadId: null };
}
export default function App() {
    const auth = useAuth();
    const adminAccess = demoMode || hasRole(import.meta.env.VITE_OIDC_ADMIN_ROLE || 'company_admin');
    const [route, setRoute] = useState(readRoute);
    const [menuOpen, setMenuOpen] = useState(false);
    const [data, setData] = useState({ leads: [], followups: [], config: null, clock: null });
    const [errors, setErrors] = useState({});
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [revision, setRevision] = useState(0);
    const [leadCursor, setLeadCursor] = useState(null);
    const [followupCursor, setFollowupCursor] = useState(null);
    const [loadingMore, setLoadingMore] = useState(false);
    const [loadMoreError, setLoadMoreError] = useState('');
    const [inboxFilter, setInboxFilter] = useState('all');
    const inFlight = useRef(null);
    const refreshData = useCallback(() => {
        if (inFlight.current) return inFlight.current;
        setRefreshing(true);
        const job = (async () => {
            const keys = ['leads', 'followups', 'config', 'clock'];
            const calls = [api.getLeadsPage(), api.getFollowupsPage(), api.getConfig(), demoMode ? api.getDemoClock() : api.getServerTime()];
            const responses = await Promise.allSettled(calls);
            const next = {};
            const failures = {};
            responses.forEach((response, index) => {
                const key = keys[index];
                const valid = response.status === 'fulfilled' && (index < 2 ? Array.isArray(response.value.items) : key === 'config' ? response.value?.config_value : response.value?.effective_now);
                if (valid) next[key] = index < 2 ? response.value.items : key === 'config' ? response.value.config_value : response.value;
                else { next[key] = index < 2 ? [] : null; failures[key] = true; }
            });
            setLeadCursor(responses[0].status === 'fulfilled' ? responses[0].value.nextCursor : null);
            setFollowupCursor(responses[1].status === 'fulfilled' ? responses[1].value.nextCursor : null);
            setData(next); setErrors(failures); setRevision(value => value + 1);
            setLoadMoreError('');
            setLoading(false); setRefreshing(false);
            return !failures.leads && !failures.followups;
        })();
        inFlight.current = job;
        job.finally(() => { inFlight.current = null; });
        return job;
    }, []);
    useEffect(() => { refreshData(); }, [refreshData]);
    useEffect(() => {
        const handler = () => { setRoute(readRoute()); setMenuOpen(false); window.scrollTo(0, 0); };
        window.addEventListener('hashchange', handler);
        return () => window.removeEventListener('hashchange', handler);
    }, []);
    useEffect(() => {
        document.title = `${route.view === 'detail' ? 'Lead workspace' : ({dashboard:'Overview',inbox:'Leads',followups:'Follow-ups',activity:'Activity',settings:'Settings',privacy:'Privacy requests'})[route.view]} · LeadRescue AI`;
    }, [route.view]);
    useEffect(() => {
        if (!menuOpen) return;
        const handler = event => { if (event.key === 'Escape') setMenuOpen(false); };
        document.addEventListener('keydown', handler);
        const oldOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => { document.removeEventListener('keydown', handler); document.body.style.overflow = oldOverflow; };
    }, [menuOpen]);
    const navigate = (view, filter = 'all') => { setInboxFilter(filter); window.location.hash = `/${paths[view] || 'overview'}`; setMenuOpen(false); };
    const selectLead = id => { window.location.hash = `/leads/${encodeURIComponent(id)}`; };
    const loadMore = async kind => {
        const cursor = kind === 'leads' ? leadCursor : followupCursor;
        if (!cursor || loadingMore) return;
        setLoadingMore(true);
        setLoadMoreError('');
        try {
            const page = kind === 'leads' ? await api.getLeadsPage({ cursor }) : await api.getFollowupsPage({ cursor });
            setData(current => ({ ...current, [kind]: [...current[kind], ...page.items].sort((a, b) => {
                const left = kind === 'leads' ? a.created_at : a.due_at;
                const right = kind === 'leads' ? b.created_at : b.due_at;
                return kind === 'leads' ? right.localeCompare(left) : left.localeCompare(right);
            }) }));
            if (kind === 'leads') setLeadCursor(page.nextCursor);
            else setFollowupCursor(page.nextCursor);
            setRevision(value => value + 1);
        } catch {
            setLoadMoreError(`Could not load the next ${kind === 'leads' ? 'lead' : 'follow-up'} page. Retry when the API is available.`);
        } finally { setLoadingMore(false); }
    };
    const createLead = async values => { const lead = await api.createLead(values); await refreshData(); selectLead(lead.lead_id); };
    const seedLeads = async () => { const result = await api.seedDemoLeads(); await refreshData(); return result; };
    const dueCount = data.clock && !errors.followups && !errors.leads ? data.followups.filter(f => ['due', 'overdue'].includes(followupBucket(f, data.leads.find(l => l.lead_id === f.lead_id), data.clock.effective_now))).length : null;
    const needsLeads = ['dashboard', 'inbox', 'followups', 'activity'].includes(route.view);
    return <div className="app-layout"><a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a><Sidebar currentView={route.view === 'detail' ? 'inbox' : route.view} setView={navigate} leadCount={loading || errors.leads ? null : data.leads.length} dueCount={dueCount} businessName={data.config?.business_name} open={menuOpen} onClose={() => setMenuOpen(false)} demoMode={demoMode} adminAccess={adminAccess} /><div className="main-wrapper" inert={menuOpen ? '' : undefined}><Navbar currentView={route.view} clock={data.clock} onMenu={() => setMenuOpen(true)} onRefreshData={refreshData} refreshing={refreshing} connected={!loading && !errors.leads} demoMode={demoMode} onSignOut={auth.signOut} /><main className="content-container" id="main-content" tabIndex={-1}>
        {loading ? <Skeleton rows={6} label="Loading your operations workspace…" /> : needsLeads && errors.leads ? <ErrorState title="Your lead workspace is unavailable" description="We could not reach the lead API. No sample data has been substituted. Check that the API is available, then retry." onRetry={refreshData} /> : <>
            {route.view === 'dashboard' && <DashboardView leads={data.leads} followups={data.followups} onSelectLead={selectLead} onSeedData={demoMode ? seedLeads : undefined} demoMode={demoMode} onNavigate={navigate} now={data.clock?.effective_now} config={data.config} followupsError={errors.followups} onRetryFollowups={refreshData} />}
            {route.view === 'inbox' && <LeadInboxView leads={data.leads} followups={data.followups} onSelectLead={selectLead} onCreateLead={createLead} now={data.clock?.effective_now} initialFilter={inboxFilter} hasMore={Boolean(leadCursor)} loadingMore={loadingMore} onLoadMore={() => loadMore('leads')} loadMoreError={loadMoreError} />}
            {route.view === 'detail' && <LeadDetailView key={route.leadId} leadId={route.leadId} onBack={() => navigate('inbox')} onRefreshLeads={refreshData} revision={revision} config={data.config} clock={data.clock} followups={data.followups} followupsError={errors.followups} />}
            {route.view === 'followups' && <FollowupsView leads={data.leads} followups={data.followups} now={data.clock?.effective_now} onSelectLead={selectLead} onRefreshLeads={refreshData} error={errors.followups ? 'The follow-up API is unavailable. Retry to load the schedule.' : null} onRetry={refreshData} hasMore={Boolean(followupCursor)} loadingMore={loadingMore} onLoadMore={() => loadMore('followups')} loadMoreError={loadMoreError} />}
            {route.view === 'activity' && <ActivityView leads={data.leads} revision={revision} onSelectLead={selectLead} />}
            {route.view === 'settings' && <SettingsView onRefreshData={refreshData} clock={data.clock} demoMode={demoMode} />}
            {route.view === 'privacy' && <PrivacyRequestsView onSelectLead={selectLead} />}
        </>}
        <footer className="page-footer"><span>LeadRescue AI <span className="footer-divider">/</span> Lead intelligence, human control.</span><span>{demoMode ? 'Synthetic workspace · All sends are simulated' : 'Company workspace · Message delivery is not connected'}</span></footer>
    </main></div></div>;
}
