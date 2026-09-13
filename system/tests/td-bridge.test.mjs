import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { openDatabase, rpc, OPERATOR_ID } from '../tools/database.mjs';

test('TD receives consent, claims only its session, retries the same lease, and rejects late reset results', async () => {
  const db = await openDatabase();
  try {
    const owner = randomUUID();
    const op = (name, args) => rpc(db, OPERATOR_ID, name, args);
    const worker = (name, args) => rpc(db, null, name, args, 'service_role');
    const session = await op('nys_create_session', {p_request_id:randomUUID()});
    const other = await op('nys_create_session', {p_request_id:randomUUID()});
    let state = await rpc(db, owner, 'nys_join', {p_token:session.entries[0].token});
    async function act(action) {
      const p = state.participant;
      state = await rpc(db, owner, 'nys_action', {p_id:p.id,p_generation:p.generation,p_revision:p.revision,p_request_id:randomUUID(),p_action:action,p_data:{}});
    }
    await act('consent');
    let local = await worker('nys_local_state', {p_session_id:session.session_id});
    assert.equal(local.participants[0].step, 'tutorial');
    assert.ok(local.participants[0].consent_at);
    await assert.rejects(rpc(db, owner, 'nys_local_state', {p_session_id:session.session_id}), /permission denied/);
    await act('tutorial'); await act('confirm');
    await db.exec("update public.jobs set not_before=now()-interval '1 second'");
    assert.equal(await worker('nys_td_claim',{p_session_id:other.session_id,p_claim_id:randomUUID()}),null);
    const claim = {p_session_id:session.session_id,p_claim_id:randomUUID()};
    const job = await worker('nys_td_claim',claim);
    assert.deepEqual(await worker('nys_td_claim',claim),job);
    assert.equal(await worker('nys_td_claim',{...claim,p_claim_id:randomUUID()}),null);
    local = await worker('nys_local_state',{p_session_id:session.session_id});
    const p = local.participants[0];
    await op('nys_operator_action',{p_id:p.id,p_generation:p.generation,p_revision:p.revision,p_request_id:randomUUID(),p_action:'reset'});
    assert.equal(await worker('nys_worker_finish',{p_job_id:job.id,p_lease_id:job.lease_id,p_result:null,p_error:'CAPTURE_FAILED'}),false);
  } finally { await db.close(); }
});
