import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App.tsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
);

// Register the service worker only in production. API/auth responses are excluded
// from its cache so sensitive patient data is not persisted by the offline layer.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      console.error('VitalGuard service worker registration failed:', error);
    });
  });
}
