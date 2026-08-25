import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
// vitest/config re-exports Vite's defineConfig with the `test` key added.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Vite does not read tsconfig `paths`, so the alias is declared in both
  // places. They must agree or the build resolves imports the typechecker
  // accepted.
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // The session cookie is SameSite=Lax, which browsers will not attach to
    // cross-site requests. Proxying /api through the dev server makes the API
    // same-origin with the app, so the cookie travels and no CSRF token
    // plumbing is needed. Production does the same thing with one reverse
    // proxy. Calling the backend directly on :8000 would appear to work until
    // the first authenticated request silently arrived without a cookie.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
});
