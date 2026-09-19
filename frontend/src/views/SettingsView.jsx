import React, { useState, useEffect } from 'react';
import { Settings, Save, Shield, Database, Server } from 'lucide-react';
import { api } from '../api/client';

export function SettingsView() {
    const [config, setConfig] = useState({
        business_name: 'LeadRescue AI SMB Demo',
        response_target_minutes: 20,
        high_value_threshold: 50000,
        supported_locations: ['Pune', 'Mumbai', 'Delhi', 'Bangalore'],
    });

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);

    useEffect(() => {
        async function loadConfig() {
            try {
                const res = await api.getConfig();
                if (res && res.config_value) {
                    setConfig(res.config_value);
                }
            } catch (err) {
                console.error('Failed to load settings:', err);
            } finally {
                setLoading(false);
            }
        }
        loadConfig();
    }, []);

    const handleSave = async (e) => {
        e.preventDefault();
        setSaving(true);
        setSaveSuccess(false);
        try {
            await api.updateConfig(config);
            setSaveSuccess(true);
            setTimeout(() => setSaveSuccess(false), 3000);
        } catch (err) {
            alert(`Failed to save settings: ${err.message}`);
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-dim)' }}>Loading Configuration...</div>;
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '800px' }}>
            {/* Header */}
            <div>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.2rem' }}>Settings & Business Rules</h2>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                    Configure policy parameters, response SLAs, and high-value thresholds.
                </p>
            </div>

            {/* Main Settings Form */}
            <div className="panel">
                <div className="panel-header">
                    <div className="panel-title">
                        <Settings size={18} color="var(--accent-primary)" />
                        Deterministic Business Rules Configuration
                    </div>
                    <span className="badge-sub">DynamoDB Table: config</span>
                </div>

                <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                    <div>
                        <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.3rem' }}>
                            Business / Organization Name
                        </label>
                        <input
                            type="text"
                            value={config.business_name || ''}
                            onChange={(e) => setConfig({ ...config, business_name: e.target.value })}
                            style={{
                                width: '100%',
                                padding: '0.6rem',
                                borderRadius: 'var(--radius-sm)',
                                background: 'var(--bg-dark-0)',
                                border: '1px solid var(--border-color)',
                                color: 'var(--text-main)',
                                fontSize: '0.9rem',
                            }}
                        />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div>
                            <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.3rem' }}>
                                Response Target SLA (Minutes) *
                            </label>
                            <input
                                type="number"
                                required
                                min={1}
                                value={config.response_target_minutes || 20}
                                onChange={(e) => setConfig({ ...config, response_target_minutes: parseInt(e.target.value) || 20 })}
                                style={{
                                    width: '100%',
                                    padding: '0.6rem',
                                    borderRadius: 'var(--radius-sm)',
                                    background: 'var(--bg-dark-0)',
                                    border: '1px solid var(--border-color)',
                                    color: 'var(--text-main)',
                                    fontSize: '0.9rem',
                                }}
                            />
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginTop: '0.2rem' }}>
                                Leads unresponded after this duration trigger AT_RISK status.
                            </span>
                        </div>

                        <div>
                            <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.3rem' }}>
                                High-Value Deal Threshold ($) *
                            </label>
                            <input
                                type="number"
                                required
                                min={0}
                                value={config.high_value_threshold || 50000}
                                onChange={(e) => setConfig({ ...config, high_value_threshold: parseFloat(e.target.value) || 0 })}
                                style={{
                                    width: '100%',
                                    padding: '0.6rem',
                                    borderRadius: 'var(--radius-sm)',
                                    background: 'var(--bg-dark-0)',
                                    border: '1px solid var(--border-color)',
                                    color: 'var(--text-main)',
                                    fontSize: '0.9rem',
                                }}
                            />
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginTop: '0.2rem' }}>
                                Deals exceeding this value award +5 bonus score points.
                            </span>
                        </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
                        {saveSuccess ? (
                            <span style={{ color: 'var(--color-success)', fontWeight: 600, fontSize: '0.85rem' }}>
                                ✓ Settings successfully saved to DynamoDB
                            </span>
                        ) : <span />}

                        <button type="submit" disabled={saving} className="btn-primary">
                            <Save size={16} /> {saving ? 'Saving...' : 'Save Configuration'}
                        </button>
                    </div>
                </form>
            </div>

            {/* System Infrastructure Information */}
            <div className="panel" style={{ background: 'var(--bg-dark-0)' }}>
                <div className="panel-header">
                    <div className="panel-title" style={{ fontSize: '0.9rem' }}>
                        <Server size={16} color="var(--accent-primary)" />
                        Backend Infrastructure Environment
                    </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-dim)' }}>API Base URL:</span>
                        <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)' }}>{import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'}</code>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-dim)' }}>Strands Agent SDK:</span>
                        <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>1.56.0 Connected</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-dim)' }}>AWS Bedrock Verification:</span>
                        <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>Local Offline Fallback (Unconfigured Host AWS CLI)</span>
                    </div>
                </div>
            </div>

        </div>
    );
}
