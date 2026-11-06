import {defineConfig} from 'vite';

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    open: false,
    proxy: {'/api': 'http://127.0.0.1:8765'},
  },
  plugins: [{
    name: 'wxq-local-frontend',
    configureServer(server) {
      server.middlewares.use('/__wxq_local_frontend', (request, response, next) => {
        if (request.method === 'GET') {
          response.setHeader('Content-Type', 'application/json');
          response.end(JSON.stringify({root: server.config.root}));
        } else if (request.method === 'POST' && request.headers.host === '127.0.0.1:5173'
          && !request.headers.origin && request.headers['x-wxq-refresh'] === '1') {
          server.ws.send({type: 'full-reload', path: '*'});
          response.statusCode = 204;
          response.end();
        } else {
          next();
        }
      });
    },
  }],
});
