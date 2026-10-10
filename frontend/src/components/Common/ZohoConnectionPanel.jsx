import React, { useCallback, useEffect, useState } from 'react';
import { ExternalLink, Link2, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { safeError } from '../../api/presentation';
import { BusyLabel, Notice, SectionHeader } from './UI';

const ALLOWED_ACCOUNTS_HOSTS = new Set([
    'accounts.zoho.com',
    'accounts.zoho.com.au',
    'accounts.zoho.eu',
    'accounts.zoho.in',
    'accounts.zoho.com.cn',
    'accounts.zoho.jp',
    'accounts.zohocloud.ca',
]);

function validateAuthorizationUrl(value) {
    try {
        const url = new URL(value);
        return url.protocol === 'https:' && ALLOWED_ACCOUNTS_HOSTS.has(url.hostname);
    } catch {
        return false;
    }
}

export function ZohoConnectionPanel({ demoMode = false }) {
    const [status, setStatus] = useState(null);
    const [authorizationUrl, setAuthorizationUrl] = useState('');
    const [loading, setLoading] = useState(!demoMode);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    const loadStatus = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            setStatus(await api.getZohoConnectionStatus());
        } catch (reason) {
            setStatus(null);
            setError(safeError(reason, 'Zoho connection status is unavailable.'));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!demoMode) loadStatus();
    }, [demoMode, loadStatus]);

    const prepareAuthorization = async () => {
        setBusy(true);
        setError('');
        setNotice('');
        setAuthorizationUrl('');
        try {
            const result = await api.startZohoAuthorization();
            if (!validateAuthorizationUrl(result?.authorization_url)) {
                throw new Error('The server returned an unsupported Zoho authorization address.');
            }
            setAuthorizationUrl(result.authorization_url);
            setNotice('Authorization link is ready. It is single-use and expires after ten minutes.');
        } catch (reason) {
            setError(safeError(reason, 'Zoho authorization could not be started.'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="panel">
            <SectionHeader
                icon={Link2}
                title="Zoho CRM connection"
                subtitle="Authorize the selected Zoho organization for Lead record updates."
            />
            {demoMode ? (
                <Notice tone="warning">Zoho is disabled in the synthetic demo. No external account or data is contacted.</Notice>
            ) : (
                <div className="integration-connection">
                    {loading ? (
                        <p className="form-note" role="status">Checking saved connection configuration…</p>
                    ) : status ? (
                        <div className="integration-status" role="status">
                            <span className={`status-dot ${status.connection_status === 'configured' ? 'active' : ''}`} aria-hidden="true" />
                            <div>
                                <strong>{status.connection_status === 'configured' ? 'Authorization saved' : 'Not connected'}</strong>
                                <p>
                                    {status.connection_status === 'configured'
                                        ? `Zoho ${status.accounts_region || ''}${status.api_region ? ` · API ${status.api_region}` : ''}. Token validity is not checked here.`
                                        : 'Ask the deployment administrator to configure the Zoho OAuth secret before connecting.'}
                                </p>
                            </div>
                        </div>
                    ) : null}

                    {error && <Notice tone="error">{error}</Notice>}
                    {notice && <Notice>{notice}</Notice>}

                    <div className="integration-actions">
                        <button type="button" className="btn-secondary" onClick={loadStatus} disabled={loading || busy}>
                            <RefreshCw size={15} aria-hidden="true" /> Refresh status
                        </button>
                        <button type="button" className="btn-primary" onClick={prepareAuthorization} disabled={busy || loading || !status}>
                            {busy ? <BusyLabel>Preparing…</BusyLabel> : 'Connect or reconnect Zoho'}
                        </button>
                        {authorizationUrl && (
                            <a className="btn-secondary" href={authorizationUrl} target="_blank" rel="noopener noreferrer">
                                Continue to Zoho <ExternalLink size={15} aria-hidden="true" />
                            </a>
                        )}
                    </div>
                    <p className="field-hint">The OAuth grant requests update access to the Leads module. CRM outcome writeback is not enabled by this connection screen yet.</p>
                </div>
            )}
        </section>
    );
}
