const js = require('@eslint/js')
const typescriptEslint = require('@typescript-eslint/eslint-plugin')
const typescriptParser = require('@typescript-eslint/parser')
const reactHooks = require('eslint-plugin-react-hooks')

module.exports = [
  {
    ignores: ['dist/', 'dist-electron/', 'dist-frontend/', 'dist-tests/', 'release/', 'node_modules/', '*.config.*'],
  },
  js.configs.recommended,
  {
    files: ['src/renderer/**/*.{ts,tsx}'],
    languageOptions: {
      parser: typescriptParser,
      ecmaVersion: 2020,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        console: 'readonly',
        performance: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
      },
      parserOptions: {
        project: './tsconfig.json',
        tsconfigRootDir: __dirname,
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: '18.2' },
    },
    plugins: {
      '@typescript-eslint': typescriptEslint,
      'react-hooks': reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
  {
    files: ['src/main.ts', 'src/preload.ts', 'src/reminderEvents.ts', 'src/processLifecycle.ts'],
    languageOptions: {
      parser: typescriptParser,
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        __dirname: 'readonly',
        console: 'readonly',
        process: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
      },
      parserOptions: {
        project: './tsconfig.node.json',
        tsconfigRootDir: __dirname,
      },
    },
    plugins: {
      '@typescript-eslint': typescriptEslint,
    },
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
]
