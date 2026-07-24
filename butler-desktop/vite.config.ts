import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { createRequire } from 'node:module';
import { loadProductionBuildContext } from './build/loadBuildContext';

const requireJson = createRequire(import.meta.url);
const pkg = requireJson('./package.json') as { version: string };

export default defineConfig(({ mode }) => {
  const production = mode === 'production';
  const loaded = production ? loadProductionBuildContext(process.env.BUTLER_BUILD_CONTEXT_PATH) : null;
  const commit = loaded?.context.commit_oid.slice(0, 12) ?? 'development';
  const contextDigest = loaded?.digest ?? 'development';

  return {
    plugins: [react()],
    clearScreen: false,
    define: {
      __BUILD_COMMIT__: JSON.stringify(commit),
      __BUILD_BRANCH__: JSON.stringify(production ? 'production' : 'development'),
      __BUILD_CHANNEL__: JSON.stringify(production ? 'production' : 'development'),
      __BUILD_CONTEXT_DIGEST__: JSON.stringify(contextDigest),
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
    server: { port: 1420, strictPort: true },
    test: {
      exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
      globals: false,
      environment: 'jsdom',
      environmentOptions: {
        jsdom: {
          url: 'http://127.0.0.1:8765/',
        },
      },
      setupFiles: ['./src/test-setup.ts'],
    },
  };
});
