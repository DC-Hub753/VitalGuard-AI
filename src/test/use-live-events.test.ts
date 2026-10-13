import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const handlers = vi.hoisted(() => ({
  onEvent: null as null | ((event: any) => void),
  onStatus: null as null | ((status: 'connecting' | 'connected' | 'reconnecting' | 'offline') => void),
}));

vi.mock('../services/liveEvents.ts', () => ({
  createLiveSocket: vi.fn((onEvent: typeof handlers.onEvent, onStatus: typeof handlers.onStatus) => {
    handlers.onEvent = onEvent;
    handlers.onStatus = onStatus;
    return () => undefined;
  }),
}));

import { useLiveEvents } from '../services/useLiveEvents.ts';

describe('useLiveEvents', () => {
  beforeEach(() => {
    handlers.onEvent = null;
    handlers.onStatus = null;
  });

  afterEach(() => vi.clearAllMocks());

  it('counts alert updates as live events', () => {
    const { result } = renderHook(() => useLiveEvents());

    act(() => {
      handlers.onEvent?.({
        type: 'alert.updated',
        alert: {
          id: 17,
          patient_id: 'P-SIM-001',
          title: 'Review required',
          severity: 'high',
          status: 'acknowledged',
          created_at: '2026-10-14T00:00:00Z',
        },
      });
    });

    expect(result.current.eventCount).toBe(1);
    expect(result.current.lastEvent?.type).toBe('alert.updated');
  });

  it('does not count control frames as clinical events', () => {
    const { result } = renderHook(() => useLiveEvents());

    act(() => {
      handlers.onEvent?.({ type: 'pong' });
    });

    expect(result.current.eventCount).toBe(0);
    expect(result.current.lastEvent).toBeNull();
  });
});
