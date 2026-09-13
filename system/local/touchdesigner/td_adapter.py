"""Runs on TD's main thread. Never performs network I/O or AI calls."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import checked_job, current_job, fresh, read_json, write_json


class Runtime:
    def __init__(self, owner, project_root):
        self.owner = owner
        self.system = Path(project_root) / 'system'
        self.root = self.system / 'runtime'
        self.last_tick = 0
        self.last_heartbeat = 0
        self.saves = {}
        self.last_states = {}
        self.process = None

    def setting(self, key):
        table = self.owner.op('settings')
        cell = table[key, 1]
        return cell.val.strip() if cell is not None else ''

    def text(self, key):
        table = self.owner.op('copy')
        cell = table[key, 1]
        return cell.val if cell is not None else ''

    def start_bridge(self, session, demo=True, mock=True, processor=None):
        import uuid
        uuid.UUID(session)
        if self.process and self.process.poll() is None:
            raise RuntimeError('Bridge is already running. Stop it before changing session.')
        executable = self.setting('python')
        if not executable or not Path(executable).is_file():
            raise RuntimeError('Set the python row in settings to a Python executable, not TouchDesigner.exe')
        command = [executable, str(self.system / 'local/bridge.py'), '--session', session]
        if demo:
            command.append('--demo')
        if mock:
            command.append('--mock')
        elif processor:
            command.extend(['--processor', str(processor)])
        else:
            raise RuntimeError('Choose mock=True or a processor script. No AI prompts are configured.')
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / 'bridge.log').open('ab') as log:
            self.process = subprocess.Popen(command, cwd=str(self.system), stdout=log, stderr=log,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def stop_bridge(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None

    def overlay(self, participant):
        p = participant
        if p['step'] == 'consent':
            return self.text('consent')
        if p['step'] == 'tutorial':
            return self.text('tutorial')
        if p['step'] == 'map':
            return self.text('map')
        if p['step'] == 'complete':
            return self.text('complete')
        if p['status'] == 'countdown':
            end = datetime.fromisoformat(p['countdown_ends_at'].replace('Z', '+00:00')).timestamp()
            return str(max(1, min(3, math.ceil(end - time.time()))))
        if p['status'] == 'processing':
            return self.text('processing')
        if p['status'] == 'error':
            return self.text('error')
        if p['status'] == 'result':
            response = next((r['result'] for r in p.get('responses', []) if r['question'] == p['question']), {})
            return response.get('trace') or response.get('translated_response') or 'Result ready.'
        return self.text('Q' + str(p['question']))

    def finish_capture(self, job, error=None):
        write_json(self.root / 'captures' / job['slot'] / (job['id'] + '.json'),
                   {'job_id': job['id'], 'generation': job['generation'], 'error': error, 'updated_epoch': time.time()})

    def capture(self, participant):
        slot = participant['slot']
        request = read_json(self.root / 'requests' / (slot + '.json'))
        if not fresh(request):
            return
        job = checked_job(request['job'])
        if not current_job(participant, job):
            return
        folder = self.root / 'captures' / slot
        marker = folder / (job['id'] + '.json')
        final = folder / (job['id'] + '.png')
        temporary = folder / (job['id'] + '.tmp.png')
        attempt = self.root / 'td/attempts' / (job['id'] + '.json')
        if marker.exists():
            return
        if job['id'] in self.saves:
            status, started = self.saves[job['id']]
            if status.isCompleted():
                if not temporary.is_file() or temporary.stat().st_size == 0:
                    self.finish_capture(job, 'CAPTURE_EMPTY')
                else:
                    os.replace(temporary, final)
                    self.finish_capture(job)
                del self.saves[job['id']]
            elif time.time() - started > 10:
                self.finish_capture(job, 'CAPTURE_TIMEOUT')
                del self.saves[job['id']]
            return
        if attempt.exists() or final.exists():
            # TD restarted after capture began but before the completion marker was persisted.
            self.finish_capture(job, 'CAPTURE_UNCERTAIN')
            return
        source_path = self.setting('camera_' + slot)
        source = self.owner.op(source_path) if source_path else None
        if source is None or not hasattr(source, 'save') or not hasattr(source, 'width'):
            self.finish_capture(job, 'CAMERA_NOT_CONFIGURED')
            return
        folder.mkdir(parents=True, exist_ok=True)
        write_json(attempt, {'job_id': job['id'], 'generation': job['generation'], 'started_epoch': time.time()})
        try:
            status = source.save(str(temporary), asynchronous=True)
            self.saves[job['id']] = (status, time.time())
        except Exception:
            self.finish_capture(job, 'CAPTURE_FAILED')

    def tick(self):
        if time.monotonic() - self.last_tick < 0.1:
            return
        self.last_tick = time.monotonic()
        session = None
        for slot in ('A', 'B'):
            envelope = read_json(self.root / 'state' / (slot + '.json'))
            node = self.owner.op(slot)
            if not fresh(envelope):
                node.op('overlay_text').text = 'Waiting for connection.'
                continue
            p = envelope.get('participant')
            if not p:
                node.op('overlay_text').text = 'Waiting for participant.'
                continue
            session = envelope['session_id']
            previous = self.last_states.get(slot)
            identity = (p['id'], p['generation'], p['revision'])
            if previous != identity:
                node.op('state').text = json.dumps(p, ensure_ascii=False, indent=2)
                self.last_states[slot] = identity
                node.par.Consented = bool(p.get('consent_at'))
                node.par.Step = p['step']
                node.par.Status = p['status']
                node.par.Question = p['question']
                node.par.Generation = p['generation']
                # Durable notification identity; state restoration above always happens.
                seen_path = self.root / 'td/seen' / (slot + '.json')
                seen = read_json(seen_path, {})
                consent_id = [p['id'], p['generation']]
                if p.get('consent_at') and seen.get('consent_id') != consent_id:
                    write_json(seen_path, {'consent_id': consent_id})
                    self.owner.op('hooks').module.on_consent(slot, p)
                self.owner.op('hooks').module.on_state(slot, p)
            node.op('overlay_text').text = self.overlay(p)
            camera = self.setting('camera_' + slot)
            if camera:
                node.op('camera').par.top = camera
            self.capture(p)
        if time.time() - self.last_heartbeat > 1:
            write_json(self.root / 'td/heartbeat.json', {'updated_epoch': time.time(), 'session_id': session})
            self.last_heartbeat = time.time()
