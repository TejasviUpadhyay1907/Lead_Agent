import React from 'react';
import { Flame, AlertTriangle, Clock, Inbox, CheckCircle2, ChevronRight, Sparkles, User } from 'lucide-react';
import { PriorityBadge, RiskBadge, LifecycleBadge } from '../components/Common/Badge';
import { StatCard } from '../components/Common/StatCard';

export function DashboardView({ leads, followups, onSelectLead, onSeedData, onAnalyzeLead }) {
    const totalLeads = leads.length;
    const hotLeads = leads.filter(l => l.priority && l.priority.toLowerCase() === 'hot').length;
    const warmLeads = leads.filter(l => l.priority && l.priority.toLowerCase() === 'warm').length;
    const coldLeads = leads.filter(l => l.priority && l.priority.toLowerCase() === 'cold').length;
    const atRiskLeads = leads.filter(l => l.risk_status && l.risk_status.toLowerCase() === 'at_risk').length;
    const pendingResponses = leads.filter(l => l.response_status === 'draft').length;
    const followupsDue = followups.filter(f => f.status === 'scheduled' || f.status === 'overdue').length;

    // Leads needing attention: AT_RISK leads or HOT/WARM leads with draft response or unanalyzed
    const needsAttention = leads.filter(l =>
        (l.risk_status && l.risk_status.toLowerCase() === 'at_risk') ||
        (l.priority && (l.priority.toLowerCase() === 'hot' || l.priority.toLowerCase() === 'warm') && l.lifecycle_status !== 'resolved' && l.lifecycle_status !== 'opted_out') ||
        l.lifecycle_status === 'new'
    ).slice(0, 5);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Top Banner if no leads */}
            {totalLeads === 0 && (
                <div className="panel" style={{ borderLeft: '4px solid var(--accent-primary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div>
                        <h3 style={{ fontSize: '1.1rem', marginBottom: '0.25rem' }}>Welcome to LeadRescue AI Dashboard</h3>
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                            No leads currently in database. Click below to seed the 5 canonical Phase 0 demo leads.
                        </p>
                    </div>
                    <button onClick={onSeedData} className="btn-primary">
                        <Sparkles size={16} /> Seed Canonical Demo Leads
                    </button>
                </div>
            )}

            {/* Top Metrics Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
                <StatCard title="Total Leads" value={totalLeads} subtext="Incoming Lead Inquiries" icon={Inbox} color="var(--accent-primary)" />
                <StatCard title="HOT Leads" value={hotLeads} subtext="High Commercial Intent" icon={Flame} color="var(--color-hot)" />
                <StatCard title="At Risk SLA" value={atRiskLeads} subtext="Response Target Exceeded" icon={AlertTriangle} color="var(--color-at-risk)" />
                <StatCard title="Pending Responses" value={pendingResponses} subtext="Awaiting Human Approval" icon={Clock} color="var(--color-warm)" />
                <StatCard title="Follow-ups Due" value={followupsDue} subtext="Scheduled Tasks" icon={CheckCircle2} color="var(--color-success)" />
            </div>

            {/* Main Grid: Needs Attention & Analytics */}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>

                {/* Needs Attention Priority Section */}
                <div className="panel">
                    <div className="panel-header">
                        <div className="panel-title">
                            <AlertTriangle size={18} color="var(--color-warm)" />
                            Needs Immediate Attention
                        </div>
                        <span className="badge-sub">{needsAttention.length} Actionable Leads</span>
                    </div>

                    {needsAttention.length === 0 ? (
                        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-dim)' }}>
                            No leads currently require urgent attention.
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                            {needsAttention.map((lead) => (
                                <div
                                    key={lead.lead_id}
                                    onClick={() => onSelectLead(lead.lead_id)}
                                    style={{
                                        padding: '1rem',
                                        borderRadius: 'var(--radius-sm)',
                                        background: 'var(--bg-dark-0)',
                                        border: lead.risk_status === 'at_risk' ? '1px solid var(--border-at-risk)' : '1px solid var(--border-color)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'space-between',
                                        cursor: 'pointer',
                                        transition: 'all 0.15s ease',
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent-primary)'}
                                    onMouseLeave={(e) => e.currentTarget.style.borderColor = lead.risk_status === 'at_risk' ? 'var(--border-at-risk)' : 'var(--border-color)'}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flex: 1 }}>
                                        <div style={{
                                            width: '40px',
                                            height: '40px',
                                            borderRadius: '50%',
                                            background: 'var(--bg-dark-2)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            fontWeight: 600,
                                            color: 'var(--text-main)',
                                        }}>
                                            {lead.customer_name ? lead.customer_name.charAt(0) : <User size={18} />}
                                        </div>

                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.2rem' }}>
                                                <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>{lead.customer_name}</span>
                                                <PriorityBadge priority={lead.priority} />
                                                <RiskBadge risk={lead.risk_status} />
                                                <LifecycleBadge status={lead.lifecycle_status} />
                                            </div>
                                            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                "{lead.raw_message}"
                                            </p>
                                        </div>
                                    </div>

                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginLeft: '1rem' }}>
                                        {lead.score !== null && (
                                            <div style={{ textAlign: 'right' }}>
                                                <span style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'var(--font-heading)', color: 'var(--accent-primary)' }}>
                                                    {lead.score}
                                                </span>
                                                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'block' }}>/100</span>
                                            </div>
                                        )}
                                        {lead.lifecycle_status === 'new' ? (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); onAnalyzeLead(lead.lead_id); }}
                                                className="btn-primary"
                                                style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                                            >
                                                <Sparkles size={12} /> Analyze
                                            </button>
                                        ) : (
                                            <ChevronRight size={18} color="var(--text-dim)" />
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Priority & Risk Distribution Overview */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                    <div className="panel">
                        <div className="panel-header">
                            <div className="panel-title">Priority Breakdown</div>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                                    <span style={{ color: 'var(--color-hot)', fontWeight: 600 }}>HOT (80-100)</span>
                                    <span>{hotLeads} leads</span>
                                </div>
                                <div style={{ height: '6px', background: 'var(--bg-dark-2)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                                    <div style={{ width: `${totalLeads ? (hotLeads / totalLeads) * 100 : 0}%`, height: '100%', background: 'var(--color-hot)' }} />
                                </div>
                            </div>

                            <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                                    <span style={{ color: 'var(--color-warm)', fontWeight: 600 }}>WARM (50-79)</span>
                                    <span>{warmLeads} leads</span>
                                </div>
                                <div style={{ height: '6px', background: 'var(--bg-dark-2)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                                    <div style={{ width: `${totalLeads ? (warmLeads / totalLeads) * 100 : 0}%`, height: '100%', background: 'var(--color-warm)' }} />
                                </div>
                            </div>

                            <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                                    <span style={{ color: 'var(--color-cold)', fontWeight: 600 }}>COLD (0-49)</span>
                                    <span>{coldLeads} leads</span>
                                </div>
                                <div style={{ height: '6px', background: 'var(--bg-dark-2)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                                    <div style={{ width: `${totalLeads ? (coldLeads / totalLeads) * 100 : 0}%`, height: '100%', background: 'var(--color-cold)' }} />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="panel">
                        <div className="panel-header">
                            <div className="panel-title">SLA & Operational Status</div>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.85rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0', borderBottom: '1px solid var(--border-color)' }}>
                                <span style={{ color: 'var(--text-muted)' }}>Response Target SLA:</span>
                                <span style={{ fontWeight: 600 }}>20 Minutes</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0', borderBottom: '1px solid var(--border-color)' }}>
                                <span style={{ color: 'var(--text-muted)' }}>High-Value Threshold:</span>
                                <span style={{ fontWeight: 600 }}>$50,000</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0' }}>
                                <span style={{ color: 'var(--text-muted)' }}>Opt-Out Safeguard:</span>
                                <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>Active</span>
                            </div>
                        </div>
                    </div>

                </div>

            </div>
        </div>
    );
}
