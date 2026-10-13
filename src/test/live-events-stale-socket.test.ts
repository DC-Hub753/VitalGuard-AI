import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/config.ts', () => ({ APP_CONFIG: { apiBaseUrl: 'https://api.example.test' } }));
vi.mock('../services/authenticatedFetch.ts', () => ({ getOperatorAccessToken: () => 'test-token', authorizedFetch: vi.fn() }));
import { createLiveSocket } from '../services/liveEvents.ts';

class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  constructor() { FakeSocket.instances.push(this); }
  send() {}
  open() { this.readyState = FakeSocket.OPEN; this.onopen?.(); }
  close() { this.readyState = 3; this.onclose?.(); }
}

describe('stale live socket callbacks', () => {
  beforeEach(() => { vi.useFakeTimers(); FakeSocket.instances = []; vi.stubGlobal('WebSocket', FakeSocket); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

  it('does not let an old socket error close the replacement connection', () => {
    const stop = createLiveSocket(() => undefined, () => undefined);
    const first = FakeSocket.instances[0];
    first.open();
    first.close();
    vi.advanceTimersByTime(1000);
    const second = FakeSocket.instances[1];
    second.open();
    first.onerror?.();
    expect(second.readyState).toBe(FakeSocket.OPEN);
    const count = FakeSocket.instances.length;
    vi.advanceTimersByTime(5000);
    expect(FakeSocket.instances).toHaveLength(count);
    expect(second.readyState).toBe(FakeSocket.OPEN);
    stop();
  });
});
