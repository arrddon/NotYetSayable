import copy
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / 'Data' / 'latent_home_table_v02.json'


SYNTHETIC_ROWS = [
    ('London', 'Connection', -0.1278, 51.5074, 'A shared kitchen above a bus route remembers everyone by the sound of their keys.', ['shared kitchen', 'bus route', 'keys', 'neighbours', 'arrival']),
    ('London', 'Temporary Shelter', -0.0754, 51.5145, 'Cardboard boxes line a rented room, but the window keeps a small square of sky.', ['rented room', 'boxes', 'window', 'temporary', 'sky']),
    ('London', 'Care', -0.1425, 51.5010, 'A kettle clicks on before anyone speaks, making care visible as steam.', ['kettle', 'steam', 'care', 'morning', 'quiet']),
    ('London', 'Memory', -0.2360, 51.5126, 'The smell of rain on brick carries a childhood street into the present.', ['rain', 'brick', 'childhood street', 'memory', 'pavement']),
    ('London', 'Connection', -0.0206, 51.5450, 'A market stall becomes a map of names, accents, and remembered recipes.', ['market', 'names', 'recipes', 'accents', 'belonging']),
    ('Paris', 'Memory', 2.3522, 48.8566, 'An apartment stairwell holds the echo of dinners that ended very late.', ['stairwell', 'dinners', 'echo', 'apartment', 'late night']),
    ('Berlin', 'Temporary Shelter', 13.4050, 52.5200, 'A sublet room changes hands, carrying tape marks from other futures.', ['sublet', 'tape marks', 'future', 'room', 'transition']),
    ('Amsterdam', 'Care', 4.9041, 52.3676, 'Bicycles gather by the canal like promises that someone will return.', ['bicycles', 'canal', 'return', 'promise', 'care']),
    ('Barcelona', 'Future Commons', 2.1734, 41.3851, 'A terrace garden imagines a home shared with heat, shade, and strangers.', ['terrace', 'garden', 'shade', 'shared home', 'heat']),
    ('Copenhagen', 'Connection', 12.5683, 55.6761, 'Warm windows form a constellation for people crossing winter streets.', ['warm windows', 'winter', 'streets', 'constellation', 'connection']),
    ('Lisbon', 'Memory', -9.1393, 38.7223, 'Tiles keep the sea inside the wall, blue memory repeating by hand.', ['tiles', 'sea', 'blue', 'wall', 'memory']),
    ('Milan', 'Future Commons', 9.1900, 45.4642, 'A courtyard becomes a soft machine for shade, laundry, and shared repair.', ['courtyard', 'shade', 'laundry', 'repair', 'commons']),
    ('Seoul', 'Connection', 126.9780, 37.5665, 'An elevator ride is brief, but the hallway remembers every small greeting.', ['elevator', 'hallway', 'greeting', 'apartment', 'connection']),
    ('Seoul', 'Care', 127.0276, 37.4979, 'Soup steam rises from a late table, making the room larger than its walls.', ['soup', 'steam', 'late table', 'walls', 'care']),
    ('Seoul', 'Temporary Shelter', 126.9236, 37.5563, 'A studio room folds bed, desk, and future into the same bright corner.', ['studio', 'bed', 'desk', 'future', 'corner']),
    ('Seoul', 'Memory', 126.9946, 37.5796, 'A hanok roofline returns in dreams as a quiet angle of protection.', ['hanok', 'roofline', 'dreams', 'protection', 'memory']),
    ('Seoul', 'Future Commons', 127.0496, 37.5145, 'A riverside tower imagines neighbours meeting first through plants.', ['riverside', 'tower', 'plants', 'neighbours', 'future']),
    ('Seoul', 'Connection', 126.9368, 37.5559, 'The last train home gathers tired strangers into one temporary pulse.', ['last train', 'strangers', 'pulse', 'home', 'night']),
]


CLUSTER_BY_THEME = {
    'Connection': 'cluster_connection',
    'Temporary Shelter': 'cluster_temporary_shelter',
    'Care': 'cluster_care',
    'Memory': 'cluster_memory',
    'Future Commons': 'cluster_future_commons',
}


def phase_block(raw, keywords, phrase):
    return {
        'raw_fragments': [raw],
        'keywords_original': keywords,
        'keywords_en': keywords,
        'poetry_original': [raw, phrase],
        'poetry_en': [phrase],
    }


def make_row(index, city, theme, lng, lat, phrase, keywords):
    row_id = 'row_{:04d}'.format(index)
    session_id = 'test_{:04d}'.format(index)
    created = datetime(2026, 7, 9, 15, 0, 0) + timedelta(minutes=index)
    cluster_id = CLUSTER_BY_THEME.get(theme, 'cluster_live_unassigned')
    raw_past = 'A remembered home in {} begins with {}.'.format(city, keywords[0])
    raw_present = 'The present condition carries {}, {}, and {}.'.format(keywords[1], keywords[2], keywords[3])
    raw_future = phrase

    return {
        'row_id': row_id,
        'unit_id': 'unit_{}_live'.format(session_id),
        'session_id': session_id,
        'language': 'en',
        'status': 'test_appended',
        'created_at': created.isoformat() + 'Z',
        'articulation': {
            'past': phase_block(raw_past, keywords[:4], phrase),
            'present': phase_block(raw_present, keywords[1:5], phrase),
            'future': phase_block(raw_future, keywords, phrase),
        },
        'map': {
            'lng': lng,
            'lat': lat,
            'zoom_hint': 12.0,
            'placement_mode': 'synthetic_test_pin',
            'seed_city': city,
            'seed_reason': 'Synthetic Lv2 navigation test data.',
        },
        'classification': {
            'primary_theme': theme,
            'confidence': 0.82,
            'reason': 'Synthetic variation for Lv2 navigation testing.',
            'source': 'test_seed',
        },
        'keywords': {
            'all_original': keywords,
            'all_en': keywords,
        },
        'lod': {
            'cluster_id': cluster_id,
            'cluster_seed': keywords[:8],
            'show_from_zoom': 10,
            'poem_from_zoom': 13,
        },
        'world_params': {
            'phase': 'future',
            'strength': 0.75,
            'radius': 0.28,
            'height': 0.62,
            'cluster_weight': 1.0,
        },
        'cluster_metrics': {},
    }


def update_cluster_metrics(table):
    rows = table.get('rows') or []
    cluster_members = defaultdict(list)

    for row in rows:
        cid = (row.get('lod') or {}).get('cluster_id') or 'cluster_live_unassigned'
        cluster_members[cid].append(row)

    max_members = max([len(members) for members in cluster_members.values()] or [1])
    clusters = []

    for cid, members in sorted(cluster_members.items()):
        lngs = []
        lats = []
        theme_counts = Counter()
        keyword_counts = Counter()
        poetry = []

        for row in members:
            map_data = row.get('map') or {}
            if map_data.get('lng') is not None and map_data.get('lat') is not None:
                lngs.append(float(map_data.get('lng')))
                lats.append(float(map_data.get('lat')))

            theme = (row.get('classification') or {}).get('primary_theme', 'Unassigned')
            theme_counts[theme] += 1

            for keyword in (row.get('keywords') or {}).get('all_en', []):
                keyword_counts[str(keyword)] += 1

            future_poetry = ((row.get('articulation') or {}).get('future') or {}).get('poetry_en') or []
            for line in future_poetry:
                if line and line not in poetry:
                    poetry.append(line)

        member_count = len(members)
        primary_theme, primary_count = theme_counts.most_common(1)[0]
        sorted_keywords = keyword_counts.most_common(16)

        cluster = {
            'cluster_id': cid,
            'lod': 1,
            'zoom_min': 0,
            'zoom_max': 10,
            'basis': 'test_seed' if cid.startswith('cluster_') else 'live_append',
            'center_lng': round(sum(lngs) / len(lngs), 6) if lngs else 0,
            'center_lat': round(sum(lats) / len(lats), 6) if lats else 0,
            'radius_km': round(25 + 8 * math.sqrt(member_count), 3),
            'member_count': member_count,
            'member_row_ids': [row.get('row_id') for row in members if row.get('row_id')],
            'classification_counts': dict(theme_counts),
            'primary_theme': primary_theme,
            'primary_theme_count': primary_count,
            'primary_theme_ratio': round(primary_count / float(member_count), 3) if member_count else 0,
            'keyword_counts': dict(sorted_keywords),
            'dominant_keywords': [item[0] for item in sorted_keywords[:8]],
            'display_poetry_en': poetry[:5],
            'text_scale': round(0.85 + 1.15 * math.sqrt(member_count / float(max_members)), 3),
            'text_weight': round(member_count * max(primary_count / float(member_count), 0.25), 3) if member_count else 0,
        }
        clusters.append(cluster)

        for row in members:
            theme = (row.get('classification') or {}).get('primary_theme', 'Unassigned')
            row['cluster_metrics'] = {
                'cluster_id': cid,
                'cluster_member_count': member_count,
                'theme_frequency_in_cluster': int(theme_counts.get(theme, 1)),
                'theme_ratio_in_cluster': round(theme_counts.get(theme, 1) / float(max(member_count, 1)), 3),
                'text_scale': cluster['text_scale'],
            }

    table['clusters'] = clusters


def main():
    table = json.loads(TABLE_PATH.read_text(encoding='utf-8'))
    rows = table.setdefault('rows', [])

    existing = rows[:20]
    next_index = len(existing) + 1
    template_rows = []

    for spec in SYNTHETIC_ROWS:
        if len(existing) + len(template_rows) >= 20:
            break
        template_rows.append(make_row(next_index, *spec))
        next_index += 1

    table['rows'] = existing + template_rows
    update_cluster_metrics(table)
    table['last_appended_session_id'] = table['rows'][-1].get('session_id', '') if table['rows'] else ''
    table['last_appended_row_id'] = table['rows'][-1].get('row_id', '') if table['rows'] else ''
    table['updated_at'] = datetime.utcnow().isoformat() + 'Z'

    TABLE_PATH.write_text(json.dumps(table, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
