import { defineConfig, loadEnv } from 'vite';
export default defineConfig(({mode}) => ({ server: { proxy: {
  '/api': loadEnv(mode, '.', 'WXQ_').WXQ_API_TARGET || 'http://127.0.0.1:8765',
} } }));
