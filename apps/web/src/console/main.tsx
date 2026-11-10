// The admin console's page: mounts the console into #app. Served on the console's own port only.

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
import { App } from './App';

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
