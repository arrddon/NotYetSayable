"""Supabase / local demo -> durable files -> TouchDesigner -> processor -> Supabase.

No TD calls or AI prompts here. Run with --mock explicitly, or provide --processor.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

from common import checked_job, current_job, fresh, read_json, write_json

SYSTEM = Path(__file__).resolve().parents[1]


def load_env():
    path = SYSTEM / '.env.local'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


class Client:
    def __init__(self, demo):
        self.demo = demo
        load_env()
        if not demo:
            self.url = os.environ.get('SUPABASE_URL', '').rstrip('/')
            self.key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
            if not self.url.startswith('https://') or not self.key:
                raise RuntimeError('Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in system/.env.local')

    def call(self, name, args):
        if self.demo:
            config = read_json(SYSTEM / 'runtime/demo-bridge.json')
            if not config:
                raise RuntimeError('Start npm run dev:td first')
            url = config['url']
            if not url.startswith('http://127.0.0.1:'):
                raise RuntimeError('Demo must use loopback')
            headers = {'X-Demo-Bridge': config['token']}
            body = {'name': name, 'args': args}
        else:
            url = self.url + '/rest/v1/rpc/' + name
            headers = {'apikey': self.key, 'Authorization': 'Bearer ' + self.key}
            body = args
        request = urllib.request.Request(url, json.dumps(body).encode(),
                                         {'Content-Type': 'application/json', **headers}, method='POST')
        with urllib.request.urlopen(request, timeout=4) as response:
            value = json.load(response)
        return value['data'] if self.demo else value


class SingleInstance:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a+b')
        self.stream.seek(0)
        self.stream.write(b'0')
        self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('A bridge is already running for this runtime directory')


def process_image(job, path, mock, processor):
    if mock:
        return {'question_id': 'Q' + str(job['question']),
                'raw_response': '[TEST] Capture received for participant ' + job['slot'],
                'translated_response': '[TEST] Capture received.', 'keywords': [],
                'trace': '[TEST] Your image was received by the local bridge.',
                'classification': None, 'processing_mode': 'mock', 'analysis_status': 'not_configured'}
    # External script receives JSON on stdin and must return just the result JSON on stdout.
    # It owns the later user-supplied Vision prompt and API configuration.
    result = subprocess.run([sys.executable, str(processor)],
                            input=json.dumps({'job': job, 'image_path': str(path)}),
                            capture_output=True, text=True, encoding='utf-8', timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError('PROCESSOR_FAILED')
    return json.loads(result.stdout)


class Bridge:
    def __init__(self, client, runtime, session, mock=False, processor=None):
        self.client, self.root, self.session = client, Path(runtime), str(uuid.UUID(session))
        self.mock, self.processor = mock, processor
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.futures = {}
        self.records = {}
        self.states = {}
        for path in (self.root / 'jobs').glob('*.json'):
            record = read_json(path)
            if record and record['job']['session_id'] == self.session and record['stage'] not in ('done', 'cancelled'):
                if record['stage'] == 'processing':
                    # Do not repeat a potentially billed request after a crash.
                    record.update(stage='upload', error='PROCESSING_UNCERTAIN')
                self.records[record['job']['id']] = record

    def save(self, record):
        write_json(self.root / 'jobs' / (record['job']['id'] + '.json'), record)

    def tick(self):
        state = self.client.call('nys_local_state', {'p_session_id': self.session})
        self.states = {p['slot']: p for p in state['participants']}
        now = time.time()
        for slot in ('A', 'B'):
            write_json(self.root / 'state' / (slot + '.json'),
                       {'updated_epoch': now, 'session_id': self.session, 'participant': self.states.get(slot)})
        heartbeat = read_json(self.root / 'td/heartbeat.json')
        # No capture claim unless TD is running and reading this exact session.
        td_online = fresh(heartbeat, 3) and heartbeat.get('session_id') == self.session
        if td_online:
            pending_path = self.root / 'claim.json'
            pending = read_json(pending_path)
            if not pending or pending.get('session_id') != self.session:
                pending = {'session_id': self.session, 'id': str(uuid.uuid4())}
                write_json(pending_path, pending)
            job = self.client.call('nys_td_claim', {'p_session_id': self.session, 'p_claim_id': pending['id']})
            if job:
                checked_job(job)
                if job['id'] not in self.records:
                    record = {'job': job, 'stage': 'capture', 'result': None, 'error': None}
                    self.records[job['id']] = record
                    self.save(record)
                # Fetch again next tick before publishing: the old snapshot was countdown.
            write_json(pending_path, {'session_id': self.session, 'id': str(uuid.uuid4())})
        for job_id, record in list(self.records.items()):
            if record['stage'] in ('done', 'cancelled'):
                continue
            job = record['job']
            p = self.states.get(job['slot'])
            # The snapshot immediately before a claim may still be countdown for this job.
            if p and p.get('active_job_id') == job_id and p.get('status') == 'countdown':
                continue
            if not current_job(p, job):
                # A lost completion response is still safely acknowledged after a restart.
                if p and p.get('generation') == job['generation'] and p.get('active_job_id') == job_id and p.get('status') == 'result':
                    record['stage'] = 'done'
                else:
                    record['stage'] = 'cancelled'
                self.save(record)
                continue
            if record['stage'] == 'capture':
                write_json(self.root / 'requests' / (job['slot'] + '.json'), {'updated_epoch': now, 'job': job})
                marker = read_json(self.root / 'captures' / job['slot'] / (job_id + '.json'))
                if not marker:
                    continue
                if marker.get('job_id') != job_id or marker.get('generation') != job['generation']:
                    continue
                path = self.root / 'captures' / job['slot'] / (job_id + '.png')
                if marker.get('error') or not path.is_file() or path.stat().st_size == 0:
                    record.update(stage='upload', error=marker.get('error') or 'CAPTURE_MISSING')
                else:
                    record['stage'] = 'processing'
                    self.save(record)
                    self.futures[job_id] = self.pool.submit(process_image, job, path, self.mock, self.processor)
            if record['stage'] == 'processing' and self.futures[job_id].done():
                try:
                    record['result'] = self.futures.pop(job_id).result()
                    write_json(self.root / 'results' / (job_id + '.json'), {'job': job, 'result': record['result']})
                except Exception:
                    record['error'] = 'PROCESSOR_FAILED'
                record['stage'] = 'upload'
            if record['stage'] == 'upload':
                self.save(record)  # Persist before network I/O; repeat the same upload after failure.
                accepted = self.client.call('nys_worker_finish', {
                    'p_job_id': job_id, 'p_lease_id': job['lease_id'],
                    'p_result': record['result'], 'p_error': record['error']})
                record['stage'] = 'done' if accepted else 'cancelled'
                self.save(record)
        write_json(self.root / 'bridge-status.json', {'updated_epoch': time.time(), 'session_id': self.session,
                                                     'td_online': td_online, 'mode': 'mock' if self.mock else 'processor'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True, help='Full session UUID from the operator page')
    parser.add_argument('--demo', action='store_true')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--mock', action='store_true')
    mode.add_argument('--processor', type=Path)
    args = parser.parse_args()
    if args.processor and not args.processor.is_file():
        parser.error('Processor script does not exist')
    root = SYSTEM / 'runtime'
    lock = SingleInstance(root / 'bridge.lock')
    bridge = Bridge(Client(args.demo), root, args.session, args.mock, args.processor)
    print('Bridge running for session ' + bridge.session, flush=True)
    try:
        while True:
            try:
                bridge.tick()
            except Exception as error:
                # Never print request headers / credentials / response contents.
                write_json(root / 'bridge-status.json', {'updated_epoch': time.time(), 'error': type(error).__name__})
                print('Bridge waiting: ' + type(error).__name__, flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.pool.shutdown(wait=True)
        lock.stream.close()


if __name__ == '__main__':
    main()
