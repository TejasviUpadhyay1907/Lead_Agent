import React, { useState } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { safeError } from '../../api/presentation';
import { BusyLabel, ErrorState, SectionHeader } from './UI';

const PAGE_LIMIT = 100;

function utcDate(date) {
    return date.toISOString().slice(0, 10);
}

function reportWindow(days) {
    const end = new Date();
    const start = new Date(end.getTime() - (days - 1) * 24 * 60 * 60 * 1000);
    return { start: utcDate(start), end: utcDate(end) };
}

function emptyTotals() {
    return { total: 0, won: 0, lost: 0, disqualified: 0, open: 0, won_value_by_currency: {} };
}

export function OutcomeReport() {
    const [days, setDays] = useState('30');
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState(null);

    const loadReport = async () => {
        if (loading) return;
        setLoading(true);
        setProgress(0);
        setError(null);
        setReport(null);
        const window = reportWindow(Number(days));
        const totals = emptyTotals();
        let cursor = null;
        let pages = 0;
        try {
            do {
                if (pages >= PAGE_LIMIT) {
                    throw new Error('This report window contains more than 10,000 leads. Choose a shorter period to keep the report bounded.');
                }
                const page = await api.getOutcomeReportPage(window.start, window.end, cursor);
                for (const key of ['total', 'won', 'lost', 'disqualified', 'open']) totals[key] += page.counts[key] || 0;
                for (const [currency, amount] of Object.entries(page.won_value_by_currency || {})) {
                    const current = totals.won_value_by_currency[currency] || '0';
                    totals.won_value_by_currency[currency] = addDecimalStrings(current, amount);
                }
                cursor = page.next_cursor;
                pages += 1;
                setProgress(pages);
            } while (cursor);
            const decided = totals.won + totals.lost;
            setReport({ ...totals, ...window, pages, decided, winRate: decided ? (totals.won / decided) * 100 : null, generatedAt: new Date().toISOString() });
        } catch (loadError) {
            setError(safeError(loadError, 'The complete outcome report could not be loaded. No partial totals are shown.'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <section className="panel outcome-report">
            <SectionHeader icon={BarChart3} title="Sales outcomes" subtitle="Company-wide cohort report from every lead page, not the dashboard sample." />
            <div className="outcome-report-controls">
                <label className="field">
                    <span className="field-label">Lead received within</span>
                    <select className="field-input" value={days} onChange={event => setDays(event.target.value)} disabled={loading}>
                        <option value="7">Last 7 days</option>
                        <option value="30">Last 30 days</option>
                        <option value="90">Last 90 days</option>
                        <option value="365">Last 365 days</option>
                    </select>
                </label>
                <button type="button" className="btn-secondary" onClick={loadReport} disabled={loading}>
                    {loading ? <BusyLabel>Reading page {progress + 1}…</BusyLabel> : <><RefreshCw size={15} aria-hidden="true" /> {report ? 'Refresh report' : 'Generate report'}</>}
                </button>
            </div>
            {error && <ErrorState title="Outcome report unavailable" description={error} onRetry={loadReport} />}
            {loading && <p className="form-note" role="status" aria-live="polite">Reading all matching lead pages. Current page: {progress + 1}. Partial totals are hidden until the report is complete.</p>}
            {report && <>
                <div className="outcome-report-metrics" aria-label="Complete outcome report">
                    <div><span>Leads received</span><strong>{report.total.toLocaleString()}</strong></div>
                    <div><span>Won</span><strong>{report.won.toLocaleString()}</strong></div>
                    <div><span>Lost</span><strong>{report.lost.toLocaleString()}</strong></div>
                    <div><span>Disqualified</span><strong>{report.disqualified.toLocaleString()}</strong></div>
                    <div><span>Open / unrecorded</span><strong>{report.open.toLocaleString()}</strong></div>
                    <div><span>Win rate of decided leads</span><strong>{report.winRate == null ? '—' : `${report.winRate.toFixed(1)}%`}</strong><small>{report.decided.toLocaleString()} won or lost</small></div>
                </div>
                {Object.keys(report.won_value_by_currency).length > 0 && <div className="outcome-revenue-list">
                    <strong>Operator-entered won value</strong>
                    {Object.entries(report.won_value_by_currency).sort(([a], [b]) => a.localeCompare(b)).map(([currency, amount]) => (
                        <span key={currency}><b>{currency}</b> {amount}</span>
                    ))}
                </div>}
                <p className="form-note">Cohort: leads received {report.start} through {report.end} (UTC); outcomes reflect the latest recorded state. This report is eventually consistent and may briefly miss recent changes. Values are operator-entered and are not proof of incremental revenue or LeadRescue attribution.</p>
            </>}
            {!report && !loading && !error && <p className="form-note">Generate a bounded report. Won, lost and disqualified are based on recorded outcomes; leads without a result remain open.</p>}
        </section>
    );
}

function addDecimalStrings(left, right) {
    const [leftWhole, leftFraction = ''] = left.split('.');
    const [rightWhole, rightFraction = ''] = right.split('.');
    const scale = Math.max(leftFraction.length, rightFraction.length);
    const factor = 10n ** BigInt(scale);
    const leftValue = BigInt(leftWhole) * factor + BigInt((leftFraction + '0'.repeat(scale)).slice(0, scale) || '0');
    const rightValue = BigInt(rightWhole) * factor + BigInt((rightFraction + '0'.repeat(scale)).slice(0, scale) || '0');
    const sum = leftValue + rightValue;
    const whole = sum / factor;
    if (!scale) return whole.toString();
    const fraction = (sum % factor).toString().padStart(scale, '0').replace(/0+$/, '');
    return fraction ? `${whole}.${fraction}` : whole.toString();
}
