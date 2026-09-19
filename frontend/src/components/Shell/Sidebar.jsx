import React from 'react';
import { LayoutDashboard, Inbox, Clock, Settings, ArrowRight } from 'lucide-react';

export function Sidebar({ currentView, setView }) {
    const navItems = [
        { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { id: 'inbox', label: 'Lead Inbox', icon: Inbox },
        { id: 'followups', label: 'Follow-ups', icon: Clock },
        { id: 'settings', label: 'Settings', icon: Settings },
    ];

    return (
        <aside style={{
            width: '240px',
            background: 'var(--bg-dark-1)',
            borderRight: '1px solid var(--border-color)',
            padding: '1.5rem 1rem',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
        }}>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                <div style={{ padding: '0 0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                    Navigation
                </div>

                {navItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = currentView === item.id;
                    return (
                        <button
                            key={item.id}
                            onClick={() => setView(item.id)}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '0.7rem 0.85rem',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '0.9rem',
                                fontWeight: isActive ? 600 : 500,
                                color: isActive ? 'var(--text-main)' : 'var(--text-muted)',
                                background: isActive ? 'var(--bg-dark-2)' : 'transparent',
                                borderLeft: isActive ? '3px solid var(--accent-primary)' : '3px solid transparent',
                                transition: 'all 0.15s ease',
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <Icon size={18} color={isActive ? 'var(--accent-primary)' : 'currentColor'} />
                                {item.label}
                            </div>
                            {isActive && <ArrowRight size={14} color="var(--accent-primary)" />}
                        </button>
                    );
                })}
            </nav>

            {/* Architecture Principle Footer Badge */}
            <div style={{
                padding: '1rem',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg-dark-0)',
                border: '1px solid var(--border-color)',
                fontSize: '0.75rem',
                color: 'var(--text-dim)',
            }}>
                <div style={{ fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    ARCHITECTURE BOUNDARY
                </div>
                <div style={{ lineHeight: 1.4 }}>
                    <strong style={{ color: 'var(--accent-primary)' }}>AI</strong> understands.<br />
                    <strong style={{ color: 'var(--color-success)' }}>Software</strong> decides.<br />
                    <strong style={{ color: 'var(--color-warm)' }}>Human</strong> approves.
                </div>
            </div>
        </aside>
    );
}
