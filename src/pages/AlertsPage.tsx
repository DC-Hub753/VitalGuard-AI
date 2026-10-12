import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BellRing, CheckCircle2, ShieldCheck, Filter, RefreshCw } from 'lucide-react';
import { Shell } from '../components/layout/Shell.tsx';
import { PageHeader } from '../components/ui/Primitives.tsx';
import { EmptyState } from '../components/ui/States.tsx';
import { useSimulation } from '../store/useSimulation.ts';
import { AlertCard } from '../components/alerts/AlertCard.tsx';
import { BackendAlertInbox } from '../components/alerts/BackendAlertInbox.tsx';
import type { AlertStatus } from '../types/index.ts';

const tabs: { key: AlertStatus | 'all'; label: string }[] = [
  { key: 'all', label: 'All Alerts' },
  { key: 'open', label: 'Open' },
  { key: 'acknowledged', label: 'Acknowledged' },
  { key: 'resolved', label: 'Resolved' },
];

export function AlertsPage() {
  const { alerts, acknowledgeAlert, resolveAlert, reopenAlert, refresh, connectionState } = useSimulation();
  const [tab, setTab] = useState<(typeof tabs)[number]['key']>('all');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const counts = useMemo(() => ({
    open: alerts.filter((a) => a.status === 'open').length,
    ack: alerts.filter((a) => a.status === 'acknowledged' || a.status === 'assigned').length,
    res: alerts.filter((a) => a.status === 'resolved').length,
  }), [alerts]);

  const rows = useMemo(() => {
    return alerts.filter((a) => {
      if (tab === 'all') return true;
      if (tab === 'acknowledged') return a.status === 'acknowledged' || a.status === 'assigned';
      return a.status === tab;
    });
  }, [alerts, tab]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await refresh();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  return (
    <Shell title="Alert Operations" subtitle="Safety signals · clinical review required">
      <PageHeader
        eyebrow="Safety signals"
        title="Alert Operations Center"
        subtitle="Authoritative safety signals, Royal College of Physicians NEWS2 escalation thresholds, and audit trails."
        crumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Alerts' }]}
      />

      {/* Primary Backend Alert Management Inbox */}
      <BackendAlertInbox />

      {/* Operational Signal Queue Overview */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-bold">Active Patient Signal Feed</h2>
          <p className="text-xs text-slate-500">Live synchronized telemetry events across monitored ward units</p>
        </div>
        <button
          onClick={handleManualRefresh}
          disabled={isRefreshing}
          className="btn-secondary !text-xs inline-flex items-center gap-1.5"
        >
          <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
          Sync Signals
        </button>
      </div>

      <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4 stagger">
        {[
          { l: 'Open Signals', v: counts.open, h: 'Requires clinical evaluation', icon: BellRing, cls: 'text-rose-600 bg-rose-50 dark:bg-rose-950/60 dark:text-rose-300' },
          { l: 'Acknowledged / Assigned', v: counts.ack, h: 'Under review by staff', icon: ShieldCheck, cls: 'text-amber-600 bg-amber-50 dark:bg-amber-950/60 dark:text-amber-300' },
          { l: 'Resolved Signals', v: counts.res, h: 'Archived clinical events', icon: CheckCircle2, cls: 'text-teal-700 bg-teal-50 dark:bg-teal-950/60 dark:text-teal-300' },
        ].map(({ l, v, h, icon: Icon, cls }) => (
          <div key={l} className="card card-hover p-4 sm:p-5">
            <p className="eyebrow flex items-center gap-1.5">
              <span className={`h-6 w-6 rounded-lg grid place-items-center ${cls}`}>
                <Icon size={13} aria-hidden />
              </span>
              {l}
            </p>
            <p className="metric text-3xl mt-2 tabular-nums">{v}</p>
            <p className="text-[11px] text-slate-400 mt-0.5">{h}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2" role="tablist" aria-label="Alert status filter">
        <span className="text-xs font-bold text-slate-400 mr-1 flex items-center gap-1">
          <Filter size={13} /> Filter:
        </span>
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`tab-btn ${tab === t.key ? 'tab-on' : 'tab-off'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon="alert"
            title="No alerts in this status view"
            hint={
              connectionState === 'disconnected'
                ? 'Backend telemetry stream is currently disconnected. Attempting to restore link.'
                : 'All patient vital signs and clinical assessment thresholds are within target bounds.'
            }
          />
        </div>
      ) : (
        <div className="mt-4 grid xl:grid-cols-2 gap-3 items-start">
          {rows.map((a) => (
            <div key={a.id} className="relative group">
              <AlertCard
                a={a}
                onAck={() => acknowledgeAlert(a.id)}
                onResolve={() => resolveAlert(a.id, 'Clinical assessment resolved by staff')}
                onReopen={() => reopenAlert(a.id, 'Clinical re-evaluation required')}
              />
              <div className="mt-1 text-right">
                <Link
                  to={`/patients/${a.patientId}`}
                  className="inline-flex items-center gap-1 text-[11px] font-bold text-teal-600 hover:text-teal-700 dark:text-teal-400"
                >
                  View patient history & trajectory <ArrowRight size={11} aria-hidden />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}
