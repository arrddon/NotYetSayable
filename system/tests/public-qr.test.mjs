import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { openDatabase, rpc, OPERATOR_ID } from '../tools/database.mjs';

test('public display shows only the current unclaimed entry and keeps its URL after reset', async () => {
  const db = await openDatabase();
  try {
    const operator = (name, args) => rpc(db, OPERATOR_ID, name, args);
    const publicRead = (id) => rpc(db, null, 'nys_public_qr', { p_display_id: id }, 'anon');
    const created = await operator('nys_create_session', { p_request_id: randomUUID() });
    const entry = created.entries.find((item) => item.slot === 'A');
    await assert.rejects(rpc(db, randomUUID(), 'nys_publish_qr',
      { p_id: entry.id, p_token: entry.token }), /FORBIDDEN/);
    const displayId = await operator('nys_publish_qr', { p_id: entry.id, p_token: entry.token });
    assert.deepEqual(await publicRead(displayId), { available: true, token: entry.token });
    assert.deepEqual(await publicRead(randomUUID()), { available: false });

    const participant = randomUUID();
    const joined = await rpc(db, participant, 'nys_join', { p_token: entry.token });
    assert.deepEqual(await publicRead(displayId), { available: false });
    const p = joined.participant;
    const reset = await operator('nys_operator_action', { p_id: p.id, p_generation: p.generation,
      p_revision: p.revision, p_request_id: randomUUID(), p_action: 'reset' });
    assert.deepEqual(await publicRead(displayId), { available: false });
    assert.notEqual(reset.token, entry.token);
    assert.equal(await operator('nys_publish_qr', { p_id: p.id, p_token: reset.token }), displayId);
    assert.deepEqual(await publicRead(displayId), { available: true, token: reset.token });
    await assert.rejects(rpc(db, randomUUID(), 'nys_join', { p_token: entry.token }), /ENTRY_EXPIRED/);
  } finally { await db.close(); }
});
