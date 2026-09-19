import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Shell/Navbar';
import { Sidebar } from './components/Shell/Sidebar';
import { DashboardView } from './views/DashboardView';
import { LeadInboxView } from './views/LeadInboxView';
import { LeadDetailView } from './views/LeadDetailView';
import { FollowupsView } from './views/FollowupsView';
import { SettingsView } from './views/SettingsView';
import { api } from './api/client';

function App() {
    const [currentView, setCurrentView] = useState('dashboard');
    const [selectedLeadId, setSelectedLeadId] = useState(null);
    const [theme, setTheme] = useState('dark');

    const [leads, setLeads] = useState([]);
    const [followups, setFollowups] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Fetch initial data from backend API
    const refreshData = async () => {
        try {
            const [leadsData, followupsData] = await Promise.all([
                api.getLeads().catch(() => []),
                api.getFollowups().catch(() => []),
            ]);
            setLeads(leadsData);
            setFollowups(followupsData);
            setError(null);
        } catch (err) {
            console.error('Error fetching data:', err);
            setError('Unable to connect to backend API server at http://127.0.0.1:8000/api');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        refreshData();
    }, []);

    const toggleTheme = () => {
        const nextTheme = theme === 'dark' ? 'light' : 'dark';
        setTheme(nextTheme);
        document.documentElement.setAttribute('data-theme', nextTheme);
    };

    const handleSelectLead = (leadId) => {
        setSelectedLeadId(leadId);
        setCurrentView('detail');
    };

    const handleAnalyzeLead = async (leadId) => {
        try {
            await api.analyzeLead(leadId);
            await refreshData();
            handleSelectLead(leadId);
        } catch (err) {
            alert(`Analysis failed: ${err.message}`);
        }
    };

    const handleCreateLead = async (leadData) => {
        const created = await api.createLead(leadData);
        await refreshData();
        handleSelectLead(created.lead_id);
    };

    const handleSeedData = async () => {
        try {
            await api.seedDemoLeads();
            await refreshData();
        } catch (err) {
            alert(`Failed to seed demo data: ${err.message}`);
        }
    };

    return (
        <div className="app-layout" data-theme={theme}>
            <Sidebar
                currentView={currentView === 'detail' ? 'inbox' : currentView}
                setView={(v) => { setCurrentView(v); setSelectedLeadId(null); }}
            />

            <div className="main-wrapper">
                <Navbar
                    theme={theme}
                    toggleTheme={toggleTheme}
                    onRefreshData={refreshData}
                />

                <main className="content-container">
                    {error && (
                        <div className="panel" style={{ borderLeft: '4px solid var(--color-hot)', marginBottom: '1.5rem', background: 'var(--bg-at-risk)' }}>
                            <strong style={{ color: 'var(--color-hot)', display: 'block' }}>Backend Connection Alert</strong>
                            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{error}. Ensure `uvicorn app.main:app` is running.</span>
                        </div>
                    )}

                    {currentView === 'dashboard' && (
                        <DashboardView
                            leads={leads}
                            followups={followups}
                            onSelectLead={handleSelectLead}
                            onSeedData={handleSeedData}
                            onAnalyzeLead={handleAnalyzeLead}
                        />
                    )}

                    {currentView === 'inbox' && (
                        <LeadInboxView
                            leads={leads}
                            onSelectLead={handleSelectLead}
                            onAnalyzeLead={handleAnalyzeLead}
                            onCreateLead={handleCreateLead}
                        />
                    )}

                    {currentView === 'detail' && selectedLeadId && (
                        <LeadDetailView
                            leadId={selectedLeadId}
                            onBack={() => { setCurrentView('inbox'); setSelectedLeadId(null); }}
                            onRefreshLeads={refreshData}
                        />
                    )}

                    {currentView === 'followups' && (
                        <FollowupsView
                            followups={followups}
                            leads={leads}
                            onSelectLead={handleSelectLead}
                        />
                    )}

                    {currentView === 'settings' && (
                        <SettingsView />
                    )}
                </main>
            </div>
        </div>
    );
}

export default App;
