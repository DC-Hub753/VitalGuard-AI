import { useState } from 'react';
import { Bell, RefreshCw, LogOut, ShieldCheck, Stethoscope, HeartPulse } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSimulation } from '../../store/useSimulation.ts';
import { formatTimeAgo } from '../../utils/format.ts';
import { useOptionalAuth } from '../../store/AuthContext.tsx';

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const { alerts, running, lastRefresh, refresh } = useSimulation();
  const auth = useOptionalAuth();
  const username = auth?.username ?? null;
  const role = auth?.role ?? null;
  const fullName = auth?.fullName ?? username ?? 'Operator';
  const logout = auth?.logout ?? (() => Promise.resolve());
  const open = alerts.filter((a) => a.status === 'open').length;
  const [spinning, setSpinning] = useState(false);

  const roleBadge = () => {
    if (role === 'admin') {
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
          <ShieldCheck size={11} /> Admin
        </span>
      );
    }
    if (role === 'clinician') {
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-400 border border-teal-500/30">
          <Stethoscope size={11} /> Clinician
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
        <HeartPulse size={11} /> Nurse
      </span>
    );
  };

  return (
    <header className="sticky top-0 z-20 bg-[#f5f8fb]/85 dark:bg-slate-950/80 backdrop-blur-xl border-b border-slate-200/70 dark:border-slate-800/80">
      <div className="flex items-center gap-3 px-4 md:px-8 h-[70px]">
        <div className="min-w-0">
          <h1 className="font-display font-extrabold text-[17px] md:text-lg tracking-tight truncate">{title}</h1>
          {subtitle && <p className="text-xs text-slate-500 truncate mt-0.5">{subtitle}</p>}
        </div>
        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1.5 rounded-full border border-emerald-200/80 bg-emerald-50/70 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200 dark:border-emerald-900/60">
            <span className={`h-1.5 w-1.5 rounded-full ${running ? 'bg-emerald-500 pulse-dot' : 'bg-emerald-500'}`} aria-hidden />
            {running ? 'Simulation running' : 'Simulation paused'}
          </span>
          <span className="hidden xl:inline text-[11px] text-slate-400 tabular-nums" title="Last data refresh">
            Updated {formatTimeAgo(lastRefresh)}
          </span>
          <button
            aria-label="Refresh demo data timestamps"
            title="Refresh demo data timestamps"
            onClick={() => { setSpinning(true); refresh(); window.setTimeout(() => setSpinning(false), 600); }}
            className="icon-btn"
          >
            <RefreshCw size={17} className={spinning ? 'animate-spin' : ''} aria-hidden />
          </button>
          <Link to="/alerts" aria-label={`Alert center, ${open} open alerts`} className="icon-btn relative">
            <Bell size={17} aria-hidden />
            {open > 0 && (
              <span className="absolute top-0.5 right-0.5 min-w-[18px] h-[18px] px-1 rounded-full text-white text-[10px] grid place-items-center font-bold tabular-nums" style={{ background: 'linear-gradient(135deg,#e11d48,#f43f5e)' }}>{open}</span>
            )}
          </Link>

          <div className="hidden md:flex items-center gap-2 pl-2 border-l border-slate-700/60">
            {roleBadge()}
            <span className="max-w-28 truncate text-xs font-medium text-slate-300" title={fullName}>
              {fullName}
            </span>
          </div>

          <button
            type="button"
            onClick={() => void logout()}
            aria-label="Sign out"
            title="Sign out"
            className="icon-btn text-rose-400 hover:text-rose-300 hover:bg-rose-950/30"
          >
            <LogOut size={17} aria-hidden />
          </button>
        </div>
      </div>
    </header>
  );
}
