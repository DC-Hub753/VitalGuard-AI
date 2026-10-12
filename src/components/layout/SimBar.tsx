import { Activity, Clock3, Database, RefreshCw, Wifi, WifiOff } from 'lucide-react';
import { useSimulation } from '../../store/useSimulation.ts';

export function SimBar() {
  const {
    connectionStatus,
    feedMode,
    lastObservationAt,
    prioritization,
    refresh,
    triggerReplayBurst,
    loading,
  } = useSimulation();

  const isConnected = connectionStatus === 'connected';
  const isReconnecting = connectionStatus === 'reconnecting';
  const isStale = connectionStatus === 'stale' || (lastObservationAt && (Date.now() - new Date(lastObservationAt).getTime()) > 4 * 3600 * 1000);

  const criticalCount = prioritization.filter((p) => p.priority_rank === 1 || p.risk_category === 'critical').length;
  const highCount = prioritization.filter((p) => p.priority_rank === 2 || p.risk_category === 'high').length;
  const reviewCount = prioritization.filter((p) => p.needs_review).length;

  const formatElapsed = (iso: string | null) => {
    if (!iso) return 'No observations recorded yet';
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 60) return `${s}s ago`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    return `${h}h ago`;
  };

  return (
    <div className="px-4 md:px-8 pt-4">
      <div
        className="relative overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 sm:px-5 py-3.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 shadow-[0_2px_10px_rgba(15,35,65,0.025)]"
        role="region"
        aria-label="Clinical telemetry and backend connection state"
      >
        <div
          className={`absolute inset-y-0 left-0 w-1.5 ${
            isConnected
              ? 'bg-emerald-500'
              : isReconnecting
              ? 'bg-amber-500'
              : 'bg-rose-500'
          }`}
          aria-hidden
        />

        <div className="relative flex items-center gap-3 min-w-0">
          <span
            className={`relative grid place-items-center h-10 w-10 rounded-xl border shrink-0 ${
              isConnected
                ? 'bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-300'
                : isReconnecting
                ? 'bg-amber-50 border-amber-200 text-amber-700 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-300'
                : 'bg-rose-50 border-rose-200 text-rose-700 dark:bg-rose-950/40 dark:border-rose-800 dark:text-rose-300'
            }`}
            aria-hidden
          >
            {isConnected ? (
              <Activity size={18} className="animate-pulse" />
            ) : isReconnecting ? (
              <RefreshCw size={18} className="animate-spin" />
            ) : (
              <WifiOff size={18} />
            )}
          </span>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-extrabold tracking-tight text-slate-900 dark:text-slate-100 uppercase flex items-center gap-1.5">
                <span
                  className={`h-2 w-2 rounded-full ${
                    isConnected ? 'bg-emerald-500 pulse-dot' : isReconnecting ? 'bg-amber-500' : 'bg-rose-500'
                  }`}
                  aria-hidden
                />
                {isConnected ? 'Telemetry Channel: Active' : isReconnecting ? 'Reconnecting to Event Stream' : 'Event Stream: Offline'}
              </span>

              <span
                className={`text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-md border ${
                  feedMode === 'live'
                    ? 'bg-teal-50 border-teal-200 text-teal-800 dark:bg-teal-950/40 dark:border-teal-800 dark:text-teal-300'
                    : feedMode === 'replay'
                    ? 'bg-indigo-50 border-indigo-200 text-indigo-800 dark:bg-indigo-950/40 dark:border-indigo-800 dark:text-indigo-300'
                    : 'bg-slate-100 border-slate-200 text-slate-600 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400'
                }`}
              >
                {feedMode === 'live' ? 'Live Telemetry' : feedMode === 'replay' ? 'Historical Replay Mode' : 'No Recent Stream'}
              </span>

              {isStale && (
                <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-300 px-2 py-0.5 rounded-md flex items-center gap-1">
                  <Clock3 size={11} /> Stale Telemetry (&gt;4h)
                </span>
              )}
            </div>

            <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate mt-0.5 flex flex-wrap items-center gap-x-2">
              <span>Last observation: {formatElapsed(lastObservationAt)}</span>
              <span>·</span>
              <span className="font-medium text-slate-700 dark:text-slate-300">
                Queue: {criticalCount} Critical, {highCount} High, {reviewCount} Needs Review
              </span>
            </p>
          </div>
        </div>

        <div className="relative ml-auto flex flex-wrap items-center gap-2">
          <button
            onClick={() => void refresh()}
            disabled={loading}
            className="btn-secondary !py-1.5 !text-xs"
            title="Reconcile with persistent backend state"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden />
            Sync State
          </button>

          <button
            onClick={() => void triggerReplayBurst()}
            className="btn-secondary !py-1.5 !text-xs border-indigo-200 text-indigo-700 dark:border-indigo-900 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-950/30"
            title="Inject a controlled batch of historical observations for testing"
          >
            <Database size={13} aria-hidden />
            Historical Replay (QA)
          </button>
        </div>
      </div>
    </div>
  );
}

