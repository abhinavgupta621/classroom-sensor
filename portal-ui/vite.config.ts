import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Built into ../data/portal/app (never committed) and served by analysis/portal.py, which
// also serves the data (/api), images (/media, /photos) and the live frame (/frame).
// `npm run dev` proxies those to the running portal on 8790.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  build: { outDir: '../data/portal/app', emptyOutDir: true },
  server: {
    port: 5190,
    proxy: Object.fromEntries(['/api', '/media', '/photos', '/frame', '/status'].map((p) => [p, 'http://127.0.0.1:8790'])),
  },
});
