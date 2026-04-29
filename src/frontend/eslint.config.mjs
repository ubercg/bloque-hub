import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';

export default defineConfig([
  ...nextVitals,
  globalIgnores(['.next/**', 'node_modules/**', 'playwright-report/**', 'test-results/**']),
  {
    rules: {
      // Reglas nuevas de React Compiler / hooks: el código legado las incumple; revisar gradualmente.
      'react-hooks/set-state-in-effect': 'off',
      'react/no-unescaped-entities': 'warn',
    },
  },
  {
    files: ['app/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: [
                '@/features/*/components/**',
                '@/features/*/store/**',
                '@/features/*/lib/**',
              ],
              message:
                'Importa solo la API pública: `@/features/<nombre>` (index). Middleware puede usar `@/features/*/server/*`.',
            },
          ],
        },
      ],
    },
  },
]);
