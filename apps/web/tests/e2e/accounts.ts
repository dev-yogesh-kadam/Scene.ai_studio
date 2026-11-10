// The accounts the end-to-end tests use, made by global-setup.ts in the tests' own database. The first is the admin.

export const ACCOUNTS = {
  admin: { email: 'e2e-admin@local.test', name: 'E2E admin', password: 'E2E-test-2026-pass' },
  user: { email: 'e2e-user@local.test', name: 'E2E user', password: 'E2E-test-2026-pass' },
};
