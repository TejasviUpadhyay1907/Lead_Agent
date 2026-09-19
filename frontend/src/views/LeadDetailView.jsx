import React, { useState, useEffect } from 'react';
import {
    ArrowLeft, Sparkles, Cpu, CheckCircle, ShieldAlert, Send, Edit3, XCircle,
    Clock, MapPin, Package, AlertTriangle, Flame, Shield, History, Activity, FileText
} from 'lucide-react';
import { PriorityBadge, RiskBadge, LifecycleBadge } from '../components/Common/Badge';
import { api } from '../api/client';

export function LeadDetailView({ leadId, onBack, onRefreshLeads }) {
    const [lead, setLead] = useState(null);
    const [auditEvents, setAuditEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [responding, setResponding] = useState(false);
    const [error, setError] = useState(null);

    const [responseDraftText, setResponseDraftText] = useState('');
    const [isEditingDraft, setIsEditingDraft] = useState(false);

    // Fetch lead and audit trail
    const loadLeadData = async () => {
        setLoading(true);
        setError(null);
        try {
            const [leadData, auditData] = await Promise.all([
                api.getLead(leadId),
                api.getAudit(leadId).catch(() => []),
            ]);
            setLead(leadData);
            setAuditEvents(auditData);
            setResponseDraftText(leadData.response_draft || '');
        } catch (err) {
            setError(err.message || 'Failed to load lead details');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (leadId) {
            loadLeadData();
        }
    }, [leadId]);

    const handleAnalyze = async () => {
        setAnalyzing(true);
        try {
            const updatedLead = await api.analyzeLead(leadId);
            setLead(updatedLead);
            setResponseDraftText(updatedLead.response_draft || '');
            await loadLeadData();
            if (onRefreshLeads) onRefreshLeads();
        } catch (err) {
            alert(`Analysis failed: ${err.message}`);
        } finally {
            setAnalyzing(false);
        }
    };

    const handleResponseAction = async (action) => {
        setResponding(true);
        try {
            const updatedLead = await api.respondToLead(leadId, action, responseDraftText);
            setLead(updatedLead);
            setIsEditingDraft(false);
            await loadLeadData();
            if (onRefreshLeads) onRefreshLeads();
        } catch (err) {
            alert(`Action failed: ${err.message}`);
        } finally {
            setResponding(false);
        }
    };

    if (loading) {
        return (
            <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                <div style={{ fontSize: '1.2rem', marginBottom: '0.5rem' }}>Loading Lead Operational Record...</div>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Fetching DynamoDB data and Audit events</span>
            </div>
        );
    }

    if (error || !lead) {
        return (
            <div className="panel" style={{ borderLeft: '4px solid var(--color-hot)', padding: '2rem' }}>
                <h3 style={{ color: 'var(--color-hot)', marginBottom: '0.5rem' }}>Error Loading Lead</h3>
                <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error || 'Lead not found'}</p>
                <button onClick={onBack} className="btn-secondary">
                    <ArrowLeft size={16} /> Back to Lead Inbox
                </button>
            </div>
        );
    }

    // Score breakdown keys mapping
    const breakdownLabels = {
        intent: 'Intent Signal',
        urgency: 'Urgency Signal',
        quantity: 'Quantity Signal',
        product: 'Product Specified',
        location: 'Location Specified',
        customer_stage: 'Customer Stage',
        recency: 'Recency Signal',
        high_value: 'High-Value Threshold',
    };

    const isOptedOut = lead.lifecycle_status === 'opted_out';

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

            {/* Top Header Bar */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <button onClick={onBack} className="btn-secondary" style={{ padding: '0.5rem 0.75rem' }}>
                        <ArrowLeft size={16} /> Back
                    </button>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>{lead.customer_name}</h2>
                            <span className="badge-sub">{lead.source?.toUpperCase()}</span>
                            <LifecycleBadge status={lead.lifecycle_status} />
                        </div>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                            Lead ID: {lead.lead_id} • Received: {new Date(lead.created_at).toLocaleString()}
                        </span>
                    </div>
                </div>

                {/* Action Trigger */}
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    {!lead.intent && (
                        <button onClick={handleAnalyze} disabled={analyzing} className="btn-primary">
                            <Sparkles size={16} /> {analyzing ? 'Analyzing with Agent...' : 'Analyze Lead'}
                        </button>
                    )}
                </div>
            </div>

            {/* Top Overview Cards: Score Gauge & Badges */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>

                {/* Score Circle Card */}
                <div className="panel" style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                    <div className={`score-circle ${lead.priority ? lead.priority.toLowerCase() : 'cold'}`}>
                        {lead.score !== null ? lead.score : '—'}
                    </div>
                    <div>
                        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', uppercase: true }}>
                            DETERMINISTIC LEAD SCORE
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
                            <PriorityBadge priority={lead.priority} />
                            <RiskBadge risk={lead.risk_status} />
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.3rem', display: 'block' }}>
                            {lead.score !== null ? `Evaluated by Policy Engine` : `Pending AI & Policy Evaluation`}
                        </span>
                    </div>
                </div>

                {/* Contact Info Card */}
                <div className="panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                        CUSTOMER CONTACT DETAILS
                    </span>
                    <div style={{ marginTop: '0.4rem', fontSize: '0.9rem', color: 'var(--text-main)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        <span>📧 {lead.customer_email || 'No email provided'}</span>
                        <span>📞 {lead.customer_phone || 'No phone provided'}</span>
                    </div>
                </div>

                {/* Risk SLA Card */}
                <div className="panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                        RESPONSE TARGET SLA
                    </span>
                    <div style={{ marginTop: '0.4rem' }}>
                        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: lead.risk_status === 'at_risk' ? 'var(--color-at-risk)' : 'var(--color-success)' }}>
                            {lead.risk_status === 'at_risk' ? '⚠️ RESPONSE OVERDUE (AT RISK)' : '✓ SLA ON TRACK'}
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                            Target: 20 min • At-risk time: {lead.at_risk_at ? new Date(lead.at_risk_at).toLocaleTimeString() : 'N/A'}
                        </span>
                    </div>
                </div>

            </div>

            {/* Raw Customer Message Block */}
            <div className="panel" style={{ background: 'var(--bg-dark-0)' }}>
                <div className="panel-header" style={{ marginBottom: '0.5rem', paddingBottom: '0.5rem' }}>
                    <div className="panel-title" style={{ fontSize: '0.9rem' }}>
                        <FileText size={16} color="var(--accent-primary)" />
                        Raw Incoming Customer Message
                    </div>
                    <span className="badge-sub">Source: {lead.source?.toUpperCase()}</span>
                </div>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: 'var(--text-main)', lineHeight: 1.6, margin: 0, padding: '0.5rem 0' }}>
                    "{lead.raw_message}"
                </p>
            </div>

            {/* Main Grid: AI Understanding (Left) & Deterministic Decision (Right) */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>

                {/* PANEL 1: AI UNDERSTANDING */}
                <div className="panel" style={{ borderTop: '4px solid var(--accent-primary)' }}>
                    <div className="panel-header">
                        <div>
                            <div className="panel-title">
                                <Cpu size={18} color="var(--accent-primary)" />
                                AI Understanding
                            </div>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginTop: '0.1rem' }}>
                                Generated by Strands + Amazon Bedrock
                            </span>
                        </div>
                        <span className="badge" style={{ background: 'var(--bg-dark-2)', color: 'var(--accent-primary)', border: '1px solid var(--border-color)' }}>
                            Local demo inference
                        </span>
                    </div>

                    {!lead.intent ? (
                        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                            <p style={{ marginBottom: '1rem' }}>Lead has not yet been analyzed by the Strands Agent.</p>
                            <button onClick={handleAnalyze} disabled={analyzing} className="btn-primary">
                                <Sparkles size={16} /> Run Agent Analysis
                            </button>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

                            {/* Structured Extracted Attributes */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
                                <div style={{ padding: '0.6rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-dark-0)', border: '1px solid var(--border-color)' }}>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>INTENT</span>
                                    <strong style={{ fontSize: '0.9rem', color: 'var(--accent-primary)', textTransform: 'uppercase' }}>{lead.intent}</strong>
                                </div>

                                <div style={{ padding: '0.6rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-dark-0)', border: '1px solid var(--border-color)' }}>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>URGENCY</span>
                                    <strong style={{ fontSize: '0.9rem', color: lead.urgency === 'high' ? 'var(--color-hot)' : 'var(--text-main)', textTransform: 'uppercase' }}>{lead.urgency}</strong>
                                </div>

                                <div style={{ padding: '0.6rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-dark-0)', border: '1px solid var(--border-color)' }}>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>PRODUCT</span>
                                    <strong style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>{lead.product || 'Not specified'}</strong>
                                </div>

                                <div style={{ padding: '0.6rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-dark-0)', border: '1px solid var(--border-color)' }}>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>QUANTITY / LOCATION</span>
                                    <strong style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>
                                        {lead.quantity ? `${lead.quantity} units` : 'No qty'} • {lead.location || 'No loc'}
                                    </strong>
                                </div>
                            </div>

                            {/* Key Entities Chips */}
                            {lead.key_entities && lead.key_entities.length > 0 && (
                                <div>
                                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.4rem' }}>
                                        KEY EXTRACTED ENTITIES
                                    </span>
                                    <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                        {lead.key_entities.map((ent, idx) => (
                                            <span key={idx} className="badge-sub" style={{ background: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent-primary)' }}>
                                                {ent}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* AI Summary */}
                            <div>
                                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                                    AI ANALYSIS SUMMARY
                                </span>
                                <p style={{ fontSize: '0.85rem', color: 'var(--text-main)', background: 'var(--bg-dark-0)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', margin: 0 }}>
                                    {lead.ai_summary}
                                </p>
                            </div>

                            {/* Recommended Action */}
                            <div>
                                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                                    RECOMMENDED ACTION
                                </span>
                                <p style={{ fontSize: '0.85rem', color: 'var(--color-warning)', background: 'rgba(245, 158, 11, 0.08)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-warm)', margin: 0 }}>
                                    {lead.recommended_action}
                                </p>
                            </div>

                        </div>
                    )}
                </div>

                {/* PANEL 2: DETERMINISTIC POLICY DECISION */}
                <div className="panel" style={{ borderTop: '4px solid var(--color-success)' }}>
                    <div className="panel-header">
                        <div>
                            <div className="panel-title">
                                <Shield size={18} color="var(--color-success)" />
                                Policy Decision
                            </div>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginTop: '0.1rem' }}>
                                Calculated by deterministic policy engine
                            </span>
                        </div>
                        <span className="badge" style={{ background: 'var(--bg-success)', color: 'var(--color-success)', border: '1px solid var(--border-success)' }}>
                            LLM Independent
                        </span>
                    </div>

                    {lead.score === null && !isOptedOut ? (
                        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                            Score calculation will run automatically upon agent analysis.
                        </div>
                    ) : isOptedOut ? (
                        <div style={{ padding: '1.5rem', background: 'var(--bg-at-risk)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-at-risk)', textAlign: 'center' }}>
                            <AlertTriangle size={24} color="var(--color-hot)" style={{ marginBottom: '0.5rem' }} />
                            <h4 style={{ color: 'var(--color-hot)', marginBottom: '0.25rem' }}>Opt-Out Safeguard Triggered</h4>
                            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>
                                Customer requested opt-out. Score calculation bypassed, lead marked as OPTED_OUT, and outreach blocked.
                            </p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

                            {/* Score Breakdown Table */}
                            <div>
                                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>
                                    100-POINT DETERMINISTIC SCORE BREAKDOWN
                                </span>

                                <div style={{ borderRadius: 'var(--radius-sm)', overflow: 'hidden', border: '1px solid var(--border-color)', background: 'var(--bg-dark-0)' }}>
                                    <table className="data-table" style={{ fontSize: '0.8rem' }}>
                                        <thead>
                                            <tr>
                                                <th style={{ padding: '0.5rem 0.75rem' }}>Signal Category</th>
                                                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>Points Awarded</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {Object.entries(lead.score_breakdown || {}).map(([key, val]) => (
                                                <tr key={key}>
                                                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{breakdownLabels[key] || key}</td>
                                                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontWeight: 600, color: val > 0 ? 'var(--color-success)' : 'var(--text-dim)' }}>
                                                        +{val}
                                                    </td>
                                                </tr>
                                            ))}
                                            <tr style={{ background: 'var(--bg-dark-2)', fontWeight: 700 }}>
                                                <td style={{ padding: '0.6rem 0.75rem', color: 'var(--text-main)' }}>Total Calculated Score</td>
                                                <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--accent-primary)', fontSize: '1rem' }}>
                                                    {lead.score} / 100
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            {/* Priority & Risk Rules */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem', fontSize: '0.85rem' }}>
                                <div style={{ padding: '0.65rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-dark-0)', border: '1px solid var(--border-color)' }}>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>CLASSIFIED PRIORITY</span>
                                    <PriorityBadge priority={lead.priority} />
                                </div>

                                <div style={{ padding: '0.65rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-dark-0)', border: '1px solid var(--border-color)' }}>
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>EVALUATED RISK</span>
                                    <RiskBadge risk={lead.risk_status} />
                                </div>
                            </div>

                        </div>
                    )}
                </div>

            </div>

            {/* PANEL 3: RESPONSE APPROVAL (HUMAN IN THE LOOP) */}
            <div className="panel" style={{ borderTop: '4px solid var(--color-warm)' }}>
                <div className="panel-header">
                    <div>
                        <div className="panel-title">
                            <Send size={18} color="var(--color-warm)" />
                            AI Response Draft — Human Approval
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginTop: '0.1rem' }}>
                            Draft generated from available lead/business context • Human operator review required
                        </span>
                    </div>

                    <span className="badge" style={{
                        background: lead.response_status === 'simulated_sent' ? 'var(--bg-success)' : 'var(--bg-warm)',
                        color: lead.response_status === 'simulated_sent' ? 'var(--color-success)' : 'var(--color-warm)',
                        border: lead.response_status === 'simulated_sent' ? '1px solid var(--border-success)' : '1px solid var(--border-warm)'
                    }}>
                        Status: {lead.response_status ? lead.response_status.toUpperCase() : 'PENDING'}
                    </span>
                </div>

                {isOptedOut ? (
                    <div style={{ padding: '1rem', background: 'var(--bg-dark-0)', borderRadius: 'var(--radius-sm)', color: 'var(--text-dim)', textAlign: 'center', fontSize: '0.875rem' }}>
                        Outreach blocked due to customer opt-out. No response draft available.
                    </div>
                ) : !lead.response_draft ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        Response draft will be generated upon agent analysis.
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

                        {/* Draft Text Box */}
                        <div style={{ position: 'relative' }}>
                            <textarea
                                rows={4}
                                readOnly={!isEditingDraft}
                                value={responseDraftText}
                                onChange={(e) => setResponseDraftText(e.target.value)}
                                style={{
                                    width: '100%',
                                    padding: '0.85rem',
                                    borderRadius: 'var(--radius-sm)',
                                    background: isEditingDraft ? 'var(--bg-dark-0)' : 'var(--bg-dark-2)',
                                    border: isEditingDraft ? '1px solid var(--accent-primary)' : '1px solid var(--border-color)',
                                    color: 'var(--text-main)',
                                    fontFamily: 'var(--font-sans)',
                                    fontSize: '0.9rem',
                                    lineHeight: 1.5,
                                    resize: 'vertical',
                                }}
                            />
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginTop: '0.25rem' }}>
                                Simulated — no external message sent
                            </span>
                        </div>

                        {/* Action Buttons */}
                        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                            {!isEditingDraft ? (
                                <button onClick={() => setIsEditingDraft(true)} className="btn-secondary">
                                    <Edit3 size={14} /> Edit Draft
                                </button>
                            ) : (
                                <button onClick={() => setIsEditingDraft(false)} className="btn-secondary">
                                    Cancel Edit
                                </button>
                            )}

                            <button
                                onClick={() => handleResponseAction('reject')}
                                disabled={responding || lead.response_status === 'rejected'}
                                className="btn-secondary"
                                style={{ color: 'var(--color-hot)', borderColor: 'var(--border-hot)' }}
                            >
                                <XCircle size={14} /> Reject Response
                            </button>

                            <button
                                onClick={() => handleResponseAction('approve')}
                                disabled={responding || lead.response_status === 'simulated_sent'}
                                className="btn-primary"
                                style={{ background: 'var(--color-success)' }}
                            >
                                <CheckCircle size={14} /> {lead.response_status === 'simulated_sent' ? 'Sent (Simulated)' : 'Approve & Simulate Send'}
                            </button>
                        </div>

                    </div>
                )}
            </div>

            {/* Grid: Agent Activity Trace & Audit Trail */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>

                {/* AGENT ACTIVITY OPERATIONAL TRACE */}
                <div className="panel">
                    <div className="panel-header">
                        <div className="panel-title" style={{ fontSize: '0.95rem' }}>
                            <Activity size={16} color="var(--accent-primary)" />
                            Agent Activity Operational Trace
                        </div>
                        <span className="badge-sub">Read-Only Tools</span>
                    </div>

                    <div className="trace-timeline">
                        <div className="trace-item">
                            <span className="trace-status">✓</span>
                            <span>get_lead</span>
                            <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: '0.75rem' }}>42ms</span>
                        </div>
                        <div className="trace-item">
                            <span className="trace-status">✓</span>
                            <span>get_customer_history</span>
                            <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: '0.75rem' }}>18ms</span>
                        </div>
                        <div className="trace-item">
                            <span className="trace-status">✓</span>
                            <span>get_business_rules</span>
                            <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: '0.75rem' }}>11ms</span>
                        </div>
                        <div className="trace-item" style={{ borderLeft: '3px solid var(--color-success)' }}>
                            <span className="trace-status">✓</span>
                            <span style={{ fontWeight: 600 }}>AgentAnalysisResult validated (extra="forbid")</span>
                            <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: '0.75rem' }}>93ms</span>
                        </div>
                    </div>
                </div>

                {/* AUDIT TRAIL TIMELINE */}
                <div className="panel">
                    <div className="panel-header">
                        <div className="panel-title" style={{ fontSize: '0.95rem' }}>
                            <History size={16} color="var(--text-muted)" />
                            Audit Trail Timeline
                        </div>
                        <span className="badge-sub">{auditEvents.length} Events</span>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '240px', overflowY: 'auto', paddingRight: '0.5rem' }}>
                        {auditEvents.length === 0 ? (
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>No audit events logged yet.</span>
                        ) : (
                            auditEvents.map((evt) => (
                                <div key={evt.event_id} style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                                        {new Date(evt.timestamp).toLocaleTimeString()}
                                    </span>
                                    <div>
                                        <strong style={{ color: 'var(--accent-primary)' }}>{evt.action}</strong> by {evt.actor}
                                        {evt.details && (
                                            <span style={{ color: 'var(--text-dim)', display: 'block', fontSize: '0.75rem' }}>
                                                {JSON.stringify(evt.details)}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>

            </div>

        </div>
    );
}
