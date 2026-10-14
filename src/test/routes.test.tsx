import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SimulationProvider } from '../store/SimulationContext.tsx';
import { AuthProvider } from '../store/AuthContext.tsx';
import { DashboardPage } from '../pages/DashboardPage.tsx';
import { AlertsPage } from '../pages/AlertsPage.tsx';
import { AnalyticsPage } from '../pages/AnalyticsPage.tsx';
import { SettingsPage } from '../pages/SettingsPage.tsx';
import { PatientsPage } from '../pages/PatientsPage.tsx';
import { PatientDetailPage } from '../pages/PatientDetailPage.tsx';
import { NotFoundPage } from '../pages/NotFoundPage.tsx';
import { formatTimeAgo } from '../utils/format.ts';
import { RISK_STYLES, CHART_COLORS } from '../theme/tokens.ts';
function wrap(ui: React.ReactNode, route = '/dashboard') {
  return render(<AuthProvider><SimulationProvider><MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter></SimulationProvider></AuthProvider>);
}
function wrapRouted(route = '/patients/P-SIM-003') {
  return render(
    <AuthProvider>
      <SimulationProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/patients/:patientId" element={<PatientDetailPage />} />
            <Route path="*" element={<PatientDetailPage />} />
          </Routes>
        </MemoryRouter>
      </SimulationProvider>
    </AuthProvider>,
  );
}
describe('routes render', () => {
  it('dashboard renders hero + queue', () => {
    wrap(<DashboardPage />);
    expect(screen.getByText('Patient Monitoring Overview')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Review priority patient/ })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Patient priority queue' })).toBeTruthy();
  });
  it('patient list renders + filters + view toggle', () => {
    wrap(<PatientsPage />);
    expect(screen.getAllByRole('heading', { name: 'Patients' }).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Search patient ID')).toBeTruthy();
    expect(screen.getByLabelText('View mode')).toBeTruthy();
  });
  it('search filters the directory', () => {
    wrap(<PatientsPage />);
    fireEvent.change(screen.getByLabelText('Search patient ID'), { target: { value: 'P-SIM-003' } });
    expect(screen.getByLabelText('Search patient ID')).toHaveValue('P-SIM-003');
  });
  it('patient detail renders vitals + risk + NEWS2 + explanation + timeline', () => {
    wrapRouted('/patients/P-SIM-003');
    expect(screen.getByText('No patient P-SIM-003 found.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Back to directory' })).toBeTruthy();
  });
  it('alerts page works + acknowledge', () => {
    wrap(<AlertsPage />);
    expect(screen.getByRole('heading', { name: 'Alert Operations Center' })).toBeTruthy();
    expect(screen.getByRole('tablist', { name: 'Alert status filter' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'All Alerts' })).toBeTruthy();
  });
  
it('dashboard shows live telemetry without replay and history panels', () => {
  wrap(<DashboardPage />);
  expect(screen.getByText(/LIVE TELEMETRY/)).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Patient Monitoring Overview' })).toBeTruthy();
  expect(screen.queryByText('Observation data quality')).toBeNull();
  expect(screen.queryByText('Historical Replay (QA)')).toBeNull();
  expect(screen.queryByText('Observation history')).toBeNull();
});

  it('analytics renders', () => { wrap(<AnalyticsPage />); expect(screen.getAllByText('Analytics').length).toBeGreaterThan(0); expect(screen.getByText('DEMO ANALYTICS')).toBeTruthy(); });
  it('settings renders + theme switching', () => {
    wrap(<SettingsPage />);
    expect(screen.getAllByRole('heading', { name: 'Settings' }).length).toBeGreaterThan(0);
    const themeGroup = screen.getByRole('group', { name: 'Theme' });
    const darkBtn = themeGroup.querySelector('button:nth-child(2)') as HTMLElement;
    fireEvent.click(darkBtn);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    const lightBtn = themeGroup.querySelector('button:nth-child(1)') as HTMLElement;
    fireEvent.click(lightBtn);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
  it('mobile navigation renders', () => {
    wrap(<DashboardPage />);
    expect(screen.getAllByLabelText('Open navigation menu').length).toBeGreaterThan(0);
  });
  it('unknown route works', () => { wrap(<NotFoundPage />); expect(screen.getAllByText('404').length).toBeGreaterThan(0); });
  it('formatting helpers + centralized tokens', () => {
    expect(formatTimeAgo(new Date().toISOString())).toBe('Just now');
    expect(formatTimeAgo(new Date(Date.now() - 120000).toISOString())).toBe('2 min ago');
    expect(RISK_STYLES.high).toBeTruthy();
    expect(CHART_COLORS.spo2).toBe('#2563eb');
  });
});
