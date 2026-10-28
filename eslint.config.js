import js from '@eslint/js';
import globals from 'globals';
import ts from 'typescript-eslint';

export default ts.config(
  { ignores: [
    'dist/**', 'node_modules/**', 'artifacts/**', '.venv/**',
    '.generated/**', 'test-results/**', 'playwright-report/**',
  ] },
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      'max-len': ['error', { code: 80, ignoreUrls: true }],
      'max-lines': ['error', 1000],
      'max-lines-per-function': ['error', {
        max: 40,
        skipBlankLines: true,
        skipComments: true,
      }],
      'max-params': ['error', 7],
      complexity: ['error', 10],
    },
  },
);
