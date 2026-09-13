import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { openDatabase, rpc, OPERATOR_ID } from '../tools/database.mjs';

test('local database restart preserves accepted requests and participant state', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'nys-db-test-'));
  let db;
  try {
    db = await openDatabase(dir);
    const req = { p_request_id:randomUUID() };
    const created = await rpc(db, OPERATOR_ID, 'nys_create_session', req);
    const uid = randomUUID();
    const initial = await rpc(db, uid, 'nys_join', { p_token:created.entries[0].token });
    const p = initial.participant;
    await rpc(db,uid,'nys_action',{ p_id:p.id,p_generation:p.generation,p_revision:p.revision,p_request_id:randomUUID(),p_action:'consent',p_data:{} });
    await db.close(); db = await openDatabase(dir);
    const state = await rpc(db, uid, 'nys_snapshot',{p_id:p.id});
    assert.equal(state.participant.step,'tutorial');
    assert.deepEqual(await rpc(db, OPERATOR_ID,'nys_create_session',req),created);
  } finally {
    await db?.close();
    // mkdtemp returned this exact test-owned directory; never remove a computed project path.
    assert.ok(dir.startsWith(join(tmpdir(), 'nys-db-test-')));
    await rm(dir,{recursive:true,force:true});
  }
});
