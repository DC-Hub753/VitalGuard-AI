import { APP_CONFIG } from './config.ts';

export interface RiskPredictionInput {
  patient_id: string;
  age: number;
  heart_rate: number;
  spo2: number;
  systolic_bp: number;
  diastolic_bp: number;
  temperature: number;
  respiratory_rate: number;
}
export interface RiskPredictionResult {
  patient_id: string;
  observation_id: number | null;
  created_at: string | null;
  risk_score: number;
  risk_level: 'low' | 'moderate' | 'high' | 'critical';
  model_probability: number;
  factors: Array<{ feature: string; observed_value: number; direction: 'increases-risk' | 'decreases-risk'; explanation: string }>;
  model_version: string;
  demo_only: true;
  disclaimer: string;
}
export interface ObservationRecord {
  id: number;
  patient_id: string;
  created_at: string;
  inputs: Omit<RiskPredictionInput, 'patient_id'>;
  prediction: RiskPredictionResult;
  model_version: string;
}
export interface ObservationHistory {
  items: ObservationRecord[];
  count: number;
  limit: number;
  next_before_id: number | null;
  demo_only: true;
  disclaimer: string;
}
const AUTH_STORAGE_KEY = 'vitalguard.operator.session';
function getAccessToken(): string | null {
  try {
    const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as { token?: string; expiresAt?: number };
    if (!session.token || !session.expiresAt || session.expiresAt <= Date.now()) { sessionStorage.removeItem(AUTH_STORAGE_KEY); return null; }
    return session.token;
  } catch { sessionStorage.removeItem(AUTH_STORAGE_KEY); return null; }
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getAccessToken();
  if (token) headers.set('Authorization', 'Bearer ' + token);
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(`${APP_CONFIG.apiBaseUrl}${path}`, {
    ...init,
    signal: AbortSignal.timeout(8000),
    headers,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(detail || `API request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}
async function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' });
}
export const api = {
  // Patients
  listPatients: (ward?: string, limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (ward && ward !== 'All') params.set('ward', ward);
    return get<{ items: Array<any>; count: number; total: number }>(`/api/v1/patients?${params.toString()}`);
  },
  getPatient: (id: string) => get<any>(`/api/v1/patients/${encodeURIComponent(id)}`),
  createPatient: (payload: { patient_id: string; display_name: string; sex?: string; ward?: string; bed?: string; date_of_birth?: string }) =>
    request<any>('/api/v1/patients', { method: 'POST', body: JSON.stringify(payload) }),
  updatePatient: (id: string, updates: Partial<{ display_name: string; ward: string; bed: string; active: boolean }>) =>
    request<any>(`/api/v1/patients/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(updates) }),
  deactivatePatient: (id: string) =>
    request<any>(`/api/v1/patients/${encodeURIComponent(id)}/deactivate`, { method: 'POST' }),

  // Prioritization & Alerts
  getPrioritization: (ward?: string, riskCategory?: string) => {
    const params = new URLSearchParams();
    if (ward && ward !== 'All') params.set('ward', ward);
    if (riskCategory && riskCategory !== 'All') params.set('risk_category', riskCategory);
    return get<{ items: Array<any>; count: number; total: number }>(`/api/v1/alerts/prioritization?${params.toString()}`);
  },
  listAlerts: (params?: { status?: string; severity?: string; patient_id?: string; limit?: number }) => {
    const search = new URLSearchParams({ limit: String(params?.limit ?? 100) });
    if (params?.status && params.status !== 'all') search.set('status', params.status);
    if (params?.severity && params.severity !== 'all') search.set('severity', params.severity);
    if (params?.patient_id) search.set('patient_id', params.patient_id);
    return get<{ items: Array<any>; count: number }>(`/api/v1/alerts?${search.toString()}`);
  },
  acknowledgeAlert: (id: string | number, note?: string) =>
    request<any>(`/api/v1/alerts/${id}/acknowledge`, { method: 'POST', body: JSON.stringify({ note }) }),
  assignAlert: (id: string | number, assignee: string, note?: string) =>
    request<any>(`/api/v1/alerts/${id}/assign`, { method: 'POST', body: JSON.stringify({ assignee, note }) }),
  resolveAlert: (id: string | number, note?: string) =>
    request<any>(`/api/v1/alerts/${id}/resolve`, { method: 'POST', body: JSON.stringify({ note }) }),
  reopenAlert: (id: string | number, reason: string) =>
    request<any>(`/api/v1/alerts/${id}/reopen`, { method: 'POST', body: JSON.stringify({ reason }) }),
  addAlertNote: (id: string | number, note: string) =>
    request<any>(`/api/v1/alerts/${id}/notes`, { method: 'POST', body: JSON.stringify({ note }) }),
  getAlertAudit: (id: string | number) =>
    get<{ items: Array<any>; count: number }>(`/api/v1/alerts/${id}/audit`),

  // Observations & Clinical scoring
  predictRisk: (input: RiskPredictionInput) =>
    request<RiskPredictionResult>('/api/v1/risk/predict', { method: 'POST', body: JSON.stringify(input) }),
  explainRisk: (input: RiskPredictionInput) =>
    request<any>('/api/v1/risk/explain', { method: 'POST', body: JSON.stringify(input) }),
  calculateNews2: (input: any) =>
    request<any>('/api/v1/scores/news2', { method: 'POST', body: JSON.stringify(input) }),
  listObservations: (patientId?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (patientId) params.set('patient_id', patientId);
    return get<ObservationHistory>(`/api/v1/observations?${params.toString()}`);
  },
  getObservationTrends: (patientId: string) =>
    get<any>(`/api/v1/observations/trends?patient_id=${encodeURIComponent(patientId)}`),
  getPatientTimeline: (patientId: string, limit = 50) =>
    get<any>(`/api/v1/patients/${encodeURIComponent(patientId)}/timeline?limit=${limit}`),
  getDataQuality: () =>
    get<any>('/api/v1/observations/quality'),

  // Historical replay ingestion for controlled QA
  ingestReplayBatch: (items: any[]) =>
    request<any>('/api/v1/ingestion/replay', {
      method: 'POST',
      body: JSON.stringify({ source_name: 'vitalguard-qa-replay', records: items }),
    }),

  health: () => get<{ status: string; model_version: string; demo_only: boolean }>('/health'),
};
