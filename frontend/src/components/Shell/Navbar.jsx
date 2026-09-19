import React, { useState } from 'react';
import { FastForward, RefreshCw, Sun, Moon, Shield, Sparkles, Database } from 'lucide-react';
import { api } from '../../api/client';

export function Navbar({ theme, toggleTheme, onRefreshData }) {
    const [advancing, setAdvancing] = useState(false);
    const [seeding, setSeeding] = useState(false);
    const [demoNotice, setDemoNotice] = useState('');

    const handleAdvanceTime = async () => {
        setAdvancing(true);
        try {
            const res = await api.advanceDemoTime(20);
            setDemoNotice(`Advanced demo clock +20m (${res.leads_at_risk} leads at risk)`);
            if (onRefreshData) onRefreshData();
            setTimeout(() => setDemoNotice(''), 4000);
        } catch (err) {
            alert(`Failed to advance demo time: ${err.message}`);
        } finally {
            setAdvancing(false);
        }
    };

    const handleResetClock = async () => {
        try {
            await api.resetDemoClock();
            setDemoNotice('Demo clock reset to real system time');
            if (onRefreshData) onRefreshData();
            setTimeout(() => setDemoNotice(''), 4000);
        } catch (err) {
            alert(`Failed to reset demo clock: ${err.message}`);
        }
    };

    const handleSeedLeads = async () => {
        setSeeding(true);
        try {
            const res = await api.seedDemoLeads();
            setDemoNotice(`Seeded ${res.seeded_count} canonical demo leads`);
            if (onRefreshData) onRefreshData();
            setTimeout(() => setDemoNotice(''), 4000);
        } catch (err) {
            alert(`Failed to seed demo leads: ${err.message}`);
        } finally {
            setSeeding(false);
        }
    };

    return (
        <header style={{
            height: '64px',
            background: 'var(--bg-dark-1)',
            borderBottom: '1px solid var(--border-color)',
            padding: '0 1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            position: 'sticky',
            top: 0,
            zIndex: 100,
        }}>
            {/* Brand Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'linear-gradient(135deg, var(--accent-primary), #4f46e5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#fff',
                    boxShadow: 'var(--shadow-glow)',
                }}>
                    <Sparkles size={20} />
                </div>
                <div>
                    <h1 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0, lineHeight: 1.2 }}>
                        LeadRescue AI
                    </h1>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block' }}>
                        Agentic Lead Rescue & Operations
                    </span>
                </div>

                <span className="badge" style={{ background: 'rgba(99, 102, 241, 0.15)', color: 'var(--accent-primary)', border: '1px solid var(--accent-glow)', marginLeft: '0.5rem' }}>
                    DEMO MODE
                </span>
                <span className="badge" style={{ background: 'var(--bg-dark-2)', color: 'var(--text-muted)', border: '1px solid var(--border-color)' }}>
                    SYNTHETIC DATA
                </span>
            </div>

            {/* Demo Controls & Actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                {demoNotice && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-success)', fontWeight: 500, animation: 'fadeIn 0.3s' }}>
                        ✓ {demoNotice}
                    </span>
                )}

                <button
                    onClick={handleSeedLeads}
                    disabled={seeding}
                    className="btn-secondary"
                    title="Seed the 5 canonical Phase 0 demo leads"
                    style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                >
                    <Database size={14} /> {seeding ? 'Seeding...' : 'Seed Canonical Leads'}
                </button>

                <button
                    onClick={handleAdvanceTime}
                    disabled={advancing}
                    className="btn-primary"
                    title="Advance demo clock by +20 minutes to test SLA at-risk triggers"
                    style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                >
                    <FastForward size={14} /> {advancing ? 'Advancing...' : '+20 Min Clock'}
                </button>

                <button
                    onClick={handleResetClock}
                    className="btn-secondary"
                    title="Reset demo clock to real UTC time"
                    style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                >
                    <RefreshCw size={14} /> Reset
                </button>

                <button
                    onClick={toggleTheme}
                    className="btn-secondary"
                    style={{ padding: '0.4rem 0.6rem' }}
                    title="Toggle Dark / Light Theme"
                >
                    {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                </button>
            </div>
        </header>
    );
}
