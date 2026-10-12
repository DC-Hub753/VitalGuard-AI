import { createContext } from 'react';
import type { Patient, RiskSignal, VitalReading, AlertItem, PrioritizedPatient } from '../types/index.ts';

export type ToastSeverity = 'high' | 'critical' | 'info' | 'ok';
export interface ToastMsg { id: number; title: string; message: string; severity: ToastSeverity; at: string; patientId?: string; }

export interface SimValue {
  patients: Patient[];
  latest: Record<string, VitalReading>;
  risks: Record<string, RiskSignal>;
  histories: Record<string, VitalReading[]>;
  alerts: AlertItem[];
  prioritization: PrioritizedPatient[];
  toasts: ToastMsg[];
  connectionStatus: 'connected' | 'reconnecting' | 'disconnected' | 'stale';
  connectionState: 'connected' | 'reconnecting' | 'disconnected' | 'stale';
  feedMode: 'live' | 'replay' | 'idle';
  telemetryMode: 'live' | 'historical_replay' | 'idle';
  lastObservationAt: string | null;
  lastRefresh: string;
  loading: boolean;
  error: string | null;

  // Authoritative clinical operations
  refresh: () => Promise<void>;
  createPatient: (payload: { patient_id: string; display_name: string; sex?: 'M' | 'F' | 'U'; ward?: string; bed?: string; date_of_birth?: string }) => Promise<void>;
  updatePatient: (id: string, updates: Partial<{ display_name: string; ward: string; bed: string; active: boolean }>) => Promise<void>;
  deactivatePatient: (id: string) => Promise<void>;
  acknowledgeAlert: (id: string | number, note?: string) => Promise<void>;
  assignAlert: (id: string | number, assignee: string, note?: string) => Promise<void>;
  resolveAlert: (id: string | number, note?: string) => Promise<void>;
  reopenAlert: (id: string | number, reason: string) => Promise<void>;
  addAlertNote: (id: string | number, note: string) => Promise<void>;
  triggerReplayBurst: (patientId?: string) => Promise<void>;
  dismissToast: (id: number) => void;

  // Compatibility shims for legacy views
  running: boolean;
  tick: number;
  speed: 'slow' | 'normal' | 'fast';
  multiplier: 1 | 2;
  start: () => void;
  pause: () => void;
  reset: () => void;
  setSpeed: (s: 'slow' | 'normal' | 'fast') => void;
  setMultiplier: (m: 1 | 2) => void;
  acknowledge: (id: string) => void;
  undoAcknowledge: (id: string) => void;
  dataSource: 'demo' | 'api';
  setDataSource: (d: 'demo' | 'api') => void;
  theme: 'light' | 'dark';
  setTheme: (t: 'light' | 'dark') => void;
}
export const SimCtx = createContext<SimValue | null>(null);


