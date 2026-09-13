import { createServer } from 'node:http';
import { mkdir, writeFile } from 'node:fs/promises';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { resolve } from 'node:path';
import { createServer as createViteServer } from 'vite';
import { openDatabase, rpc, RPC_ARGUMENTS } from './database.mjs';
import { startMockWorker } from './mock-processing.mjs';

// Intentionally loopback-only: local demo authentication trusts a browser UUID.
// Never expose this server to a LAN or use it as the exhibition server.
const port = Number(process.env.PORT ?? 5173);
const tdMode = process.argv.includes('--td');
const bridgeToken = tdMode ? randomBytes(32).toString('hex') : '';
await mkdir('runtime', { recursive: true });
if (tdMode) await writeFile('runtime/demo-bridge.json', JSON.stringify({ url: `http://127.0.0.1:${port}/demo/bridge`, token: bridgeToken }));
const db = await openDatabase(resolve('runtime/demo-db'));
const vite = await createViteServer({
  server: { middlewareMode: true },
  appType: 'spa',
  define: { 'import.meta.env.VITE_DEMO': JSON.stringify('true') },
});
const stopWorker = tdMode ? async () => {} : startMockWorker((name, args) => rpc(db, null, name, args, 'service_role'));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const server = createServer(async (req, res) => {
  if (!req.url?.startsWith('/demo/')) return vite.middlewares(req, res);
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  const send = (status, body) => { res.writeHead(status); res.end(JSON.stringify(body)); };
  const bridgeRequest = req.url === '/demo/bridge';
  if (req.method !== 'POST' || (!bridgeRequest && req.url !== '/demo/rpc')) return send(404, { error: 'NOT_FOUND' });
  const origin = req.headers.origin;
  if (origin && origin !== `http://127.0.0.1:${port}` && origin !== `http://localhost:${port}`) return send(403, { error: 'FORBIDDEN' });
  const user = req.headers['x-demo-user'];
  if (bridgeRequest) {
    const supplied = Buffer.from(String(req.headers['x-demo-bridge'] ?? ''));
    const expected = Buffer.from(bridgeToken);
    if (!tdMode || origin || supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return send(403, { error: 'FORBIDDEN' });
  } else if (typeof user !== 'string' || !uuid.test(user)) return send(401, { error: 'FORBIDDEN' });
  try {
    let body = '';
    for await (const chunk of req) {
      body += chunk;
      if (body.length > 16384) return send(413, { error: 'TOO_LARGE' });
    }
    const { name, args } = JSON.parse(body);
    const localRpcs = ['nys_local_state', 'nys_td_claim', 'nys_worker_finish'];
    if (!Object.hasOwn(RPC_ARGUMENTS, name) || (bridgeRequest ? !localRpcs.includes(name) : name.startsWith('nys_worker_') || localRpcs.includes(name))) return send(403, { error: 'FORBIDDEN' });
    const data = await rpc(db, bridgeRequest ? null : user, name, args, bridgeRequest ? 'service_role' : 'authenticated');
    send(200, { data });
  } catch (error) { send(400, { error: error.message }); }
});
server.listen(port, '127.0.0.1', () => console.log(`Local demo: http://127.0.0.1:${port}/operator (${tdMode ? 'TD bridge mode; no automatic mock worker' : 'mock processing'})`));
let closing = false;
async function shutdown() {
  if (closing) return;
  closing = true;
  server.close();
  await stopWorker();
  await vite.close();
  await db.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
