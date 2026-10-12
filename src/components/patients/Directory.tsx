import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import type { Patient, RiskSignal, VitalReading } from '../../types/index.ts';
import { RiskBadge, TrendPill } from '../ui/Badges.tsx';
import { Sparkline } from '../ui/premium.tsx';
import { RISK_STYLES } from '../../theme/tokens.ts';
import { formatTimeAgo } from '../../utils/format.ts';

export function PatientRows({ slice, risks, latest }: {
  slice: Patient[]; risks: Record<string, RiskSignal>; latest: Record<string, VitalReading>;
}) {
  return (
    <tbody>
      {slice.map((p) => {
        const r = risks[p.id] ?? {
          patientId: p.id,
          score: 10,
          level: 'low',
          probability: 0.1,
          news2: 0,
          trend: 'stable',
          trajectory: [10],
          trajectoryLabels: ['Admit'],
          updatedAt: p.updatedAt,
        };
        const v = latest[p.id];
        const s = RISK_STYLES[r.level];
        return (
          <tr key={p.id} className="table-row group">
            <td className="pl-5 pr-2 py-3.5">
              <Link to={`/patients/${p.id}`} className="font-bold text-slate-900 hover:text-teal-700 hover:underline dark:text-slate-100 dark:hover:text-teal-300" aria-label={`Open patient ${p.id}`}>
                {p.displayName ? `${p.displayName} (${p.id})` : p.id}
              </Link>
              <span className="block text-[11px] text-slate-400 mt-0.5">{p.ward} · {p.bed}</span>
            </td>
            <td className="px-3 py-3.5 text-slate-500 tabular-nums whitespace-nowrap">{p.age} / {p.sex}</td>
            <td className="px-3 py-3.5 whitespace-nowrap text-slate-600 dark:text-slate-300">{p.ward} <span className="text-slate-400">· {p.bed}</span></td>
            <td className="px-3 py-3.5">
              <RiskBadge level={r.level} score={r.score} />
              <div className="mt-1.5 h-1 w-20 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden" aria-hidden>
                <div className="h-full rounded-full vg-bar-grow" style={{ width: `${r.score}%`, background: s.hex }} />
              </div>
            </td>
            <td className="px-3 py-3.5 text-right font-bold tabular-nums">{r.news2}</td>
            <td className="px-3 py-3.5 text-right tabular-nums">
              {v ? <>{Math.round(v.spo2)}<span className="text-slate-400 text-xs">%</span></> : <span className="text-slate-400 text-xs italic">Pending</span>}
            </td>
            <td className="px-3 py-3.5 text-right tabular-nums whitespace-nowrap">
              {v ? <>{Math.round(v.heartRate)} <span className="text-slate-400 text-xs">bpm</span></> : <span className="text-slate-400 text-xs italic">—</span>}
            </td>
            <td className="px-3 py-3.5"><TrendPill trend={r.trend} /></td>
            <td className="px-3 py-3.5">
              <div className="w-20"><Sparkline data={r.trajectory} color={s.hex} height={24} /></div>
              <p className="text-[10px] text-slate-400 tabular-nums mt-0.5 whitespace-nowrap">{formatTimeAgo(p.updatedAt)}</p>
            </td>
            <td className="pl-1 pr-4 py-3.5 text-right">
              <Link to={`/patients/${p.id}`} aria-label={`View details for ${p.id}`} className="icon-btn inline-flex opacity-60 group-hover:opacity-100 transition-all">
                <ChevronRight size={17} aria-hidden />
              </Link>
            </td>
          </tr>
        );
      })}
    </tbody>
  );
}

export function PatientCards({ slice, risks, latest }: {
  slice: Patient[]; risks: Record<string, RiskSignal>; latest: Record<string, VitalReading>;
}) {
  return (
    <div className="mt-4 grid md:grid-cols-2 xl:grid-cols-3 gap-3 md:gap-4 stagger">
      {slice.map((p) => {
        const r = risks[p.id] ?? {
          patientId: p.id,
          score: 10,
          level: 'low',
          probability: 0.1,
          news2: 0,
          trend: 'stable',
          trajectory: [10],
          trajectoryLabels: ['Admit'],
          updatedAt: p.updatedAt,
        };
        const v = latest[p.id];
        const s = RISK_STYLES[r.level];
        return (
          <Link key={p.id} to={`/patients/${p.id}`} className="card card-hover p-5 relative overflow-hidden" aria-label={`Open ${p.id}`}>
            <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: `linear-gradient(90deg, ${s.hex}, transparent)` }} aria-hidden />
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-display font-extrabold tracking-tight text-[15px]">{p.displayName || p.id}</p>
                <p className="text-[11px] text-slate-400">{p.id} · {p.ward}</p>
              </div>
              <RiskBadge level={r.level} score={r.score} />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
              <span>NEWS2: <strong className="text-slate-900 dark:text-slate-100">{r.news2}</strong></span>
              <span>SpO₂: <strong className="text-slate-900 dark:text-slate-100">{v ? `${Math.round(v.spo2)}%` : 'Pending'}</strong></span>
              <span>HR: <strong className="text-slate-900 dark:text-slate-100">{v ? `${Math.round(v.heartRate)} bpm` : '—'}</strong></span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
