// The console's sections, one per address (/overview, /users, /jobs…). `live`: how often the section is asked again
// while it is open, in ms. `group` is the heading it sits under in the sidebar.

import type { ComponentType } from 'react';
import type { IconName } from '../common/components/Icon/Icon';
import Agent from './sections/agent/Agent';
import Audit from './sections/audit/Audit';
import Credits from './sections/credits/Credits';
import Economics from './sections/economics/Economics';
import Jobs from './sections/jobs/Jobs';
import Library from './sections/library/Library';
import Moderation from './sections/moderation/Moderation';
import Overview from './sections/overview/Overview';
import Pricing from './sections/pricing/Pricing';
import Projects from './sections/projects/Projects';
import Roles from './sections/roles/Roles';
import Servers from './sections/servers/Servers';
import Sessions from './sections/sessions/Sessions';
import Settings from './sections/settings/Settings';
import Showcase from './sections/showcase/Showcase';
import Skills from './sections/skills/Skills';
import System from './sections/system/System';
import Users from './sections/users/Users';
import Workflows from './sections/workflows/Workflows';

export type Section = {
  id: string;
  label: string;
  icon: IconName;
  Component: ComponentType;
  live?: number;
  group: string;
};

export const SECTIONS: Section[] = [
  { id: 'overview', label: 'Overview', icon: 'home', Component: Overview, live: 15000, group: 'Live' },
  { id: 'jobs', label: 'Jobs', icon: 'clock', Component: Jobs, live: 5000, group: 'Live' },
  { id: 'system', label: 'System', icon: 'bolt', Component: System, live: 10000, group: 'Live' },
  { id: 'sessions', label: 'Sessions', icon: 'chat', Component: Sessions, group: 'Live' },
  { id: 'users', label: 'Users', icon: 'eye', Component: Users, group: 'People' },
  { id: 'credits', label: 'Credits', icon: 'gem', Component: Credits, group: 'People' },
  { id: 'library', label: 'Library', icon: 'grid', Component: Library, group: 'People' },
  { id: 'projects', label: 'Projects', icon: 'folder', Component: Projects, group: 'People' },
  { id: 'moderation', label: 'Moderation', icon: 'shield', Component: Moderation, group: 'People' },
  { id: 'pricing', label: 'Pricing', icon: 'sliders', Component: Pricing, group: 'Money' },
  { id: 'economics', label: 'Economics', icon: 'bars', Component: Economics, group: 'Money' },
  { id: 'workflows', label: 'Workflows', icon: 'frame', Component: Workflows, group: 'Studio' },
  { id: 'agent', label: 'Agent', icon: 'chat', Component: Agent, group: 'Studio' },
  { id: 'skills', label: 'Skills', icon: 'skill', Component: Skills, group: 'Studio' },
  { id: 'showcase', label: 'Home page', icon: 'home', Component: Showcase, group: 'Studio' },
  { id: 'endpoints', label: 'Servers', icon: 'server', Component: Servers, group: 'Studio' },
  { id: 'roles', label: 'Roles', icon: 'people', Component: Roles, group: 'Records' },
  { id: 'audit', label: 'Audit log', icon: 'book', Component: Audit, group: 'Records' },
  { id: 'settings', label: 'Settings', icon: 'wrench', Component: Settings, group: 'Records' },
];

export const FIRST = '/overview';
