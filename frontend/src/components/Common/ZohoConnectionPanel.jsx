import React, { useCallback, useEffect, useState } from 'react';
import { ExternalLink, Link2, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { safeError } from '../../api/presentation';
import { ZohoOutcomeMapping } from './ZohoOutcomeMapping';
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

    const disconnect = async () => {
        if (status?.connection_status === 'configured'
            && !window.confirm('Disconnect Zoho CRM? LeadRescue will stop using this connection and ask Zoho to revoke its authorization.')) return;
        setBusy(true);
        setError('');
        setNotice('');
        setAuthorizationUrl('');
        try {
            const result = await api.disconnectZoho();
            await loadStatus();
            setNotice(result?.provider_revocation === 'pending'
                ? 'Zoho access is disabled in LeadRescue. Zoho has not confirmed revocation yet; retry this action to complete revocation.'
                : 'Zoho is disconnected and its authorization has been revoked.');
        } catch (reason) {
            setError(safeError(reason, 'Zoho disconnection could not be completed.'));
        } finally {
            setBusy(false);
        }
    };

    const updateStatus = nextStatus => setStatus(current => ({ ...current, ...nextStatus }));

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
                                <strong>
                                    {status.connection_status === 'configured'
                                        ? 'Authorization saved'
                                        : status.connection_status === 'revocation_pending'
                                            ? 'Disconnected · revocation pending'
                                            : 'Not connected'}
                                </strong>
                                <p>
                                    {status.connection_status === 'configured'
                                        ? `Zoho ${status.accounts_region || ''}${status.api_region ? ` · API ${status.api_region}` : ''}. Token validity is not checked here. ${status.outcome_writeback_enabled ? 'Outcome writeback is enabled.' : 'Outcome writeback remains off until an administrator configures and enables the CRM field mapping.'}`
                                        : status.connection_status === 'revocation_pending'
                                            ? 'Local CRM access is disabled. Retry disconnection to ask Zoho to revoke the saved token.'
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
                        <button
                            type="button"
                            className="btn-primary"
                            onClick={prepareAuthorization}
                            disabled={busy || loading || !status || status.connection_status === 'revocation_pending'}
                        >
                            {busy ? <BusyLabel>Preparing…</BusyLabel> : 'Connect or reconnect Zoho'}
                        </button>
                        {(status?.connection_status === 'configured' || status?.connection_status === 'revocation_pending') && (
                            <button type="button" className="btn-secondary" onClick={disconnect} disabled={busy || loading}>
                                {busy ? <BusyLabel>Disconnecting…</BusyLabel> : status.connection_status === 'revocation_pending' ? 'Retry revocation' : 'Disconnect Zoho'}
                            </button>
                        )}
                        {authorizationUrl && (
                            <a className="btn-secondary" href={authorizationUrl} target="_blank" rel="noopener noreferrer">
                                Continue to Zoho <ExternalLink size={15} aria-hidden="true" />
                            </a>
                        )}
                    </div>
                    {status?.connection_status === 'configured' && (
                        <ZohoOutcomeMapping
                            status={status}
                            onUpdated={updateStatus}
                            onReconnect={prepareAuthorization}
                        />
                    )}
                    <p className="field-hint">The OAuth grant requests read and update access to Leads and read-only access to field metadata. Configure outcome writeback with the field mapper below.</p>
                </div>
            )}
        </section>
    );
}
