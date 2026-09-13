export function mockResult(job) {
  return {
    question_id: `Q${job.question}`,
    raw_response: `[TEST] Participant ${job.slot ?? ''} · Q${job.question} · attempt ${job.attempt}`,
    translated_response: '',
    keywords: [],
    trace: '',
    classification: null,
    processing_mode: 'mock',
    analysis_status: 'not_configured',
  };
}

// This is a development fixture worker, not the future TouchDesigner bridge.
export function startMockWorker(call, { delayMs = 1500, intervalMs = 400, onError = console.error } = {}) {
  let stopped = false;
  let timer;
  const running = new Set();
  async function tick() {
    try {
      const job = await call('nys_worker_claim', { p_mode: 'mock' });
      if (job) {
        const work = (async () => {
          await new Promise((resolve) => setTimeout(resolve, delayMs));
          if (!stopped) await call('nys_worker_finish', {
            p_job_id: job.id, p_lease_id: job.lease_id, p_result: mockResult(job), p_error: null,
          });
        })();
        running.add(work);
        work.catch(onError).finally(() => running.delete(work));
      }
    } catch (error) { onError(error); }
    if (!stopped) timer = setTimeout(tick, intervalMs);
  }
  void tick();
  return async () => {
    stopped = true;
    clearTimeout(timer);
    await Promise.allSettled([...running]);
  };
}
