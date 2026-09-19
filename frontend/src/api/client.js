/**
 * LeadRescue AI — API Client Layer
 * Centralized fetch wrapper interacting with FastAPI backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

async function request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    };

    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'HTTP Request Failed' }));
            throw new Error(errorData.detail || `Error ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
}

export const api = {
    // Leads
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

    createLead: (leadData) => request('/leads', {
        method: 'POST',
        body: JSON.stringify(leadData),
    }),

    analyzeLead: (id) => request(`/leads/${id}/analyze`, {
        method: 'POST',
    }),

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
    getAudit: (id) => request(`/leads/${id}/audit`),

    // Config
    getConfig: () => request('/config'),

    updateConfig: (configValue) => request('/config', {
        method: 'PUT',
        body: JSON.stringify({ config_value: configValue }),
    }),

    // Demo Controls
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
