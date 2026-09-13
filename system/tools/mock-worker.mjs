import { createClient } from '@supabase/supabase-js';
import { startMockWorker } from './mock-processing.mjs';

// Node 22: npm run mock-worker -- supports .env.local via explicit loading here.
try { process.loadEnvFile('.env.local'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
if (process.env.NYS_MOCK_WORKER !== 'true') throw new Error('Set NYS_MOCK_WORKER=true explicitly. This worker writes TEST results.');
const { SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY } = process.env;
if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) throw new Error('Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY');
const client = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, { auth: { persistSession: false, autoRefreshToken: false } });
const stop = startMockWorker(async (name, args) => {
  const { data, error } = await client.rpc(name, args);
  if (error) throw new Error(error.message);
  return data;
});
console.log('MOCK worker active. No camera, OCR, or AI calls.');
process.on('SIGINT', async () => { await stop(); process.exit(0); });
