import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { api } from '../services/api.ts';
import { SectionCard } from '../components/ui/Primitives.tsx';
import { ExplanationPanel } from '../components/risk/ExplanationPanel.tsx';
import { VitalLine } from '../components/charts/Vitals.tsx';
import { EventTimeline, buildTimeline } from '../components/patients/Timeline.tsx';
import { CHART_COLORS } from '../theme/tokens.ts';
import { demoDataService } from '../services/demoDataService.ts';
import { useSimulation } from '../store/useSimulation.ts';
import { formatTimeAgo } from '../utils/format.ts';
export function ExplainCard({ patientId }: { patientId: string }) {
  const { latest } = useSimulation();
  const v = latest[patientId];
  if (!v) return null;
  const factors = demoDataService.factors(patientId).map((f, i) => {
    if (i === 0) return { ...f, currentValue: `${Math.round(v.spo2)}%`, trend: 'Downward in window' };
    if (i === 1) return { ...f, currentValue: `${Math.round(v.heartRate)} bpm`, trend: 'Upward in window' };
    return f;
  });
  return (
    <div className="mt-4">
      <SectionCard eyebrow="Explainability" title="Why is the AI risk signal elevated?" hint="Ranked signal contributions" label="AI explanation">
        <ExplanationPanel factors={factors} patientId={patientId} />
      </SectionCard>
    </div>
  );
}
export function VitalCharts({ patientId }: { patientId: string }) {
  const { latest, histories } = useSimulation();
  const v = latest[patientId];
  const h = histories[patientId] ?? [];
  const [persistedRows, setPersistedRows] = useState<Array<{ t: string; hr: number; spo2: number; sys: number; dia: number; temp: number; rr: number }>>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setHistoryLoading(true);
    void api.listObservations(patientId, 100).then((response) => {
      if (!active) return;
      const items = [...(response.items ?? [])].reverse();
      setPersistedRows(items.map((obs: any) => {
        const input = obs.inputs ?? obs.observation ?? {};
        return {
          t: formatTimeAgo(obs.created_at ?? obs.observed_at ?? new Date().toISOString()),
          hr: Number(input.heart_rate ?? input.heartRate ?? 75),
          spo2: Number(input.spo2 ?? 98),
          sys: Number(input.systolic_bp ?? input.systolicBp ?? 120),
          dia: Number(input.diastolic_bp ?? input.diastolicBp ?? 80),
          temp: Number(input.temperature ?? 37),
          rr: Number(input.respiratory_rate ?? input.respiratoryRate ?? 16),
        };
      }));
    }).catch(() => {
      if (active) setPersistedRows([]);
    }).finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [patientId]);
  const rows = persistedRows.length ? persistedRows : h.map((x) => ({ t: formatTimeAgo(x.timestamp), hr: x.heartRate, spo2: x.spo2, sys: x.systolicBp, dia: x.diastolicBp, temp: x.temperature, rr: x.respiratoryRate }));
  const chartLatest = v ?? (rows.length ? {
    heartRate: rows[rows.length - 1].hr, spo2: rows[rows.length - 1].spo2,
    systolicBp: rows[rows.length - 1].sys, diastolicBp: rows[rows.length - 1].dia,
    temperature: rows[rows.length - 1].temp, respiratoryRate: rows[rows.length - 1].rr,
  } : undefined);
  if (!chartLatest) return <div className="mt-4"><SectionCard title="Vital trends" hint="Persisted observations for this patient" label="Vital trends">{historyLoading ? <p className="text-sm text-slate-500">Loading patient observations…</p> : <p className="text-sm text-slate-500">No stored observations are available for this patient yet. Use Historical Replay (QA) and retry.</p>}</SectionCard></div>;
  const C = (t: string, hint: string, l: string, val: string, u: string, lines: { key: string; color: string; name: string }[], unit: string) => (
    <SectionCard key={l} title={t} hint={hint} label={`${l} trend`}>
      <div className="flex items-baseline gap-2"><p className="metric text-2xl">{val}</p><p className="text-xs text-slate-400">{u}</p></div>
      <div className="mt-2"><VitalLine data={rows} lines={lines} unit={unit} /></div>
    </SectionCard>
  );
  return (
    <div className="mt-4 grid lg:grid-cols-2 gap-4 items-start">
      {C('Heart rate', 'Beats per minute', 'hr', String(Math.round(chartLatest.heartRate)), 'bpm', [{ key: 'hr', color: CHART_COLORS.heartRate, name: 'HR' }], 'bpm')}
      {C('SpO₂', 'Oxygen saturation', 'spo2', String(Math.round(chartLatest.spo2)), '%', [{ key: 'spo2', color: CHART_COLORS.spo2, name: 'SpO₂' }], '%')}
      {C('Blood pressure', 'Systolic + diastolic pair', 'bp', `${chartLatest.systolicBp}/${chartLatest.diastolicBp}`, 'mmHg', [{ key: 'sys', color: CHART_COLORS.systolic, name: 'Systolic' }, { key: 'dia', color: CHART_COLORS.diastolic, name: 'Diastolic' }], 'mmHg')}
      {C('Temperature', 'Degrees Celsius', 'temp', chartLatest.temperature.toFixed(1), '°C', [{ key: 'temp', color: CHART_COLORS.temperature, name: 'Temp' }], '°C')}
      {C('Respiratory rate', 'Breaths per minute', 'rr', String(Math.round(chartLatest.respiratoryRate)), '/min', [{ key: 'rr', color: CHART_COLORS.respiratoryRate, name: 'RR' }], '/min')}
      <TimelineCard patientId={patientId} />
    </div>
  );
}
export function TimelineCard({ patientId }: { patientId: string }) {
  const { histories, risks } = useSimulation();
  const h = histories[patientId] ?? [];
  const r = risks[patientId];
  if (!r) return null;
  const events = buildTimeline(h, r.trajectory);
  return (
    <SectionCard eyebrow="Timeline" title="Event timeline" hint="Signal and observation history" label="Demo event timeline">
      <span className="sr-only">Demo event timeline</span>
      <EventTimeline events={events} />
    </SectionCard>
  );
}
export function AlertList({ patientId }: { patientId: string }) {
  const { alerts } = useSimulation();
  const list = alerts.filter((a) => a.patientId === patientId).slice(0, 3);
  return (
    <div className="mt-4">
      <SectionCard eyebrow="Signals" title="Recent alerts" hint="Signals for this patient" label="Recent alerts"
        action={<Link to="/alerts" className="btn-ghost !text-[13px] !py-1.5">Alert center</Link>}>
        {list.length === 0 ? <p className="text-sm text-slate-500">No alerts for this patient yet.</p> : (
          <ul className="space-y-2.5">
            {list.map((a) => (
              <li key={a.id} className="rounded-2xl border border-slate-200/70 dark:border-white/[0.07] px-3.5 py-3 text-sm hover:border-teal-300/60 transition-colors">
                <p className="font-bold">{a.title} <span className="font-normal text-slate-400 tabular-nums">· {a.riskBefore} → {a.riskAfter}</span></p>
                <p className="text-xs text-slate-500 mt-0.5 capitalize">{formatTimeAgo(a.createdAt)} · {a.status} · Review recommended</p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
