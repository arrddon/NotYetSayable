import argparse
import base64
import csv
import json
import math
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


PROMPT_CSV = os.path.join('Assets', 'NYS_lv1_prompts - Sheet1.csv')
CACHE_PATH = os.path.join('Data', 'lv1_current_cache.json')
MIRROR_PATH = os.path.join('Data', 'lv1_current_mirror.json')
LV2_TABLE_PATH = os.path.join('Data', 'latent_home_table_v02.json')
COMPLETED_SESSION_DIR = os.path.join('Data', 'lv1_sessions')
CAPTURE_DIR = os.path.join('Capture', 'lv1_simple')
SCRIPT_LOG = os.path.join('Data', 'lv1_ai_simple_debug.log')
WORKER_STDOUT_LOG = os.path.join('Data', 'lv1_ai_simple_worker_stdout.log')
WORKER_STDERR_LOG = os.path.join('Data', 'lv1_ai_simple_worker_stderr.log')

PHASE_CHOP = 'MainPhase'
PHASE_CHANNEL = 'MainPhase'
CAPTURE_TOP = 'lv1_capture'
GOT_ANSWER_OP = 'gotAnswer'

RESET_PHASE = 1
FINAL_RESET_PHASE = 13
FINAL_RESET_TARGET_PHASE = 0
ANALYSIS_PHASES = {
    4: 'Q1',
    7: 'Q2',
    10: 'Q3-1',
}
DISPLAY_PHASES = {
    5: 'Q1',
    8: 'Q2',
    11: 'Q3-1',
}
DISPLAY_HOLD_SECONDS = 3.0
DISPLAY_HOLD_FRAMES = 180
OBSOLETE_TD_OPS = [
    'lv1_ai_phase',
    'lv1_ai_debug',
    'lv1_current_json',
    'lv1_current_status',
    'lv1_current_results',
    'lv1_current_events',
]

DEFAULT_MODEL = 'gpt-5.4-mini'
OPENAI_MODEL_ENV = 'OPENAI_MODEL'
OPENAI_API_KEY_ENV = 'OPENAI_API_KEY'
OPENAI_API_KEY_FILE = os.path.join('Local', 'openai_api_key.txt')

POLL_DELAY_FRAMES = 12
CAPTURE_WAIT_FRAMES = 6
WORKER_TIMEOUT_SECONDS = 75
WORKER_WAIT_IMAGE_SECONDS = 10
THEMES = ['Belonging', 'Care', 'Stability', 'Freedom', 'Connection', 'Possibility']


def in_td():
    return 'op' in globals()


def project_dir():
    if in_td():
        try:
            return project.folder
        except Exception:
            pass
    return os.getcwd()


def full_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(project_dir(), path)


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def log(message):
    line = '[lv1_ai_simple] {}'.format(message)
    print(line)
    try:
        path = full_path(SCRIPT_LOG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write('{} {}\n'.format(now(), line))
    except Exception:
        pass


def td_table(name, header):
    if not in_td():
        return None
    table = op(name)
    if table is None:
        try:
            table = me.parent().create(tableDAT, name)
        except Exception:
            return None
    table.clear()
    table.appendRow(header)
    return table


def cleanup_obsolete_td_ops():
    if not in_td():
        return
    for name in OBSOLETE_TD_OPS:
        old = op(name)
        if old is None or old == me:
            continue
        try:
            old.destroy()
            log('deleted old TD op {}'.format(name))
        except Exception as e:
            log('could not delete old TD op {}: {}'.format(name, e))


def read_json(path, default):
    path = full_path(path)
    try:
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return default
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read().strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default


def write_json(path, data):
    path = full_path(path)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def new_cache(phase=RESET_PHASE):
    return {
        'schema': 'lv1_ai_simple_cache_v01',
        'session_id': datetime.now().strftime('%Y%m%d%H%M%S'),
        'status': 'active',
        'current_phase': phase,
        'created_at': now(),
        'updated_at': now(),
        'questions': {},
        'events': [],
    }


def add_event(cache, kind, detail=None):
    cache.setdefault('events', []).append({
        'ts': now(),
        'kind': kind,
        'detail': detail or {},
    })
    cache['events'] = cache['events'][-80:]
    cache['updated_at'] = now()


def make_mirror(cache):
    questions = cache.get('questions') or {}
    responses = {}
    for key in ['Q1', 'Q2', 'Q3-1', 'Q3-2']:
        entry = questions.get(key) or {}
        result = entry.get('result') or {}
        classification = result.get('classification') or {}
        mirror_key = key.lower().replace('-', '_')
        responses[mirror_key] = {
            'question_id': key,
            'phase': entry.get('phase', ''),
            'status': entry.get('status', ''),
            'raw_response': result.get('raw_response', ''),
            'translated_response': result.get('translated_response', ''),
            'keywords': result.get('keywords') or [],
            'trace': result.get('trace', ''),
            'primary_theme': classification.get('primary_theme', ''),
            'reason': classification.get('reason', ''),
            'confidence': classification.get('confidence', ''),
        }
    return {
        'schema': 'lv1_current_mirror_v01',
        'session_id': cache.get('session_id', ''),
        'status': cache.get('status', ''),
        'current_phase': cache.get('current_phase', ''),
        'updated_at': cache.get('updated_at', ''),
        'responses': responses,
    }


def save_cache(cache):
    cache['updated_at'] = now()
    cache_path = full_path(CACHE_PATH)
    mirror_path = full_path(MIRROR_PATH)
    try:
        cache_path = write_json(CACHE_PATH, cache)
        mirror_path = write_json(MIRROR_PATH, make_mirror(cache))
        update_td_debug(cache, cache_path, mirror_path)
    except Exception as e:
        cache['file_error'] = str(e)
        update_td_debug(cache, cache_path, mirror_path)
        raise


def update_td_debug(cache, cache_path='', mirror_path=''):
    return


def table_values(name):
    values = {}
    if not in_td():
        return values
    table = op(name)
    if table is None:
        return values
    try:
        for r in range(table.numRows):
            key = table[r, 0].val.strip()
            val = table[r, 1].val.strip()
            if key:
                values[key] = val
    except Exception:
        pass
    return values


def read_pin_from_ctrl():
    for table_name in ['pin_values', 'ctrl_values']:
        values = table_values(table_name)
        try:
            lng = float(values.get('lng', ''))
            lat = float(values.get('lat', ''))
            zoom = float(values.get('zoom', 13) or 13)
        except Exception:
            continue
        return {
            'lng': lng,
            'lat': lat,
            'zoom': zoom,
            'type': values.get('type', ''),
            'phase': values.get('phase', ''),
        }
    return None


def read_phase():
    if not in_td():
        return None
    chop = op(PHASE_CHOP)
    if chop is None:
        return None
    try:
        return int(round(float(chop[PHASE_CHANNEL].eval())))
    except Exception:
        try:
            return int(round(float(chop[0].eval())))
        except Exception:
            return None


def read_prompts():
    with open(full_path(PROMPT_CSV), 'r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))

    system_prompt = ''
    header_index = None
    for i, row in enumerate(rows):
        if not row:
            continue
        if row[0] == 'AI System Prompt':
            system_prompt = row[1] if len(row) > 1 else ''
        if row[0] == 'Phase':
            header_index = i
            break

    if header_index is None:
        raise RuntimeError('Phase header not found in {}'.format(PROMPT_CSV))

    header = rows[header_index]
    phase_rows = {}
    for row in rows[header_index + 1:]:
        if not row or not row[0].strip():
            continue
        row = row + [''] * max(0, len(header) - len(row))
        item = dict(zip(header, row))
        try:
            phase_rows[int(item.get('Phase', '').strip())] = item
        except Exception:
            pass

    return system_prompt, phase_rows


def capture_path(question_id, phase):
    folder = full_path(CAPTURE_DIR)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    name = '{}_phase{}_{}_{}.png'.format(question_id, phase, stamp, secrets.token_hex(3))
    return os.path.join(folder, name)


def pulse_capture(path):
    top = op(CAPTURE_TOP)
    if top is None:
        raise RuntimeError('missing capture TOP {}'.format(CAPTURE_TOP))
    top.par.file = path
    top.par.addframe.pulse()


def pulse_got_answer():
    target = op(GOT_ANSWER_OP)
    if target is None:
        raise RuntimeError('missing gotAnswer operator {}'.format(GOT_ANSWER_OP))
    target.par.trigger.pulse()


def set_phase_value(value):
    if not in_td():
        return False

    target = op(PHASE_CHOP)
    if target is not None:
        for par_name in ['value0', 'value', 'const0value']:
            try:
                par = getattr(target.par, par_name, None)
                if par is not None:
                    par.val = value
                    return True
            except Exception:
                try:
                    setattr(target.par, par_name, value)
                    return True
                except Exception:
                    pass

    for op_name in ['setPhase0', 'resetPhase', 'phase0']:
        try:
            pulse_target = op(op_name)
            if pulse_target is not None:
                pulse_target.par.trigger.pulse()
                return True
        except Exception:
            pass

    return False


def safe_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def phase_result(cache, question_id):
    entry = (cache.get('questions') or {}).get(question_id) or {}
    return entry.get('result') or {}


def articulation_from_result(result):
    raw = str(result.get('raw_response', '') or '').strip()
    translated = str(result.get('translated_response', '') or '').strip()
    trace = str(result.get('trace', '') or '').strip()
    keywords = safe_list(result.get('keywords'))

    poetry_en = []
    if trace:
        poetry_en.append(trace)
    elif translated:
        poetry_en.append(translated)
    elif raw:
        poetry_en.append(raw)

    poetry_original = []
    if raw:
        poetry_original.append(raw)
    if trace and trace not in poetry_original:
        poetry_original.append(trace)

    return {
        'raw_fragments': safe_list(raw),
        'keywords_original': keywords,
        'keywords_en': keywords,
        'poetry_original': poetry_original,
        'poetry_en': poetry_en,
    }


def combined_classification(cache):
    counts = {}
    confidences = {}
    for qid in ['Q1', 'Q2', 'Q3-1']:
        classification = (phase_result(cache, qid).get('classification') or {})
        theme = classification.get('primary_theme', '')
        if theme not in THEMES:
            continue
        counts[theme] = counts.get(theme, 0) + 1
        try:
            confidences[theme] = confidences.get(theme, 0.0) + float(classification.get('confidence', 0) or 0)
        except Exception:
            pass

    if not counts:
        return {
            'primary_theme': 'Possibility',
            'confidence': 0.35,
            'reason': 'Fallback theme because no Lv1 classification was available.',
            'source': 'lv1_append_fallback',
        }

    ranked = sorted(counts.keys(), key=lambda key: (counts[key], confidences.get(key, 0.0)), reverse=True)
    theme = ranked[0]
    return {
        'primary_theme': theme,
        'confidence': round(min(0.95, max(0.45, confidences.get(theme, 0.0) / max(counts[theme], 1))), 2),
        'reason': 'Combined from Q1/Q2/Q3-1 Lv1 classifications.',
        'source': 'lv1_append',
    }


def collect_row_keywords(row):
    keywords = []
    for phase in ['past', 'present', 'future']:
        art = (row.get('articulation') or {}).get(phase) or {}
        for item in art.get('keywords_en') or []:
            item = str(item).strip()
            if item and item not in keywords:
                keywords.append(item)
    return keywords


def keyword_overlap(a, b):
    aa = set([str(item).lower().replace('_', ' ') for item in a if str(item).strip()])
    bb = set([str(item).lower().replace('_', ' ') for item in b if str(item).strip()])
    if not aa or not bb:
        return 0
    score = 0
    for left in aa:
        for right in bb:
            if left == right or left in right or right in left:
                score += 1
    return score


def rough_distance(lng_a, lat_a, lng_b, lat_b):
    try:
        dx = (float(lng_a) - float(lng_b)) * math.cos(math.radians((float(lat_a) + float(lat_b)) * 0.5))
        dy = float(lat_a) - float(lat_b)
        return math.sqrt(dx * dx + dy * dy)
    except Exception:
        return 999999.0


def choose_cluster(table, row, pin):
    if ((row.get('map') or {}).get('placement_mode') == 'participant_pin'):
        return 'cluster_live_{}'.format(row.get('row_id', 'unit')).lower()

    clusters = table.get('clusters') or []
    if not clusters:
        return 'cluster_live_unassigned'

    row_theme = (row.get('classification') or {}).get('primary_theme', '')
    row_keywords = collect_row_keywords(row)
    best_cluster = clusters[0]
    best_score = -999999.0

    for cluster in clusters:
        score = 0.0
        if cluster.get('primary_theme') == row_theme:
            score += 8.0
        score += keyword_overlap(row_keywords, cluster.get('dominant_keywords') or []) * 1.5
        score += keyword_overlap(row_keywords, (cluster.get('keyword_counts') or {}).keys()) * 0.75
        dist = rough_distance(pin.get('lng'), pin.get('lat'), cluster.get('center_lng', 0), cluster.get('center_lat', 0))
        score -= min(dist, 20.0) * 0.05
        if score > best_score:
            best_score = score
            best_cluster = cluster

    return best_cluster.get('cluster_id', 'cluster_live_unassigned')


def update_cluster_metrics(table):
    rows = table.get('rows') or []
    clusters = table.setdefault('clusters', [])
    cluster_lookup = {cluster.get('cluster_id'): cluster for cluster in clusters}
    cluster_members = {}

    for row in rows:
        cid = (row.get('lod') or {}).get('cluster_id', '')
        if not cid:
            continue
        cluster_members.setdefault(cid, []).append(row)
        if cid not in cluster_lookup:
            cluster = {
                'cluster_id': cid,
                'lod': 1,
                'zoom_min': 0,
                'zoom_max': 10,
                'basis': 'live_append',
                'center_lng': (row.get('map') or {}).get('lng', 0),
                'center_lat': (row.get('map') or {}).get('lat', 0),
                'radius_km': 30,
                'dominant_keywords': [],
                'display_poetry_en': [],
            }
            clusters.append(cluster)
            cluster_lookup[cid] = cluster

    max_members = max([len(members) for members in cluster_members.values()] or [1])

    for cid, members in cluster_members.items():
        cluster = cluster_lookup[cid]
        theme_counts = {}
        keyword_counts = {}
        lngs = []
        lats = []

        for row in members:
            theme = (row.get('classification') or {}).get('primary_theme', '')
            if theme:
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
            for keyword in collect_row_keywords(row):
                key = keyword.lower().replace('_', ' ')
                keyword_counts[key] = keyword_counts.get(key, 0) + 1
            map_data = row.get('map') or {}
            if map_data.get('lng') is not None and map_data.get('lat') is not None:
                lngs.append(float(map_data.get('lng')))
                lats.append(float(map_data.get('lat')))

        member_count = len(members)
        primary_theme = ''
        primary_count = 0
        if theme_counts:
            primary_theme, primary_count = sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[0]

        if lngs and lats:
            cluster['center_lng'] = round(sum(lngs) / len(lngs), 6)
            cluster['center_lat'] = round(sum(lats) / len(lats), 6)

        sorted_keywords = sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)
        cluster['member_row_ids'] = [row.get('row_id') for row in members if row.get('row_id')]
        cluster['classification_counts'] = theme_counts
        cluster['primary_theme'] = primary_theme
        cluster['primary_theme_count'] = primary_count
        cluster['primary_theme_ratio'] = round(primary_count / float(member_count), 3) if member_count else 0
        cluster['keyword_counts'] = dict(sorted_keywords[:16])
        cluster['dominant_keywords'] = [item[0] for item in sorted_keywords[:8]]
        cluster['text_scale'] = round(0.85 + 1.15 * math.sqrt(member_count / float(max_members)), 3)
        cluster['text_weight'] = round(member_count * max(cluster.get('primary_theme_ratio', 0.0), 0.25), 3)

    for row in rows:
        cid = (row.get('lod') or {}).get('cluster_id', '')
        cluster = cluster_lookup.get(cid, {})
        theme = (row.get('classification') or {}).get('primary_theme', '')
        members = cluster_members.get(cid, [])
        theme_count = int((cluster.get('classification_counts') or {}).get(theme, 1))
        row['cluster_metrics'] = {
            'cluster_id': cid,
            'cluster_member_count': len(members),
            'theme_frequency_in_cluster': theme_count,
            'theme_ratio_in_cluster': round(theme_count / float(max(len(members), 1)), 3),
            'text_scale': round(0.8 + 0.18 * math.sqrt(theme_count), 3),
        }


def build_lv2_row(cache, pin, table):
    session_id = cache.get('session_id') or datetime.now().strftime('%Y%m%d%H%M%S')
    existing_rows = table.get('rows') or []
    row_index = len(existing_rows) + 1
    row_id = 'row_{:04d}'.format(row_index)
    unit_id = 'unit_{}_live'.format(session_id)

    q1 = phase_result(cache, 'Q1')
    q2 = phase_result(cache, 'Q2')
    q3 = phase_result(cache, 'Q3-1')

    row = {
        'row_id': row_id,
        'unit_id': unit_id,
        'session_id': session_id,
        'language': 'und',
        'status': 'live_appended',
        'created_at': now(),
        'articulation': {
            'past': articulation_from_result(q1),
            'present': articulation_from_result(q2),
            'future': articulation_from_result(q3),
        },
        'map': {
            'lng': pin.get('lng'),
            'lat': pin.get('lat'),
            'zoom_hint': pin.get('zoom', 13),
            'placement_mode': 'participant_pin',
            'seed_city': '',
            'seed_reason': 'Placed by participant through mobile map controller.',
        },
        'classification': combined_classification(cache),
        'keywords': {},
        'lod': {
            'cluster_id': '',
            'cluster_seed': [],
            'show_from_zoom': 10,
            'poem_from_zoom': 13,
        },
        'world_params': {
            'phase': 'future',
            'strength': 0.9,
            'radius': 0.32,
            'height': 0.7,
            'cluster_weight': 1.0,
        },
    }

    keywords = collect_row_keywords(row)
    row['keywords'] = {
        'all_original': keywords,
        'all_en': keywords,
    }
    row['lod']['cluster_seed'] = keywords[:8]
    row['lod']['cluster_id'] = choose_cluster(table, row, pin)
    return row


def append_lv1_to_lv2_table(cache):
    if cache.get('finalized_to_lv2'):
        return cache.get('lv2_row_id', '')

    pin = read_pin_from_ctrl()
    if pin is None:
        raise RuntimeError('Cannot append Lv2 row: missing map pin in pin_values.')

    table = read_json(LV2_TABLE_PATH, {})
    table.setdefault('schema_version', 'latent_home_table_v02')
    table.setdefault('rows', [])
    table.setdefault('clusters', [])

    session_id = cache.get('session_id', '')
    for row in table.get('rows') or []:
        if row.get('session_id') == session_id:
            cache['finalized_to_lv2'] = True
            cache['lv2_row_id'] = row.get('row_id', '')
            return row.get('row_id', '')

    row = build_lv2_row(cache, pin, table)
    table.setdefault('rows', []).append(row)
    update_cluster_metrics(table)
    table['updated_at'] = now()
    table['last_appended_session_id'] = session_id
    table['last_appended_row_id'] = row.get('row_id')
    write_json(LV2_TABLE_PATH, table)

    completed = {
        'schema': 'lv1_completed_session_v01',
        'completed_at': now(),
        'lv2_table': LV2_TABLE_PATH,
        'lv2_row_id': row.get('row_id'),
        'pin': pin,
        'cache': cache,
    }
    completed_path = os.path.join(COMPLETED_SESSION_DIR, 'session_{}.json'.format(session_id))
    write_json(completed_path, completed)

    cache['finalized_to_lv2'] = True
    cache['lv2_row_id'] = row.get('row_id')
    cache['completed_session_path'] = completed_path
    add_event(cache, 'lv2_row_appended', {
        'row_id': row.get('row_id'),
        'cluster_id': (row.get('lod') or {}).get('cluster_id', ''),
        'table': LV2_TABLE_PATH,
    })
    save_cache(cache)
    return row.get('row_id')


def schedule_poll(frames=POLL_DELAY_FRAMES):
    if in_td():
        me.run(delayFrames=frames)


def handle_final_reset_phase(cache, phase):
    if phase != FINAL_RESET_PHASE:
        return False

    cache['current_phase'] = phase
    try:
        row_id = append_lv1_to_lv2_table(cache)
        add_event(cache, 'final_reset_requested', {
            'from_phase': phase,
            'to_phase': FINAL_RESET_TARGET_PHASE,
            'lv2_row_id': row_id,
        })
        save_cache(cache)
    except Exception as e:
        cache['finalize_error'] = str(e)
        add_event(cache, 'lv2_append_error', {'error': str(e)})
        save_cache(cache)
        log('phase {} append failed: {}'.format(phase, e))
        return True

    if set_phase_value(FINAL_RESET_TARGET_PHASE):
        log('phase {} reset to {}'.format(phase, FINAL_RESET_TARGET_PHASE))
    else:
        log('phase {} reset failed: cannot set {}'.format(phase, PHASE_CHOP))
    return True


def handle_display_phase(cache, phase):
    question_id = DISPLAY_PHASES.get(phase)
    if not question_id:
        return False

    key = str(phase)
    displays = cache.setdefault('display_phases', {})
    state = displays.setdefault(key, {
        'phase': phase,
        'question_id': question_id,
        'entered_at': now(),
        'entered_epoch': time.time(),
        'pulse_sent': False,
    })

    if state.get('pulse_sent'):
        save_cache(cache)
        log('display phase {} already pulsed'.format(phase))
        return True

    elapsed = time.time() - float(state.get('entered_epoch', time.time()))
    if elapsed >= DISPLAY_HOLD_SECONDS:
        pulse_got_answer()
        state['pulse_sent'] = True
        state['pulsed_at'] = now()
        add_event(cache, 'display_auto_advance', {
            'phase': phase,
            'question_id': question_id,
            'hold_seconds': DISPLAY_HOLD_SECONDS,
        })
        save_cache(cache)
        log('auto advanced display phase {}'.format(phase))
        return True

    save_cache(cache)
    schedule_poll(DISPLAY_HOLD_FRAMES)
    log('holding display phase {} for {}s'.format(phase, DISPLAY_HOLD_SECONDS))
    return True


def start_worker(cache, phase, question_id):
    image_path = capture_path(question_id, phase)
    pulse_capture(image_path)

    old = (cache.get('questions') or {}).get(question_id) or {}
    attempt = int(old.get('attempt', 0) or 0) + 1
    cache.setdefault('questions', {})[question_id] = {
        'question_id': question_id,
        'phase': phase,
        'attempt': attempt,
        'status': 'running',
        'pulse_sent': False,
        'image_path': image_path,
        'started_at': now(),
        'started_epoch': time.time(),
    }
    add_event(cache, 'started', {'question_id': question_id, 'phase': phase})
    save_cache(cache)

    script = full_path(os.path.join('Assets', 'lv1_ai_simple.py'))
    cmd = [
        sys.executable,
        script,
        '--worker',
        '--phase', str(phase),
        '--question', question_id,
        '--image', image_path,
        '--cache', full_path(CACHE_PATH),
    ]
    stdout_path = full_path(WORKER_STDOUT_LOG)
    stderr_path = full_path(WORKER_STDERR_LOG)
    os.makedirs(os.path.dirname(stdout_path), exist_ok=True)
    stdout_file = open(stdout_path, 'a', encoding='utf-8')
    stderr_file = open(stderr_path, 'a', encoding='utf-8')
    kwargs = {
        'cwd': project_dir(),
        'stdout': stdout_file,
        'stderr': stderr_file,
    }
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(cmd, **kwargs)
    stdout_file.close()
    stderr_file.close()
    log('started {} phase {} cache {}'.format(question_id, phase, full_path(CACHE_PATH)))
    schedule_poll(CAPTURE_WAIT_FRAMES)


def run():
    cleanup_obsolete_td_ops()

    phase = read_phase()
    if phase is None:
        log('no phase')
        return

    if phase <= 0:
        log('idle phase {}'.format(phase))
        return

    if phase == RESET_PHASE:
        cache = new_cache(phase)
        add_event(cache, 'reset', {'phase': phase})
        save_cache(cache)
        log('reset phase 1')
        return

    cache = read_json(CACHE_PATH, new_cache(phase))
    cache['current_phase'] = phase
    save_cache(cache)

    if handle_final_reset_phase(cache, phase):
        return

    if handle_display_phase(cache, phase):
        return

    question_id = ANALYSIS_PHASES.get(phase)
    if not question_id:
        log('idle phase {}'.format(phase))
        return

    entry = (cache.get('questions') or {}).get(question_id) or {}
    status = entry.get('status')

    if status == 'complete':
        if not entry.get('pulse_sent'):
            pulse_got_answer()
            entry['pulse_sent'] = True
            add_event(cache, 'got_answer_pulsed', {'question_id': question_id, 'phase': phase})
            save_cache(cache)
            log('pulsed gotAnswer {}'.format(question_id))
        return

    if status == 'running':
        started = float(entry.get('started_epoch', time.time()))
        if time.time() - started > WORKER_TIMEOUT_SECONDS:
            entry['status'] = 'error'
            entry['error'] = 'timeout'
            add_event(cache, 'timeout', {'question_id': question_id, 'phase': phase})
            save_cache(cache)
            log('timeout {}'.format(question_id))
            return
        schedule_poll()
        log('waiting {}'.format(question_id))
        return

    start_worker(cache, phase, question_id)


def read_api_key():
    key_file = full_path(OPENAI_API_KEY_FILE)
    if os.path.isfile(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            key = f.read().strip()
        if key:
            return key
    return os.environ.get(OPENAI_API_KEY_ENV, '').strip()


def image_data_url(path):
    with open(path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('ascii')
    return 'data:image/png;base64,' + encoded


def parse_json_text(text):
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.strip('`').strip()
        if text.lower().startswith('json'):
            text = text[4:].strip()
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end >= start:
        text = text[start:end + 1]
    return json.loads(text)


def response_text(data):
    if data.get('output_text'):
        return data['output_text']
    parts = []
    for item in data.get('output', []):
        for content in item.get('content', []):
            if content.get('type') in ['output_text', 'text']:
                parts.append(content.get('text', ''))
    return '\n'.join(parts)


def openai_call(system_prompt, request_text, image_path):
    api_key = read_api_key()
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY is missing')

    model = os.environ.get(OPENAI_MODEL_ENV, DEFAULT_MODEL).strip() or DEFAULT_MODEL
    request_text = request_text.replace(
        '{{recognized_text}}',
        'Read the participant response from the attached image. Preserve it exactly as raw_response.'
    )
    body = {
        'model': model,
        'input': [{
            'role': 'user',
            'content': [
                {'type': 'input_text', 'text': system_prompt + '\n\n' + request_text},
                {'type': 'input_image', 'image_url': image_data_url(image_path)},
            ],
        }],
    }
    request = urllib.request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': 'Bearer ' + api_key,
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=WORKER_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode('utf-8'))
    return parse_json_text(response_text(data))


def worker_update(cache_path, question_id, fields, event_kind, event_detail=None):
    cache = read_json(cache_path, new_cache())
    entry = ((cache.setdefault('questions', {})).setdefault(question_id, {}))
    entry.update(fields)
    add_event(cache, event_kind, event_detail or {'question_id': question_id})
    write_json(cache_path, cache)
    write_json(MIRROR_PATH, make_mirror(cache))


def run_worker(args):
    deadline = time.time() + WORKER_WAIT_IMAGE_SECONDS
    while time.time() < deadline:
        if os.path.isfile(args.image) and os.path.getsize(args.image) > 0:
            break
        time.sleep(0.15)
    if not os.path.isfile(args.image):
        raise RuntimeError('capture image not found: {}'.format(args.image))

    system_prompt, phase_rows = read_prompts()
    request_text = (phase_rows.get(args.phase) or {}).get('AI Request', '').strip()
    if not request_text:
        raise RuntimeError('AI Request missing for phase {}'.format(args.phase))

    result = openai_call(system_prompt, request_text, args.image)
    result['question_id'] = args.question
    worker_update(args.cache, args.question, {
        'status': 'complete',
        'completed_at': now(),
        'result': result,
    }, 'complete', {'question_id': args.question, 'phase': args.phase})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--phase', type=int)
    parser.add_argument('--question')
    parser.add_argument('--image')
    parser.add_argument('--cache')
    args = parser.parse_args()
    if args.worker:
        try:
            run_worker(args)
        except Exception as e:
            worker_update(args.cache, args.question or '', {
                'status': 'error',
                'error': str(e),
                'completed_at': now(),
            }, 'error', {'error': str(e)})
            return 1
        return 0
    run()
    return 0


def onValueChange(channel, sampleIndex, val, prev):
    run()
    return


if in_td():
    try:
        run()
    except Exception as e:
        log('error {}'.format(e))
elif __name__ == '__main__':
    sys.exit(main())
