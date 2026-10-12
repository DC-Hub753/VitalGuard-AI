export type RiskLevel = 'critical' | 'high' | 'moderate' | 'low';
export type TrendDirection = 'worsening' | 'stable' | 'recovering';
export type Scenario = 'stable' | 'worsening' | 'recovering';
export type Ward = 'ICU' | 'Emergency' | 'General Ward' | 'Cardiology';

export interface Patient {
  id: string;
  displayName?: string;
  age: number;
  sex: 'M' | 'F' | 'U';
  ward: Ward;
  bed: string;
  scenario: Scenario;
  active?: boolean;
  dateOfBirth?: string | null;
  updatedAt: string;
}

export interface VitalReading {
  patientId: string;
  timestamp: string;
  heartRate: number;
  spo2: number;
  systolicBp: number;
  diastolicBp: number;
  temperature: number;
  respiratoryRate: number;
}

export interface RiskSignal {
  patientId: string;
  score: number;
  level: RiskLevel;
  probability: number;
  news2: number;
  trend: TrendDirection;
  trajectory: number[];
  trajectoryLabels: string[];
  updatedAt: string;
}

export interface RiskFactor {
  patientId: string;
  name: string;
  contribution: number;
  direction: 'increases-risk' | 'decreases-risk';
  currentValue: string;
  trend: string;
  description: string;
}

export type AlertSeverity = 'critical' | 'high' | 'moderate' | 'info';
export type AlertStatus = 'open' | 'acknowledged' | 'assigned' | 'resolved' | 'reopened';

export interface AlertNote {
  note: string;
  actor: string;
  created_at: string;
}

export interface AlertItem {
  id: string;
  patientId: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  contributors: string[];
  status: AlertStatus;
  createdAt: string;
  alertType?: 'clinical_rule' | 'ml_derived' | 'trend_warning' | 'data_quality' | string;
  assignedTo?: string | null;
  assignedAt?: string | null;
  deadlineMinutes?: number | null;
  ageMinutes?: number;
  isOverdue?: boolean;
  notes?: AlertNote[];
  riskBefore?: number;
  riskAfter?: number;
}

export interface PrioritizedPatient {
  patient_id: string;
  display_name: string;
  ward: string;
  bed: string;
  priority_rank: number;
  risk_category: string;
  news2_score: number | null;
  ml_risk: number | null;
  active_alerts_count: number;
  critical_alerts_count: number;
  needs_review: boolean;
  review_reasons: string[];
  stale_status: string;
  last_observed_at: string | null;
}

export interface SimulationState {
  running: boolean;
  tick: number;
  speed: 'slow' | 'normal' | 'fast';
  multiplier: 1 | 2;
}

export const DEMO_DISCLAIMER = 'All patient data shown in Demo Mode is synthetic and intended only for software demonstration.';

