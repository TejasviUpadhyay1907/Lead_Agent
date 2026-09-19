import React, { useState } from 'react';
import { Search, Filter, Plus, Sparkles, ChevronRight, User, AlertTriangle } from 'lucide-react';
import { PriorityBadge, RiskBadge, LifecycleBadge } from '../components/Common/Badge';

export function LeadInboxView({ leads, onSelectLead, onAnalyzeLead, onCreateLead }) {
    const [searchTerm, setSearchTerm] = useState('');
    const [priorityFilter, setPriorityFilter] = useState('all');
    const [riskFilter, setRiskFilter] = useState('all');
    const [lifecycleFilter, setLifecycleFilter] = useState('all');
    const [sourceFilter, setSourceFilter] = useState('all');

    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newLead, setNewLead] = useState({
        customer_name: '',
        customer_email: '',
        customer_phone: '',
        source: 'whatsapp',
        raw_message: '',
    });
    const [submitting, setSubmitting] = useState(false);

    // Filter leads
    const filteredLeads = leads.filter((lead) => {
        // Search
        const searchLower = searchTerm.toLowerCase();
        const matchSearch =
            !searchTerm ||
            lead.customer_name?.toLowerCase().includes(searchLower) ||
            lead.raw_message?.toLowerCase().includes(searchLower) ||
            lead.product?.toLowerCase().includes(searchLower) ||
            lead.location?.toLowerCase().includes(searchLower);

        // Priority filter
        const matchPriority =
            priorityFilter === 'all' || (lead.priority && lead.priority.toLowerCase() === priorityFilter);

        // Risk filter
        const matchRisk =
            riskFilter === 'all' || (lead.risk_status && lead.risk_status.toLowerCase() === riskFilter);

        // Lifecycle filter
        const matchLifecycle =
            lifecycleFilter === 'all' || (lead.lifecycle_status && lead.lifecycle_status.toLowerCase() === lifecycleFilter);

        // Source filter
        const matchSource =
            sourceFilter === 'all' || (lead.source && lead.source.toLowerCase() === sourceFilter);

        return matchSearch && matchPriority && matchRisk && matchLifecycle && matchSource;
    });

    const handleCreateSubmit = async (e) => {
        e.preventDefault();
        if (!newLead.customer_name || !newLead.raw_message) {
            alert('Customer Name and Raw Message are required.');
            return;
        }
        setSubmitting(true);
        try {
            await onCreateLead(newLead);
            setShowCreateModal(false);
            setNewLead({
                customer_name: '',
                customer_email: '',
                customer_phone: '',
                source: 'whatsapp',
                raw_message: '',
            });
        } catch (err) {
            alert(`Failed to create lead: ${err.message}`);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Header & New Lead Button */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.2rem' }}>Lead Inbox</h2>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                        Search, filter, and manage incoming operational lead inquiries.
                    </p>
                </div>

                <button onClick={() => setShowCreateModal(true)} className="btn-primary">
                    <Plus size={16} /> New Lead Entry
                </button>
            </div>

            {/* Filter Bar */}
            <div className="panel" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>

                    {/* Search Box */}
                    <div style={{
                        flex: 1,
                        minWidth: '240px',
                        position: 'relative',
                        display: 'flex',
                        alignItems: 'center',
                    }}>
                        <Search size={16} color="var(--text-dim)" style={{ position: 'absolute', left: '12px' }} />
                        <input
                            type="text"
                            placeholder="Search customer, message, product..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                width: '100%',
                                padding: '0.55rem 0.75rem 0.55rem 2.2rem',
                                borderRadius: 'var(--radius-sm)',
                                background: 'var(--bg-dark-0)',
                                border: '1px solid var(--border-color)',
                                color: 'var(--text-main)',
                                fontSize: '0.875rem',
                            }}
                        />
                    </div>

                    {/* Priority Filter */}
                    <select
                        value={priorityFilter}
                        onChange={(e) => setPriorityFilter(e.target.value)}
                        style={{
                            padding: '0.55rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--bg-dark-0)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-main)',
                            fontSize: '0.85rem',
                        }}
                    >
                        <option value="all">Priority: All</option>
                        <option value="hot">HOT (80-100)</option>
                        <option value="warm">WARM (50-79)</option>
                        <option value="cold">COLD (0-49)</option>
                    </select>

                    {/* Risk Filter */}
                    <select
                        value={riskFilter}
                        onChange={(e) => setRiskFilter(e.target.value)}
                        style={{
                            padding: '0.55rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--bg-dark-0)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-main)',
                            fontSize: '0.85rem',
                        }}
                    >
                        <option value="all">Risk: All</option>
                        <option value="at_risk">AT RISK SLA</option>
                        <option value="normal">NORMAL</option>
                    </select>

                    {/* Lifecycle Filter */}
                    <select
                        value={lifecycleFilter}
                        onChange={(e) => setLifecycleFilter(e.target.value)}
                        style={{
                            padding: '0.55rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--bg-dark-0)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-main)',
                            fontSize: '0.85rem',
                        }}
                    >
                        <option value="all">Lifecycle: All</option>
                        <option value="new">NEW</option>
                        <option value="analyzed">ANALYZED</option>
                        <option value="contacted">CONTACTED</option>
                        <option value="follow_up">FOLLOW-UP</option>
                        <option value="resolved">RESOLVED</option>
                        <option value="opted_out">OPTED OUT</option>
                    </select>

                    {/* Source Filter */}
                    <select
                        value={sourceFilter}
                        onChange={(e) => setSourceFilter(e.target.value)}
                        style={{
                            padding: '0.55rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--bg-dark-0)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-main)',
                            fontSize: '0.85rem',
                        }}
                    >
                        <option value="all">Source: All</option>
                        <option value="whatsapp">WhatsApp</option>
                        <option value="website">Website</option>
                        <option value="email">Email</option>
                        <option value="phone">Phone</option>
                        <option value="marketplace">Marketplace</option>
                        <option value="manual">Manual</option>
                    </select>

                </div>
            </div>

            {/* Leads Data Table */}
            <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                {filteredLeads.length === 0 ? (
                    <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        <p style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>No leads match these filters.</p>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                            Try clearing filters or search query to view all available leads.
                        </span>
                    </div>
                ) : (
                    <div className="data-table-container">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Customer</th>
                                    <th>Source</th>
                                    <th>Message / Intent</th>
                                    <th>Score</th>
                                    <th>Priority</th>
                                    <th>Risk</th>
                                    <th>Lifecycle</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredLeads.map((lead) => (
                                    <tr
                                        key={lead.lead_id}
                                        onClick={() => onSelectLead(lead.lead_id)}
                                        style={{ cursor: 'pointer' }}
                                    >
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                                                <div style={{
                                                    width: '32px',
                                                    height: '32px',
                                                    borderRadius: '50%',
                                                    background: 'var(--bg-dark-2)',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    fontWeight: 600,
                                                    fontSize: '0.85rem',
                                                }}>
                                                    {lead.customer_name ? lead.customer_name.charAt(0) : <User size={14} />}
                                                </div>
                                                <div>
                                                    <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{lead.customer_name}</div>
                                                    <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{lead.customer_email || lead.customer_phone || 'No contact'}</span>
                                                </div>
                                            </div>
                                        </td>

                                        <td>
                                            <span className="badge-sub">{lead.source?.toUpperCase()}</span>
                                        </td>

                                        <td style={{ maxWidth: '300px' }}>
                                            <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', margin: 0 }}>
                                                {lead.raw_message}
                                            </p>
                                            {lead.intent && (
                                                <span style={{ fontSize: '0.7rem', color: 'var(--accent-primary)', fontWeight: 500 }}>
                                                    Intent: {lead.intent}
                                                </span>
                                            )}
                                        </td>

                                        <td>
                                            {lead.score !== null ? (
                                                <span style={{ fontWeight: 700, fontFamily: 'var(--font-heading)', color: 'var(--accent-primary)', fontSize: '1rem' }}>
                                                    {lead.score}
                                                </span>
                                            ) : (
                                                <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>—</span>
                                            )}
                                        </td>

                                        <td>
                                            <PriorityBadge priority={lead.priority} />
                                        </td>

                                        <td>
                                            <RiskBadge risk={lead.risk_status} />
                                        </td>

                                        <td>
                                            <LifecycleBadge status={lead.lifecycle_status} />
                                        </td>

                                        <td>
                                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                {lead.lifecycle_status === 'new' ? (
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); onAnalyzeLead(lead.lead_id); }}
                                                        className="btn-primary"
                                                        style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
                                                    >
                                                        <Sparkles size={12} /> Analyze
                                                    </button>
                                                ) : (
                                                    <button className="btn-secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}>
                                                        View Detail
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* New Lead Entry Modal */}
            {showCreateModal && (
                <div style={{
                    position: 'fixed',
                    top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0, 0, 0, 0.7)',
                    backdropFilter: 'blur(4px)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000,
                }}>
                    <div className="panel" style={{ width: '100%', maxWidth: '500px', background: 'var(--bg-dark-1)' }}>
                        <div className="panel-header">
                            <div className="panel-title">Create New Lead Entry</div>
                            <button onClick={() => setShowCreateModal(false)} style={{ color: 'var(--text-muted)' }}>✕</button>
                        </div>

                        <form onSubmit={handleCreateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
                                    Customer Name *
                                </label>
                                <input
                                    type="text"
                                    required
                                    placeholder="e.g. Ramesh Chandra"
                                    value={newLead.customer_name}
                                    onChange={(e) => setNewLead({ ...newLead, customer_name: e.target.value })}
                                    style={{
                                        width: '100%',
                                        padding: '0.6rem',
                                        borderRadius: 'var(--radius-sm)',
                                        background: 'var(--bg-dark-0)',
                                        border: '1px solid var(--border-color)',
                                        color: 'var(--text-main)',
                                    }}
                                />
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <div>
                                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
                                        Email Address
                                    </label>
                                    <input
                                        type="email"
                                        placeholder="ramesh@example.com"
                                        value={newLead.customer_email}
                                        onChange={(e) => setNewLead({ ...newLead, customer_email: e.target.value })}
                                        style={{
                                            width: '100%',
                                            padding: '0.6rem',
                                            borderRadius: 'var(--radius-sm)',
                                            background: 'var(--bg-dark-0)',
                                            border: '1px solid var(--border-color)',
                                            color: 'var(--text-main)',
                                        }}
                                    />
                                </div>

                                <div>
                                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
                                        Phone Number
                                    </label>
                                    <input
                                        type="text"
                                        placeholder="+91-9876543210"
                                        value={newLead.customer_phone}
                                        onChange={(e) => setNewLead({ ...newLead, customer_phone: e.target.value })}
                                        style={{
                                            width: '100%',
                                            padding: '0.6rem',
                                            borderRadius: 'var(--radius-sm)',
                                            background: 'var(--bg-dark-0)',
                                            border: '1px solid var(--border-color)',
                                            color: 'var(--text-main)',
                                        }}
                                    />
                                </div>
                            </div>

                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
                                    Channel Source
                                </label>
                                <select
                                    value={newLead.source}
                                    onChange={(e) => setNewLead({ ...newLead, source: e.target.value })}
                                    style={{
                                        width: '100%',
                                        padding: '0.6rem',
                                        borderRadius: 'var(--radius-sm)',
                                        background: 'var(--bg-dark-0)',
                                        border: '1px solid var(--border-color)',
                                        color: 'var(--text-main)',
                                    }}
                                >
                                    <option value="whatsapp">WhatsApp</option>
                                    <option value="website">Website</option>
                                    <option value="email">Email</option>
                                    <option value="phone">Phone</option>
                                    <option value="marketplace">Marketplace</option>
                                    <option value="manual">Manual</option>
                                </select>
                            </div>

                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
                                    Raw Customer Message *
                                </label>
                                <textarea
                                    rows={3}
                                    required
                                    placeholder="Paste incoming lead message text..."
                                    value={newLead.raw_message}
                                    onChange={(e) => setNewLead({ ...newLead, raw_message: e.target.value })}
                                    style={{
                                        width: '100%',
                                        padding: '0.6rem',
                                        borderRadius: 'var(--radius-sm)',
                                        background: 'var(--bg-dark-0)',
                                        border: '1px solid var(--border-color)',
                                        color: 'var(--text-main)',
                                        resize: 'vertical',
                                    }}
                                />
                            </div>

                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                                <button type="button" onClick={() => setShowCreateModal(false)} className="btn-secondary">
                                    Cancel
                                </button>
                                <button type="submit" disabled={submitting} className="btn-primary">
                                    {submitting ? 'Creating...' : 'Create Lead'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
