import React from 'react';

export function StatCard({ title, value, subtext, icon: Icon, color, onClick }) {
    return (
        <div
            className="panel"
            onClick={onClick}
            style={{
                cursor: onClick ? 'pointer' : 'default',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '1.25rem 1.5rem',
            }}
        >
            <div>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
                    {title}
                </span>
                <div style={{ fontSize: '2rem', fontWeight: 700, fontFamily: 'var(--font-heading)', marginTop: '0.2rem' }}>
                    {value}
                </div>
                {subtext && (
                    <span style={{ fontSize: '0.75rem', color: color || 'var(--text-dim)', marginTop: '0.2rem', display: 'block' }}>
                        {subtext}
                    </span>
                )}
            </div>

            {Icon && (
                <div style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: 'var(--radius-md)',
                    background: color ? `${color}18` : 'var(--bg-dark-2)',
                    color: color || 'var(--accent-primary)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                }}>
                    <Icon size={24} />
                </div>
            )}
        </div>
    );
}
