import React, { useState } from 'react';
import { api } from '../../api/client';
import { safeError } from '../../api/presentation';
import { BusyLabel, Notice } from './UI';

const MAPPING_FIELDS = [
    { key: 'outcome', label: 'Sales outcome', required: true },
    { key: 'sales_value', label: 'Confirmed sales value' },
    { key: 'sales_currency', label: 'Sales currency' },
    { key: 'reason', label: 'Outcome reason' },
    { key: 'recorded_at', label: 'Outcome recorded time' },
];

export function ZohoOutcomeMapping({ status, onUpdated, onReconnect }) {
    const [fields, setFields] = useState([]);
    const [mapping, setMapping] = useState(status.outcome_field_mapping || {});
    const [loadingFields, setLoadingFields] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    const loadFields = async () => {
        setLoadingFields(true);
        setError('');
        setNotice('');
        try {
            const result = await api.getZohoOutcomeFields();
            setFields(Array.isArray(result?.fields) ? result.fields : []);
        } catch (reason) {
            setError(safeError(reason, 'Zoho field metadata could not be loaded.'));
        } finally {
            setLoadingFields(false);
        }
    };

    const updateField = (key, value) => {
        setMapping(current => {
            const next = { ...current };
            if (value) next[key] = value;
            else delete next[key];
            return next;
        });
    };

    const saveMapping = async enabled => {
        setSaving(true);
        setError('');
        setNotice('');
        try {
            const result = await api.updateZohoOutcomeMapping({
                enabled,
                ...(enabled ? { field_mapping: mapping } : {}),
            });
            onUpdated(result);
            setNotice(enabled ? 'Outcome mapping saved. New recorded outcomes will be written to the selected Zoho fields.' : 'Zoho outcome writeback is disabled. The mapping is saved for later use.');
        } catch (reason) {
            setError(safeError(reason, 'Zoho outcome mapping could not be saved.'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="zoho-outcome-mapping">
            <h4>Outcome writeback</h4>
            <p className="form-note">Choose writable custom fields in the connected Leads module. LeadRescue writes only recorded outcomes and the selected optional values.</p>
            {!status.field_metadata_scope_requested ? (
                <Notice tone="warning">
                    Reconnect Zoho to grant read-only access to Leads field metadata before configuring mappings.
                    <button type="button" className="btn-secondary" onClick={onReconnect}>Reconnect Zoho</button>
                </Notice>
            ) : (
                <>
                    <div className="integration-actions">
                        <button type="button" className="btn-secondary" onClick={loadFields} disabled={loadingFields || saving}>
                            {loadingFields ? <BusyLabel>Loading fields…</BusyLabel> : fields.length ? 'Refresh Zoho fields' : 'Load Zoho fields'}
                        </button>
                    </div>
                    {error && <Notice tone="error">{error}</Notice>}
                    {notice && <Notice>{notice}</Notice>}
                    {fields.length > 0 && (
                        <div className="form-grid">
                            {MAPPING_FIELDS.map(({ key, label, required }) => {
                                const options = fields.filter(field => field.eligible_for?.includes(key)
                                    && !Object.entries(mapping).some(([otherKey, apiName]) => otherKey !== key && apiName === field.api_name));
                                return (
                                    <label className="filter-field" key={key}>
                                        <span className="field-label">{label}{required ? ' (required)' : ' (optional)'}</span>
                                        <select
                                            className="field-input"
                                            value={mapping[key] || ''}
                                            onChange={event => updateField(key, event.target.value)}
                                            required={required}
                                            disabled={saving}
                                        >
                                            <option value="">{required ? 'Select a field' : 'Do not sync'}</option>
                                            {options.map(field => (
                                                <option value={field.api_name} key={field.api_name}>
                                                    {field.label} ({field.api_name} · {field.data_type})
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                );
                            })}
                        </div>
                    )}
                    {fields.length === 0 && !loadingFields && !error && (
                        <p className="form-note">Load fields to configure the mapping. If there are no choices for a value, create a compatible writable custom field in Zoho first.</p>
                    )}
                    {fields.length > 0 && (
                        <div className="integration-actions">
                            <button type="button" className="btn-primary" onClick={() => saveMapping(true)} disabled={saving || !mapping.outcome}>
                                {saving ? <BusyLabel>Saving…</BusyLabel> : 'Save and enable outcome writeback'}
                            </button>
                            {status.outcome_writeback_enabled && (
                                <button type="button" className="btn-secondary" onClick={() => saveMapping(false)} disabled={saving}>
                                    Disable outcome writeback
                                </button>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
