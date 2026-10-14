import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { SimCtx } from './simInit.ts';
import type { AlertItem, Patient, PrioritizedPatient, RiskSignal, VitalReading } from '../types/index.ts';
import type { ToastMsg, ToastSeverity } from './simInit.ts';
import { api } from '../services/api.ts';
import { createLiveSocket } from '../services/liveEvents.ts';
import type { LiveEvent } from '../services/liveEvents.ts';

export function SimulationProvider({ children }: { children: ReactNode }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [latest, setLatest] = useState<Record<string, VitalReading>>({});
  const [risks, setRisks] = useState<Record<string, RiskSignal>>({});
  const [histories, setHistories] = useState<Record<string, VitalReading[]>>({});
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [prioritization, setPrioritization] = useState<PrioritizedPatient[]>([]);
  const [toasts, setToasts] = useState<ToastMsg[]>([]);

  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'reconnecting' | 'disconnected' | 'stale'>('disconnected');
  const [feedMode, setFeedMode] = useState<'live' | 'replay' | 'idle'>('idle');
  const [lastObservationAt, setLastObservationAt] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState(() => new Date().toISOString());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Theme
  const [theme, setThemeState] = useState<'light' | 'dark'>(() => (localStorage.getItem('vg-theme') as 'light' | 'dark') || 'light');
  const setTheme = useCallback((t: 'light' | 'dark') => {
    setThemeState(t);
    localStorage.setItem('vg-theme', t);
    document.documentElement.classList.toggle('dark', t === 'dark');
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  // Toast dispatch
  const idRef = useRef(1);
  const push = useCallback((title: string, message: string, severity: ToastSeverity = 'high', patientId?: string) => {
    const id = idRef.current++;
    setToasts((t) => [...t.slice(-4), { id, title, message, severity, at: new Date().toISOString(), patientId }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 8000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  // Map backend alert to frontend AlertItem
  const mapBackendAlert = useCallback((item: any): AlertItem => {
    const sev = (item.severity || 'high').toLowerCase();
    const severity: AlertItem['severity'] =
      sev === 'critical' ? 'critical' : sev === 'high' ? 'high' : sev === 'low' ? 'info' : 'moderate';
    return {
      id: String(item.id),
      patientId: item.patient_id,
      severity,
      title: item.title,
      description: item.details?.escalation_response || item.details?.message || item.title,
      contributors: item.details?.contributors || (item.details?.news2 ? [`NEWS2 Score: ${item.details.news2.total_score}`] : ['Clinical parameter trigger']),
      status: item.status || 'open',
      createdAt: item.created_at,
      alertType: item.alert_type || 'clinical_rule',
      assignedTo: item.assigned_to || null,
      assignedAt: item.assigned_at || null,
      deadlineMinutes: item.deadline_minutes ?? null,
      ageMinutes: item.age_minutes ?? 0,
      isOverdue: item.is_overdue ?? false,
      notes: Array.isArray(item.notes) ? item.notes : [],
      riskBefore: item.details?.risk_score,
      riskAfter: item.details?.risk_score,
    };
  }, []);

  // Core Data Fetch from Backend REST API
  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [ptRes, prioRes, alRes, obsRes] = await Promise.allSettled([
        api.listPatients(),
        api.getPrioritization(),
        api.listAlerts({ limit: 100 }),
        api.listObservations(undefined, 80),
      ]);

      // 1. Process Patients
      let pts: Patient[] = [];
      if (ptRes.status === 'fulfilled' && ptRes.value.items) {
        pts = ptRes.value.items.map((p: any) => ({
          id: p.patient_id,
          displayName: p.display_name,
          age: p.age || 65,
          sex: p.sex || 'U',
          ward: p.ward || 'General Ward',
          bed: p.bed || '',
          scenario: 'stable',
          active: p.active ?? true,
          dateOfBirth: p.date_of_birth,
          updatedAt: p.updated_at || p.created_at || new Date().toISOString(),
        }));
        setPatients(pts);
      }

      // 2. Process Prioritization
      if (prioRes.status === 'fulfilled' && prioRes.value.items) {
        setPrioritization(prioRes.value.items);
      }

      // 3. Process Alerts
      if (alRes.status === 'fulfilled' && alRes.value.items) {
        const mapped = alRes.value.items.map(mapBackendAlert);
        setAlerts(mapped);
      }

      // 4. Process Observations
      if (obsRes.status === 'fulfilled' && obsRes.value.items) {
        const nextLatest: Record<string, VitalReading> = {};
        const nextHistories: Record<string, VitalReading[]> = {};
        const nextRisks: Record<string, RiskSignal> = {};
        let latestTimestamp: string | null = null;

        const reversed = [...obsRes.value.items].reverse();
        reversed.forEach((obs: any) => {
          const pid = obs.patient_id;
          const inp = obs.inputs || {};
          const pred = obs.prediction || {};
          const reading: VitalReading = {
            patientId: pid,
            timestamp: obs.created_at,
            heartRate: inp.heart_rate || 75,
            spo2: inp.spo2 || 98,
            systolicBp: inp.systolic_bp || 120,
            diastolicBp: inp.diastolic_bp || 80,
            temperature: inp.temperature || 37.0,
            respiratoryRate: inp.respiratory_rate || 16,
          };
          nextLatest[pid] = reading;
          if (!nextHistories[pid]) nextHistories[pid] = [];
          nextHistories[pid].push(reading);

          const score = typeof pred.risk_score === 'number' ? pred.risk_score : 15;
          const level = (pred.risk_level || 'low').toLowerCase() as RiskSignal['level'];
          const prob = pred.model_probability ?? (score / 100);
          const historyArr = nextHistories[pid];
          const trajectory = historyArr.slice(-12).map((h) => h.heartRate > 100 || h.spo2 < 94 ? 75 : 20);

          nextRisks[pid] = {
            patientId: pid,
            score,
            level,
            probability: prob,
            news2: score >= 80 ? 9 : score >= 60 ? 6 : score >= 35 ? 3 : 0,
            trend: score >= 70 ? 'worsening' : 'stable',
            trajectory: trajectory.length ? trajectory : [score],
            trajectoryLabels: historyArr.slice(-12).map((h) => new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
            updatedAt: obs.created_at,
          };

          if (!latestTimestamp || new Date(obs.created_at) > new Date(latestTimestamp)) {
            latestTimestamp = obs.created_at;
          }
        });

        setLatest(nextLatest);
        setHistories(nextHistories);
        setRisks(nextRisks);
        if (latestTimestamp) setLastObservationAt(latestTimestamp);
      }

      setLastRefresh(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to synchronize with backend');
    } finally {
      setLoading(false);
    }
  }, [mapBackendAlert]);

  // Initial load
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Connect live WebSocket event listener
  useEffect(() => {
    const unsub = createLiveSocket(
      (event: LiveEvent) => {
        if (event.type === 'observation.created') {
          const obsEvent = event as any;
          const pid = obsEvent.patient_id;
          const inp = obsEvent.observation || {};
          const pred = obsEvent.prediction || {};
          const reading: VitalReading = {
            patientId: pid,
            timestamp: obsEvent.created_at,
            heartRate: inp.heart_rate || 75,
            spo2: inp.spo2 || 98,
            systolicBp: inp.systolic_bp || 120,
            diastolicBp: inp.diastolic_bp || 80,
            temperature: inp.temperature || 37.0,
            respiratoryRate: inp.respiratory_rate || 16,
          };

          setLatest((prev) => ({ ...prev, [pid]: reading }));
          setHistories((prev) => {
            const current = prev[pid] ? [...prev[pid], reading].slice(-50) : [reading];
            return { ...prev, [pid]: current };
          });

          const score = typeof pred.risk_score === 'number' ? pred.risk_score : 15;
          const level = (pred.risk_level || 'low').toLowerCase() as RiskSignal['level'];
          setRisks((prev) => {
            const old = prev[pid];
            return {
              ...prev,
              [pid]: {
                patientId: pid,
                score,
                level,
                probability: pred.model_probability ?? score / 100,
                news2: score >= 80 ? 9 : score >= 60 ? 6 : score >= 35 ? 3 : 0,
                trend: score >= 70 ? 'worsening' : 'stable',
                trajectory: old ? [...old.trajectory.slice(-11), score] : [score],
                trajectoryLabels: old ? [...old.trajectoryLabels.slice(-11), new Date(obsEvent.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })] : ['Now'],
                updatedAt: obsEvent.created_at,
              },
            };
          });

          setLastObservationAt(obsEvent.created_at);
          setFeedMode(obsEvent.source_mode === 'historical_replay' ? 'replay' : 'live');

          api.getPrioritization().then((res) => setPrioritization(res.items)).catch(() => {});
        } else if (event.type === 'alert.created' || event.type === 'alert.updated') {
          const alertEvent = event as any;
          const raw = alertEvent.alert;
          if (raw) {
            const mapped = mapBackendAlert(raw);
            setAlerts((prev) => {
              const idx = prev.findIndex((a) => a.id === mapped.id);
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = mapped;
                return next;
              }
              return [mapped, ...prev];
            });

            if (event.type === 'alert.created') {
              push(
                mapped.title,
                `Alert #${mapped.id} (${mapped.severity.toUpperCase()}) · Patient ${mapped.patientId}`,
                mapped.severity as ToastSeverity,
                mapped.patientId,
              );
            }
          }
        }
      },
      (status) => {
        if (status === 'connected') {
          setConnectionStatus('connected');
          void refresh();
        } else if (status === 'reconnecting' || status === 'connecting') {
          setConnectionStatus('reconnecting');
        } else {
          setConnectionStatus('disconnected');
        }
      },
    );

    return () => unsub();
  }, [mapBackendAlert, push, refresh]);

  // Periodic 1-second interval for timestamps
  useEffect(() => {
    const timer = window.setInterval(() => {
      setLastRefresh(new Date().toISOString());
      if (lastObservationAt) {
        const elapsedMinutes = (Date.now() - new Date(lastObservationAt).getTime()) / 60000;
        if (elapsedMinutes > 240) {
          setFeedMode('idle');
        }
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [lastObservationAt]);

  // Real Backend Patient Operations
  const createPatient = useCallback(async (payload: { patient_id: string; display_name: string; sex?: 'M' | 'F' | 'U'; ward?: string; bed?: string; date_of_birth?: string }) => {
    await api.createPatient(payload);
    push('Patient admitted', `Patient ${payload.patient_id} admitted to ${payload.ward || 'General Ward'}.`, 'ok', payload.patient_id);
    await refresh();
  }, [push, refresh]);

  const updatePatient = useCallback(async (id: string, updates: Partial<{ display_name: string; ward: string; bed: string; active: boolean }>) => {
    await api.updatePatient(id, updates);
    push('Patient updated', `Details for patient ${id} successfully updated.`, 'info', id);
    await refresh();
  }, [push, refresh]);

  const deactivatePatient = useCallback(async (id: string) => {
    await api.deactivatePatient(id);
    push('Patient discharged', `Patient ${id} has been deactivated/discharged.`, 'info', id);
    await refresh();
  }, [push, refresh]);

  // Real Backend Alert Operations
  const acknowledgeAlert = useCallback(async (id: string | number, note?: string) => {
    await api.acknowledgeAlert(id, note);
    push('Alert acknowledged', `Alert #${id} marked as acknowledged.`, 'info');
    await refresh();
  }, [push, refresh]);

  const assignAlert = useCallback(async (id: string | number, assignee: string, note?: string) => {
    await api.assignAlert(id, assignee, note);
    push('Alert assigned', `Alert #${id} assigned to ${assignee}.`, 'info');
    await refresh();
  }, [push, refresh]);

  const resolveAlert = useCallback(async (id: string | number, note?: string) => {
    await api.resolveAlert(id, note);
    push('Alert resolved', `Alert #${id} successfully resolved and archived.`, 'ok');
    await refresh();
  }, [push, refresh]);

  const reopenAlert = useCallback(async (id: string | number, reason: string) => {
    await api.reopenAlert(id, reason);
    push('Alert reopened', `Alert #${id} reopened: ${reason}`, 'high');
    await refresh();
  }, [push, refresh]);

  const addAlertNote = useCallback(async (id: string | number, note: string) => {
    await api.addAlertNote(id, note);
    push('Clinical note added', `Auditable note recorded for alert #${id}.`, 'info');
    await refresh();
  }, [push, refresh]);

  // Historical Replay Burst Trigger (Controlled QA & Dev tool)
  const triggerReplayBurst = useCallback(async () => {
    const now = new Date().toISOString();
    const records = [
      { patient_id: 'DEMO-001', event_id: 'replay-' + Date.now() + '-1', observed_at: now, vitals: { heart_rate: 128, spo2: 88, systolic_bp: 98, diastolic_bp: 64, temperature: 38.2, respiratory_rate: 26, age: 65 } },
      { patient_id: 'DEMO-001', event_id: 'replay-' + Date.now() + '-2', observed_at: new Date(Date.now() - 60_000).toISOString(), vitals: { heart_rate: 116, spo2: 91, systolic_bp: 104, diastolic_bp: 68, temperature: 37.9, respiratory_rate: 22, age: 65 } },
      { patient_id: 'DEMO-002', event_id: 'replay-' + Date.now() + '-3', observed_at: new Date(Date.now() - 120_000).toISOString(), vitals: { heart_rate: 92, spo2: 96, systolic_bp: 118, diastolic_bp: 76, temperature: 37.1, respiratory_rate: 17, age: 54 } },
    ];
    await api.ingestReplayBatch(records);
    setFeedMode('replay');
    // Re-read persisted observations immediately; do not require a manual page reload.
    await refresh();
    push('Historical Replay Batch Ingested', 'Test replay batch ingested with source_mode="historical_replay".', 'info', 'P-SIM-003');
  }, [push, refresh]);

  // Compatibility shims
  const acknowledgeShim = useCallback((id: string) => { void acknowledgeAlert(id); }, [acknowledgeAlert]);
  const undoAcknowledgeShim = useCallback((id: string) => { void reopenAlert(id, 'Undo acknowledgement requested by clinician'); }, [reopenAlert]);

  return (
    <SimCtx.Provider
      value={{
        patients,
        latest,
        risks,
        histories,
        alerts,
        prioritization,
        toasts,
        connectionStatus,
        connectionState: connectionStatus,
        feedMode,
        telemetryMode: feedMode === 'replay' ? 'historical_replay' : feedMode === 'live' ? 'live' : 'idle',
        lastObservationAt,
        lastRefresh,
        loading,
        error,

        refresh,
        createPatient,
        updatePatient,
        deactivatePatient,
        acknowledgeAlert,
        assignAlert,
        resolveAlert,
        reopenAlert,
        addAlertNote,
        triggerReplayBurst,
        dismissToast,

        // Legacy compatibility
        running: connectionStatus === 'connected',
        tick: 0,
        speed: 'normal',
        multiplier: 1,
        start: () => { void triggerReplayBurst(); },
        pause: () => {},
        reset: () => { void refresh(); },
        setSpeed: () => {},
        setMultiplier: () => {},
        acknowledge: acknowledgeShim,
        undoAcknowledge: undoAcknowledgeShim,
        dataSource: 'api',
        setDataSource: () => {},
        theme,
        setTheme,
      }}
    >
      {children}
    </SimCtx.Provider>
  );
}

