/**
 * LeadRescue AI — API Client Layer
 * Centralized fetch wrapper interacting with FastAPI backend.
 */

import { getAccessToken } from '../auth/oidc';
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function request(endpoint, options = {}, withMetadata = false) {
    const url = `${API_BASE_URL}${endpoint}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), endpoint.endsWith('/analyze') ? 90000 : 20000);
    try {
        const token = getAccessToken();
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
            headers: { ...options.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
        });
        if (!response.ok) {
            if (response.status === 401) window.dispatchEvent(new Event('leadrescue-auth-expired'));
            const error = new Error(`Request failed (${response.status})`);
            error.status = response.status;
            throw error;
        }
        if (response.status === 204) return null;
        const body = await response.json();
        return withMetadata ? { items: body, nextCursor: response.headers.get('X-Next-Cursor') || null } : body;
    } finally {
        clearTimeout(timeout);
    }
}

export const api = {
    // Leads
    getLeadsPage: (params = {}) => {
        const query = new URLSearchParams({ limit: '50' });
        if (params.cursor) query.set('cursor', params.cursor);
        return request(`/leads?${query}`, {}, true);
    },
    getLeads: (params = {}) => {
        const query = new URLSearchParams();
        if (params.lifecycle_status) query.append('lifecycle_status', params.lifecycle_status);
        if (params.priority) query.append('priority', params.priority);
        if (params.risk_status) query.append('risk_status', params.risk_status);
        if (params.source) query.append('source', params.source);
        const queryString = query.toString() ? `?${query.toString()}` : '';
        return request(`/leads${queryString}`);
    },

    getLead: (id) => request(`/leads/${id}`),

    exportLeadData: async (id) => {
        const token = getAccessToken();
        const response = await fetch(`${API_BASE_URL}/privacy/leads/${encodeURIComponent(id)}/export`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            cache: 'no-store',
        });
        if (!response.ok) {
            if (response.status === 401) window.dispatchEvent(new Event('leadrescue-auth-expired'));
            const error = new Error(`Request failed (${response.status})`);
            error.status = response.status;
            throw error;
        }
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const download = document.createElement('a');
        download.href = objectUrl;
        download.download = `lead-${id.slice(0, 80).replace(/[^A-Za-z0-9_-]/g, '_')}-export.json`;
        document.body.appendChild(download);
        download.click();
        download.remove();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    },

    getPrivacyRequestsPage: (params = {}) => {
        const query = new URLSearchParams({ limit: '50' });
        if (params.cursor) query.set('cursor', params.cursor);
        if (params.status) query.set('status', params.status);
        return request(`/privacy/requests?${query}`, {}, true);
    },

    getPrivacyRequestRecordsPage: (id, params = {}) => {
        const query = new URLSearchParams({ match: params.match, limit: String(params.limit || 50) });
        if (params.cursor) query.set('cursor', params.cursor);
        return request(`/privacy/requests/${encodeURIComponent(id)}/records?${query}`, {}, true);
    },

    updatePrivacyRequestStatus: (id, status, resolutionCode) => request(`/privacy/requests/${encodeURIComponent(id)}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status, resolution_code: resolutionCode || null }),
    }),

    createLead: (leadData) => request('/leads', {
        method: 'POST',
        body: JSON.stringify(leadData),
    }),

    analyzeLead: async (id) => {
        const storageKey = `leadrescue.analysis-job.${id}`;
        const requestKeyStorage = `${storageKey}.request`;
        let requestKey = sessionStorage.getItem(requestKeyStorage);
        if (!requestKey) {
            requestKey = crypto.randomUUID();
            sessionStorage.setItem(requestKeyStorage, requestKey);
        }
        let jobId = sessionStorage.getItem(storageKey);
        let job;
        if (jobId) {
            try {
                job = await request(`/leads/analysis-jobs/${encodeURIComponent(jobId)}`);
            } catch (error) {
                if (error.status !== 404) throw error;
                sessionStorage.removeItem(storageKey);
                jobId = null;
            }
        }
        if (!jobId) {
            job = await request(`/leads/${encodeURIComponent(id)}/analysis-jobs`, {
                method: 'POST',
                headers: { 'Idempotency-Key': requestKey },
            });
            if (job.result) {
                sessionStorage.removeItem(requestKeyStorage);
                return job.result;
            }
            jobId = job.job_id;
            sessionStorage.setItem(storageKey, jobId);
        }
        const deadline = Date.now() + 10 * 60 * 1000;
        while (Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            const current = await request(`/leads/analysis-jobs/${encodeURIComponent(jobId)}`);
            if (current.status === 'SUCCEEDED') {
                const lead = await request(`/leads/${encodeURIComponent(id)}`);
                sessionStorage.removeItem(storageKey);
                sessionStorage.removeItem(requestKeyStorage);
                return lead;
            }
            if (current.status === 'FAILED') {
                sessionStorage.removeItem(storageKey);
                sessionStorage.removeItem(requestKeyStorage);
                const error = new Error('Lead analysis could not be completed. You can safely retry.');
                error.status = 503;
                throw error;
            }
        }
        const error = new Error('Analysis is still queued. Refresh the lead before trying again.');
        error.status = 504;
        throw error;
    },

    respondToLead: (id, action, editedDraft) => request(`/leads/${id}/response`, {
        method: 'PUT',
        body: JSON.stringify({ action, edited_draft: editedDraft }),
    }),

    rescueLead: (id) => request(`/leads/${id}/rescue`, {
        method: 'POST',
    }),

    updateLeadStatus: (id, lifecycleStatus, reason) => request(`/leads/${id}/status`, {
        method: 'PUT',
        body: JSON.stringify({ lifecycle_status: lifecycleStatus, reason }),
    }),

    // Follow-ups
    getFollowupsPage: (params = {}) => {
        const query = new URLSearchParams({ limit: '50' });
        if (params.cursor) query.set('cursor', params.cursor);
        return request(`/followups?${query}`, {}, true);
    },
    getFollowups: (params = {}) => {
        const query = new URLSearchParams();
        if (params.lead_id) query.append('lead_id', params.lead_id);
        if (params.status) query.append('status', params.status);
        const queryString = query.toString() ? `?${query.toString()}` : '';
        return request(`/followups${queryString}`);
    },

    updateFollowup: (id, status, notes) => request(`/followups/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status, notes }),
    }),

    // Audit
    getAudit: (id, cursor) => {
        const query = new URLSearchParams({ limit: '50' });
        if (cursor) query.set('cursor', cursor);
        return request(`/leads/${id}/audit?${query}`, {}, true);
    },

    // Config
    getConfig: () => request('/config'),

    updateConfig: (configValue) => request('/config', {
        method: 'PUT',
        body: JSON.stringify({ config_value: configValue }),
    }),

    // Demo Controls
    getServerTime: () => request('/server-time'),
    getDemoClock: () => request('/demo/clock'),

    advanceDemoTime: (minutes = 20) => request('/demo/advance-time', {
        method: 'POST',
        body: JSON.stringify({ minutes }),
    }),

    resetDemoClock: () => request('/demo/reset', {
        method: 'POST',
    }),

    seedDemoLeads: () => request('/demo/seed', {
        method: 'POST',
    }),
};
