import React, { useEffect, useState } from 'react';
import { Settings, Save, Server, ListChecks, Info } from 'lucide-react';
import { api } from '../api/client';
import { PageHeader, SectionHeader, ErrorState, Notice, Skeleton, BusyLabel } from '../components/Common/UI';
import { dateTime, humanize, safeError } from '../api/presentation';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/** Only these keys are ever edited. Every other returned key is preserved untouched on save. */
const EDITABLE_KEYS = ['business_name', 'response_target_minutes', 'high_value_threshold', 'supported_locations'];

const SENSITIVE_KEY = /(secret|token|password|passwd|credential|api[_-]?key|private)/i;

function formatConfigValue(value) {
    if (value === null || value === undefined) return 'Not available';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (Array.isArray(value)) return value.length ? value.join(', ') : 'None';
    if (typeof value === 'object') {
        try {
            return JSON.stringify(value);
        } catch {
            return 'Not available';
        }
    }
    return String(value);
}

export function SettingsView({ onRefreshData, clock, demoMode = false }) {
    const [config, setConfig] = useState(null);
    const [locationsText, setLocationsText] = useState('');
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [saving, setSaving] = useState(false);
    const [notice, setNotice] = useState(null);
    const [actionError, setActionError] = useState(null);
    const [loadedAt, setLoadedAt] = useState(null);

    const applyConfig = value => {
        setConfig(value);
        setLocationsText(Array.isArray(value.supported_locations) ? value.supported_locations.join(', ') : '');
    };

    const loadConfig = async () => {
        setLoading(true);
        setLoadError(null);
        setNotice(null);
        setActionError(null);
        try {
            const response = await api.getConfig();
            const value = response && typeof response.config_value === 'object' && response.config_value !== null
                ? response.config_value
                : null;
            if (!value) {
                setConfig(null);
                setLoadError('The server did not return a configuration value.');
                return;
            }
            applyConfig(value);
            setLoadedAt(new Date().toISOString());
        } catch (error) {
            setConfig(null);
            setLoadError(safeError(error, 'The configuration could not be loaded from the server.'));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadConfig();
    }, []);

    const hasKey = key => config !== null && Object.prototype.hasOwnProperty.call(config, key);
    const updateField = (key, value) => setConfig(previous => ({ ...previous, [key]: value }));

    const handleSubmit = async event => {
        event.preventDefault();
        if (!config) return;

        setNotice(null);
        setActionError(null);

        const payload = { ...config };

        if (hasKey('supported_locations')) {
            payload.supported_locations = locationsText
                .split(',')
                .map(part => part.trim())
                .filter(Boolean);
            if (payload.supported_locations.length > 200 || payload.supported_locations.some(location => location.length > 120)) {
                setActionError('Enter up to 200 supported locations, each no longer than 120 characters.');
                return;
            }
            const uniqueLocations = new Set(payload.supported_locations.map(location => location.toLocaleLowerCase()));
            if (uniqueLocations.size !== payload.supported_locations.length) {
                setActionError('Remove duplicate locations before saving.');
                return;
            }
        }
        if (hasKey('response_target_minutes')) {
            const minutes = Number(payload.response_target_minutes);
            if (!Number.isInteger(minutes) || minutes < 1 || minutes > 10080) {
                setActionError('Response target must be a whole number from 1 to 10080 minutes.');
                return;
            }
            payload.response_target_minutes = minutes;
        }
        if (hasKey('high_value_threshold')) {
            const threshold = Number(payload.high_value_threshold);
            if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1_000_000_000_000_000) {
                setActionError('High-value threshold must be between zero and 1000000000000000.');
                return;
            }
            payload.high_value_threshold = threshold;
        }
        if (hasKey('business_name')) {
            const name = String(payload.business_name ?? '').trim();
            if (!name || name.length > 120) {
                setActionError('Business name must contain 1 to 120 characters.');
                return;
            }
            payload.business_name = name;
        }

        setSaving(true);
        try {
            const response = await api.updateConfig(payload);
            const saved = response && typeof response.config_value === 'object' && response.config_value !== null
                ? response.config_value
                : payload;
            applyConfig(saved);
            setLoadedAt(new Date().toISOString());
            setNotice('Configuration saved.');
            if (onRefreshData) await onRefreshData();
        } catch (error) {
            setActionError(safeError(error, 'The configuration could not be saved. Review the values and try again.'));
        } finally {
            setSaving(false);
        }
    };

    const header = (
        <PageHeader
            eyebrow="Configuration"
            title="Settings"
            description="Business rules are owned by the server. This view edits only the values the API returns."
        >
            {onRefreshData && (
                <button type="button" className="btn-secondary" onClick={loadConfig} disabled={loading}>
                    Reload configuration
                </button>
            )}
        </PageHeader>
    );

    if (loading) {
        return (
            <div className="view-stack">
                {header}
                <Skeleton rows={5} label="Loading configuration…" />
            </div>
        );
    }

    if (loadError || !config) {
        return (
            <div className="view-stack">
                {header}
                <ErrorState
                    title="Unable to load configuration"
                    description={loadError || 'No configuration value was returned.'}
                    onRetry={loadConfig}
                />
            </div>
        );
    }

    const editablePresent = EDITABLE_KEYS.filter(key => hasKey(key));
    const preservedKeys = Object.entries(config).filter(([key]) => !EDITABLE_KEYS.includes(key));

    return (
        <div className="view-stack settings-layout">
            {header}

            {notice && <Notice tone="success">{notice}</Notice>}
            {actionError && <Notice tone="error">{actionError}</Notice>}

            <section className="panel">
                <SectionHeader
                    icon={Settings}
                    title="Business rules"
                    subtitle="Deterministic policy parameters evaluated by the server."
                />

                {editablePresent.length === 0 ? (
                    <p className="form-note">
                        The returned configuration does not expose any editable fields.
                    </p>
                ) : (
                    <form className="settings-form" onSubmit={handleSubmit}>
                        <div className="form-grid">
                            {hasKey('business_name') && (
                                <div className="field">
                                    <label className="field-label" htmlFor="config-business-name">Business name</label>
                                    <input
                                        id="config-business-name"
                                        type="text"
                                        maxLength={120}
                                        required
                                        className="field-input"
                                        value={config.business_name ?? ''}
                                        onChange={event => updateField('business_name', event.target.value)}
                                    />
                                    <span className="field-hint">Used in generated customer responses.</span>
                                </div>
                            )}

                            {hasKey('response_target_minutes') && (
                                <div className="field">
                                    <label className="field-label" htmlFor="config-response-target">Response target (minutes)</label>
                                    <input
                                        id="config-response-target"
                                        type="number"
                                        min={1}
                                        max={10080}
                                        step={1}
                                        required
                                        className="field-input"
                                        value={config.response_target_minutes ?? ''}
                                        onChange={event => updateField('response_target_minutes', event.target.value)}
                                    />
                                    <span className="field-hint">Leads unanswered beyond this window become at risk.</span>
                                </div>
                            )}

                            {hasKey('high_value_threshold') && (
                                <div className="field">
                                    <label className="field-label" htmlFor="config-high-value">High-value threshold</label>
                                    <input
                                        id="config-high-value"
                                        type="number"
                                        min={0}
                                        max={1_000_000_000_000_000}
                                        step={1}
                                        required
                                        className="field-input"
                                        value={config.high_value_threshold ?? ''}
                                        onChange={event => updateField('high_value_threshold', event.target.value)}
                                    />
                                    <span className="field-hint">Deals above this value score as high value.</span>
                                </div>
                            )}

                            {hasKey('supported_locations') && (
                                <div className="field">
                                    <label className="field-label" htmlFor="config-locations">Supported locations</label>
                                    <input
                                        id="config-locations"
                                        type="text"
                                        className="field-input"
                                        placeholder="Pune, Mumbai, Delhi"
                                        value={locationsText}
                                        onChange={event => setLocationsText(event.target.value)}
                                    />
                                    <span className="field-hint">Comma-separated list of serviceable locations.</span>
                                </div>
                            )}
                        </div>

                        <div className="form-actions">
                            <button type="submit" className="btn-primary" disabled={saving}>
                                {saving ? <BusyLabel>Saving…</BusyLabel> : <><Save size={16} aria-hidden="true" /> Save configuration</>}
                            </button>
                        </div>
                    </form>
                )}
            </section>

            {preservedKeys.length > 0 && (
                <section className="panel">
                    <SectionHeader
                        icon={ListChecks}
                        title="Other configuration keys"
                        subtitle="Read-only. These values are sent back unchanged when you save."
                    />
                    <dl className="config-list">
                        {preservedKeys.map(([key, value]) => (
                            <div className="config-row" key={key}>
                                <dt className="config-key">{humanize(key)}</dt>
                                <dd className="config-value">
                                    {SENSITIVE_KEY.test(key) ? '•••• (preserved)' : formatConfigValue(value)}
                                </dd>
                            </div>
                        ))}
                    </dl>
                </section>
            )}

            <section className="panel">
                <SectionHeader
                    icon={Server}
                    title="Runtime"
                    subtitle="Values reported by the running system."
                />
                <dl className="info-list">
                    <div className="info-row">
                        <dt className="info-label">API base URL</dt>
                        <dd className="info-value code-value">{API_BASE_URL}</dd>
                    </div>
                    {demoMode && <div className="info-row">
                        <dt className="info-label">Demo clock</dt>
                        <dd className="info-value">{clock?.effective_now ? dateTime(clock.effective_now) : 'Not available'}</dd>
                    </div>}
                    <div className="info-row">
                        <dt className="info-label">Configuration loaded</dt>
                        <dd className="info-value">{loadedAt ? dateTime(loadedAt) : 'Not available'}</dd>
                    </div>
                </dl>
            </section>

            <section className="panel design-note">
                <SectionHeader
                    icon={Info}
                    title="Architecture (design)"
                    subtitle="How the system is designed to behave — not a live health check."
                />
                <ul className="design-list">
                    <li><strong>AI understands</strong> — extracts intent and context and drafts a reply.</li>
                    <li><strong>Software decides</strong> — the deterministic policy engine owns score, priority, SLA and safeguards.</li>
                    <li><strong>Human approves</strong> — approval records an exact draft version. Delivery requires a separate operator action and is deployment-gated.</li>
                </ul>
            </section>
        </div>
    );
}
