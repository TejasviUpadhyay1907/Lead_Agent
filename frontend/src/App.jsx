function App() {
    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100vh',
            fontFamily: 'Inter, system-ui, sans-serif',
            background: '#0f172a',
            color: '#e2e8f0',
        }}>
            <h1 style={{ fontSize: '2.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
                🚀 LeadRescue AI
            </h1>
            <p style={{ fontSize: '1.1rem', color: '#94a3b8' }}>
                Phase 1 Foundation — Environment Ready
            </p>
            <div style={{
                marginTop: '2rem',
                padding: '1rem 2rem',
                borderRadius: '8px',
                background: '#1e293b',
                border: '1px solid #334155',
                fontSize: '0.9rem',
                color: '#64748b',
            }}>
                Dashboard, Lead Inbox, Lead Detail, Follow-up Center — coming in Phase 5
            </div>
        </div>
    );
}

export default App;
