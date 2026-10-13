import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { DataQualityPanel } from '../components/dashboard/DataQualityPanel.tsx';
import { BackendObservationHistory } from '../components/dashboard/BackendObservationHistory.tsx';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('does not request observation quality when the operator session is missing', async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);

  render(<DataQualityPanel />);

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent(/session is missing or expired/i);
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

it('does not request observation history when the operator session is missing', async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);

  render(<BackendObservationHistory />);

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent(/session is missing or expired/i);
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

it('does not request protected dashboard data when the stored session has expired', async () => {
  sessionStorage.setItem('vitalguard.operator.session', JSON.stringify({
    token: 'expired-demo-token',
    expiresAt: Date.now() - 1000,
  }));
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);

  render(
    <>
      <DataQualityPanel />
      <BackendObservationHistory />
    </>,
  );

  await waitFor(() => {
    expect(screen.getAllByRole('alert')).toHaveLength(2);
  });
  expect(fetchMock).not.toHaveBeenCalled();
  expect(sessionStorage.getItem('vitalguard.operator.session')).toBeNull();
});
