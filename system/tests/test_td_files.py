"""Critical file recovery checks. No camera, network, or AI call."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'local'))
from bridge import Bridge
from common import write_json, read_json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'local/touchdesigner'))
from td_adapter import Runtime


class Client:
    def __init__(self, p):
        self.p, self.uploads = p, []
    def call(self, name, args):
        if name == 'nys_local_state':
            return {'participants':[self.p]}
        if name == 'nys_worker_finish':
            self.uploads.append(args)
            return True
        raise AssertionError(name)


class Files(unittest.TestCase):
    def fixture(self, root, stage='capture'):
        job = dict(id=str(uuid.uuid4()), participant_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()),
                   lease_id=str(uuid.uuid4()), generation=1, slot='A', question=1, attempt=1)
        p = dict(id=job['participant_id'], generation=1, active_job_id=job['id'], status='processing', slot='A')
        write_json(root/'jobs'/f"{job['id']}.json", {'job':job,'stage':stage,'result':None,'error':None})
        return job, p

    def test_marker_gates_processing_and_saved_result_uploads(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); job,p=self.fixture(root); client=Client(p)
            bridge=Bridge(client,root,job['session_id'],mock=True)
            try:
                image=root/'captures/A'/f"{job['id']}.png"
                image.parent.mkdir(parents=True); image.write_bytes(b'test-image')
                bridge.tick()
                self.assertFalse(bridge.futures)  # A file alone is never a capture-complete signal.
                write_json(image.with_suffix('.json'),{'job_id':job['id'],'generation':1,'error':None})
                bridge.tick()
                for future in bridge.futures.values(): future.result(timeout=2)
                bridge.tick()
                self.assertEqual(len(client.uploads),1)
                self.assertEqual(read_json(root/'jobs'/f"{job['id']}.json")['stage'],'done')
            finally: bridge.pool.shutdown()

    def test_restart_does_not_repeat_uncertain_processor(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); job,p=self.fixture(root,'processing'); client=Client(p)
            bridge=Bridge(client,root,job['session_id'],mock=True)
            try:
                bridge.tick()
                self.assertEqual(client.uploads[0]['p_error'],'PROCESSING_UNCERTAIN')
                self.assertFalse(bridge.futures)
            finally: bridge.pool.shutdown()

    def test_td_restart_does_not_recapture_and_old_generation_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); job,p=self.fixture(root)
            td=Runtime(None,root); td.root=root
            write_json(root/'requests/A.json',{'updated_epoch':time.time(),'job':job})
            write_json(root/'td/attempts'/f"{job['id']}.json",{'started_epoch':time.time()})
            td.capture(p)
            marker=root/'captures/A'/f"{job['id']}.json"
            self.assertEqual(read_json(marker)['error'],'CAPTURE_UNCERTAIN')
            marker.unlink(); p['generation']=2
            td.capture(p)
            self.assertFalse(marker.exists())


if __name__ == '__main__': unittest.main()
