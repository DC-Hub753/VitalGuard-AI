import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/config.ts', () => ({
  APP_CONFIG: { apiBaseUrl: 'https://api.example.test' },
}));
vi.mock('../services/authenticatedFetch.ts', () => ({
  getOperatorAccessToken: () => 'test-token',
  authorizedFetch: vi.fn(),
}));

import { createLiveSocket } from '../services/liveEvents.ts';

class FakeWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];
  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string, public protocols?: string[]) {
    FakeWebSocket.instances.push(this);
  }

  send(value: string) {
    this.sent.push(value);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
}

describe('createLiveSocket reliability', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('backs off after repeated short-lived connections instead of resetting on every open', () => {
    const statuses: string[] = [];
    const stop = createLiveSocket(() => undefined, (status) => statuses.push(status));

    const first = FakeWebSocket.instances[0];
    first.open();
    first.close();
    expect(statuses[statuses.length - 1]).toBe('reconnecting');

    vi.advanceTimersByTime(1000);
    const second = FakeWebSocket.instances[1];
    expect(second).toBeDefined();
    second.open();
    second.close();

    const countBeforeDelay = FakeWebSocket.instances.length;
    vi.advanceTimersByTime(1999);
    expect(FakeWebSocket.instances).toHaveLength(countBeforeDelay);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(countBeforeDelay + 1);

    stop();
  });

  it('closes a connection when heartbeat replies stop arriving', () => {
    const stop = createLiveSocket(() => undefined, () => undefined);
    const socket = FakeWebSocket.instances[0];
    socket.open();

    vi.advanceTimersByTime(25000);
    expect(socket.sent).toContain('ping');

    vi.advanceTimersByTime(50000);
    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);
    stop();
  });
});
