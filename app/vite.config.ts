import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// Offline rule: the built bundle must not contain remote URLs. React's production
// build embeds two documentation links in its error messages (text only, never
// fetched); this plugin turns them into plain text. W3C XML namespace URIs
// (e.g. the SVG namespace) are identifiers required to render SVG and are kept.
function stripVendorDocUrls(): Plugin {
  return {
    name: 'astrocare-strip-vendor-doc-urls',
    apply: 'build',
    generateBundle(_options, bundle) {
      for (const file of Object.values(bundle)) {
        if (file.type !== 'chunk') continue;
        file.code = file.code
          .replace(/https:\/\/reactjs\.org\/docs\/error-decoder\.html/g, 'reactjs.org/docs/error-decoder.html')
          .replace(/http:\/\/fb\.me\//g, 'fb.me/');
      }
    },
  };
}

// Dev: Vite on :5173 proxies /api to the local FastAPI server on :8000.
// Prod: `npm run build` writes app/dist, served by FastAPI (`npm run start`).
export default defineConfig({
  plugins: [react(), stripVendorDocUrls()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
});
