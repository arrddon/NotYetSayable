import { PGlite } from '@electric-sql/pglite';
import { readFile } from 'node:fs/promises';

export const OPERATOR_ID = '00000000-0000-4000-8000-000000000001';
const migration = new URL('../supabase/migrations/202609130001_core.sql', import.meta.url);

export async function openDatabase(dataDir) {
  const db = new PGlite(dataDir);
  const { rows } = await db.query("select to_regclass('public.participants') as existing");
  if (!rows[0].existing) {
    // Local-only substitutes for Supabase Auth. The production migration never creates these.
    await db.exec(`
      create role anon; create role authenticated; create role service_role;
      create schema auth;
      create function auth.uid() returns uuid language sql stable as
        $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
      create function auth.role() returns text language sql stable as
        $$ select current_setting('request.jwt.claim.role', true) $$;
      grant usage on schema public, auth to anon, authenticated, service_role;
      grant execute on all functions in schema auth to anon, authenticated, service_role;
    `);
    await db.exec(await readFile(migration, 'utf8'));
    await db.query('insert into nys_private.operators values ($1)', [OPERATOR_ID]);
  }
  const bridge = await db.query("select to_regprocedure('public.nys_local_state(uuid)') as existing");
  if (!bridge.rows[0].existing) await db.exec(await readFile(new URL('../supabase/migrations/202609130002_td_bridge.sql', import.meta.url), 'utf8'));
  return db;
}

export const RPC_ARGUMENTS = {
  nys_is_operator: [],
  nys_snapshot: ['p_id'],
  nys_join: ['p_token'],
  nys_create_session: ['p_request_id'],
  nys_operator_state: [],
  nys_action: ['p_id', 'p_generation', 'p_revision', 'p_request_id', 'p_action', 'p_data'],
  nys_operator_action: ['p_id', 'p_generation', 'p_revision', 'p_request_id', 'p_action'],
  nys_worker_claim: ['p_mode'],
  nys_worker_finish: ['p_job_id', 'p_lease_id', 'p_result', 'p_error'],
  nys_local_state: ['p_session_id'],
  nys_td_claim: ['p_session_id', 'p_claim_id'],
};

export async function asRole(db, userId, role, callback) {
  if (!['anon', 'authenticated', 'service_role'].includes(role)) throw new Error('FORBIDDEN');
  return db.transaction(async (tx) => {
    await tx.query("select set_config('request.jwt.claim.sub', $1, true), set_config('request.jwt.claim.role', $2, true)", [userId ?? '', role]);
    await tx.exec(`set local role ${role}`);
    return callback(tx);
  });
}

export function rpc(db, userId, name, args = {}, role = 'authenticated') {
  const keys = RPC_ARGUMENTS[name];
  if (!keys) throw new Error('UNKNOWN_RPC');
  const values = keys.map((key) => args[key] ?? (key === 'p_data' ? {} : null));
  return asRole(db, userId, role, async (tx) => {
    const result = await tx.query(`select public.${name}(${keys.map((_, i) => `$${i + 1}`).join(',')}) as result`, values);
    return result.rows[0].result;
  });
}
