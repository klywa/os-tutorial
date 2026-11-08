import {defineConfig} from 'vite';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';

const instanceId=randomUUID();

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
      server.middlewares.use('/__wxq_local_frontend', async (request, response, next) => {
        if (request.method === 'GET') {
          response.setHeader('Content-Type', 'application/json');
          response.end(JSON.stringify({root: server.config.root,mode:'local',port:server.config.server.port,
            pid:process.pid,instance_id:instanceId}));
        } else if (request.method === 'POST' && request.url === '/stop'
          && request.headers.host === `127.0.0.1:${server.config.server.port}`
          && (!request.headers.origin || request.headers.origin === `http://127.0.0.1:${server.config.server.port}`)) {
          try {
            let control;
            try {control=JSON.parse(readFileSync(resolve(server.config.root,'../raw/local-services/control.json'),'utf8'));}
            catch(error) {if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
            if(control && request.headers['x-wxq-supervisor']!==control.instance_id) {
              const result=await fetch(`http://127.0.0.1:${control.port}/pause`,{method:'POST',
                headers:{Authorization:`Bearer ${control.token}`,'Content-Type':'application/json'},
                body:JSON.stringify({services:['frontend'],reason:'explicit_stop'})});
              if(!result.ok)throw new Error('manager pause failed');
            }
            response.statusCode=202;response.end('{}');
            setTimeout(()=>{void server.close().then(()=>process.exit(0));},50);
          } catch {
            response.statusCode=503;response.end('{}');
          }
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
