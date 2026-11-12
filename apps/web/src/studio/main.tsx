// The studio's page: mounts the app into #app.

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../common/styles/tokens.css';
import '../common/styles/themes.css';
import '../common/styles/base.css';
// In the order of the stylesheet they were one of: where two rules weigh the same, the later one wins.
import '../common/components/Shared.module.css';
import '../common/components/Shared2.module.css';
import '../common/components/Shared3.module.css';
import '../common/components/Shared4.module.css';
import '../common/landing/Landing.module.css';
import '../common/landing/Landing2.module.css';
import '../common/landing/Landing3.module.css';
import '../common/landing/Landing4.module.css';
import '../common/landing/Landing5.module.css';
import '../common/landing/Landing6.module.css';
import '../common/landing/Landing7.module.css';
import '../common/landing/Landing8.module.css';
import { App, createRouter, makeQueryClient } from './App';

// A page opened before the studio was built again asks for files the new build no longer has: load the new build, once
// (a second failure within a minute is a real one, and shows).
window.addEventListener('vite:preloadError', (e) => {
  try {
    const last = Number(sessionStorage.getItem('scene.reloaded') || 0);
    if (Date.now() - last < 60_000) return;
    sessionStorage.setItem('scene.reloaded', String(Date.now()));
  } catch {
    // no storage: reload anyway
  }
  e.preventDefault();
  window.location.reload();
});

const router = createRouter();
const client = makeQueryClient();

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App client={client} router={router} />
  </StrictMode>,
);
