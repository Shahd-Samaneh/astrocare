import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // Offline rule: no remote URLs in code. Localhost is allowed.
      'no-restricted-syntax': [
        'error',
        {
          selector: "Literal[value=/^https?:\\/\\/(?!localhost|127\\.0\\.0\\.1)/]",
          message: 'AstroCare must work offline: no remote URLs (bundle assets locally).',
        },
      ],
    },
  },
);
