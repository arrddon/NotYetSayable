"""File protocol shared by external Python and TouchDesigner. Standard library only."""
import json
import os
import time
import uuid
from pathlib import Path


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def current_job(participant, job):
    return bool(participant and participant.get('id') == job.get('participant_id')
                and participant.get('generation') == job.get('generation')
                and participant.get('active_job_id') == job.get('id')
                and participant.get('status') == 'processing')


def fresh(value, max_age=5):
    age = time.time() - (value or {}).get('updated_epoch', 0)
    return 0 <= age < max_age


def checked_job(job):
    uuid.UUID(job['id'])
    uuid.UUID(job['participant_id'])
    uuid.UUID(job['lease_id'])
    if job['slot'] not in ('A', 'B') or job['question'] not in (1, 2, 3, 4):
        raise ValueError('INVALID_JOB')
    return job
