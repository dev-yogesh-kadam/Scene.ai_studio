// ESLint for the client apps: apps/web (studio + console), apps/mobile (phone site) and packages/shared.
// The classic frontend/ is not linted: it is frozen to bug fixes and goes away after the switch to apps/web.

import js from '@eslint/js';
import noUnsanitized from 'eslint-plugin-no-unsanitized';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      '**/node_modules/**',
      '**/dist/**',
      '**/.expo/**',
      'apps/mobile/expo-env.d.ts',
      'apps/web/public/**', // theme.js is a classic script, copied from the classic frontend as it is
      'apps/web/test-results/**',
      'apps/web/playwright-report/**',
      // Not client code, or not this workspace's
      'frontend/**',
      'backend/**',
      'motion/**',
      'workflows/**',
      'docs/**',
      'content/**',
      'scripts/**',
      'storage/**',
      '.venv/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx,js,mjs,cjs}'],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],
    },
  },
  // Config files and scripts that run in Node
  {
    files: [
      '*.config.{js,mjs,ts}',
      'apps/*/*.config.{js,ts}',
      'apps/web/vite.*.ts',
      'apps/*/jest.*.js',
      'apps/*/scripts/**',
      'apps/web/tests/**',
      'packages/shared/tokens/*.mjs',
    ],
    languageOptions: { globals: { ...globals.node } },
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
  // React apps: the rules of hooks
  {
    files: ['apps/**/*.{ts,tsx}', 'packages/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: { ...reactHooks.configs.recommended.rules },
  },
  // The web studio and the shared package: no HTML written as text into the page (X1), and promises always handled.
  {
    files: ['apps/web/src/**/*.{ts,tsx}', 'packages/shared/src/**/*.ts'],
    plugins: { 'no-unsanitized': noUnsanitized },
    languageOptions: { parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname } },
    rules: {
      'no-unsanitized/method': 'error',
      'no-unsanitized/property': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': ['error', { checksVoidReturn: { attributes: false } }],
    },
  },
  // The web studio's hand-drawn modules (the landing page's monitor) are JavaScript: no HTML written as text there either.
  {
    files: ['apps/web/src/**/*.js'],
    plugins: { 'no-unsanitized': noUnsanitized },
    rules: { 'no-unsanitized/method': 'error', 'no-unsanitized/property': 'error' },
  },
  // The phone site, linted for the first time when it moved here. React Native's ways stay allowed: images are
  // require()d, Reanimated's shared values are assigned (`offset.value = ...`, which the React Compiler rules read as
  // mutating a prop), and list callbacks name arguments they don't use. Its effects that set state on mount are
  // behaviour this move does not change. The rules of hooks and exhaustive deps stay on.
  {
    files: ['apps/mobile/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { args: 'none', varsIgnorePattern: '^_', caughtErrors: 'none' }],
      'react-hooks/immutability': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
    },
  },
  // Tests run under Jest (phone site) or Vitest (web)
  {
    files: ['apps/mobile/__tests__/**', 'apps/mobile/jest.*.js'],
    languageOptions: { globals: { ...globals.jest, ...globals.node } },
  },
);
