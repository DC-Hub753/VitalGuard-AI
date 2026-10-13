const host = typeof window !== 'undefined' ? (window.location.hostname || '127.0.0.1') : '127.0.0.1';
const defaultApiBaseUrl = import.meta.env.PROD
  ? 'https://vitalguard-risk-api-dc.onrender.com'
  : `http://${host === 'localhost' ? '127.0.0.1' : host}:8000`;

export const APP_CONFIG = {
  demoMode: (import.meta.env.VITE_DEMO_MODE ?? 'true') !== 'false',
  apiBaseUrl: ((import.meta.env.VITE_API_BASE_URL as string) || defaultApiBaseUrl).replace(/\/$/, ''),
  version: (import.meta.env.VITE_APP_VERSION as string) || '0.2.0-demo',
  env: import.meta.env.MODE || 'development',
};
