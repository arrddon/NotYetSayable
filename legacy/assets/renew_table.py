import json
import math
import os

CTRL = 'ctrl_values'
MAP_TOP = 'map_render'
DATA_FILE = os.path.join('Data', 'latent_home_table_v02.json')

OUT_DATA = 'current_data'
OUT_TEXT = 'current_text'
OUT_COPY_POINTS = 'copy_points'
OUT_PIN_POINTS = 'current_pin_points'
OUT_NAV_TARGETS = 'current_nav_targets'
OUT_DEBUG = 'current_debug'
LEGACY_OUTPUTS = [OUT_DATA, OUT_TEXT, OUT_COPY_POINTS, OUT_DEBUG]

TILE_SIZE = 256
COPY_LONG_EDGE = 1.75
COPY_MATCH_MAP_ASPECT = True
FALLBACK_PIXEL_W = 1920.0
FALLBACK_PIXEL_H = 1080.0
MARGIN = 1.35

MAX_OBJECTS = 80
MAX_CLUSTER_OBJECTS = 24
MAX_TEXT_LINES = 180
MAX_NAV_TARGETS = 160
MAX_PIN_POINTS = 30
RECENT_PIN_TARGETS = 12

NAV_INDEX_CHOPS = ['nav_index', 'nav_target_index', 'auto_nav_index', 'nav_select']

LOD_GLOBAL_MAX = 3.5
LOD_CLUSTER_MAX = 10.0
LOD_SHORT_TEXT_MAX = 13.0
LOD_FULL_CONTEXT_ZOOM = 14.5


def td_parent():
    try:
        return me.parent()
    except Exception:
        return None


def get_project_folder():
    try:
        return project.folder
    except Exception:
        return os.getcwd()


def get_table(name):
    t = op(name)
    if t is not None:
        return t

    owner = td_parent()
    if owner is None:
        return None

    try:
        return owner.create(tableDAT, name)
    except Exception:
        return None


def get_text_dat(name):
    t = op(name)
    if t is not None:
        return t

    owner = td_parent()
    if owner is None:
        return None

    try:
        return owner.create(textDAT, name)
    except Exception:
        return None


def clear_with_header(table, header):
    if table is None:
        return
    table.clear()
    table.appendRow(header)


def clear_existing_table(name):
    table = op(name)
    if table is None:
        return
    try:
        table.clear()
    except Exception:
        pass


def clear_legacy_outputs():
    for name in LEGACY_OUTPUTS:
        clear_existing_table(name)


def store_value(key, value):
    owner = td_parent()
    if owner is None:
        return
    try:
        owner.store(key, value)
    except Exception:
        pass


def fetch_value(key, default=None):
    owner = td_parent()
    if owner is None:
        return default
    try:
        return owner.fetch(key, default)
    except Exception:
        return default


def debug_log(*args):
    try:
        debug(*args)
    except Exception:
        pass


def load_latent_table():
    path = os.path.join(get_project_folder(), DATA_FILE)
    mtime = os.path.getmtime(path)

    cached = fetch_value('latent_home_table_cache', None)
    if cached and cached.get('mtime') == mtime:
        return cached.get('data', {})

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    store_value('latent_home_table_cache', {
        'mtime': mtime,
        'data': data
    })

    return data


def mercator(lng, lat, zoom):
    world = TILE_SIZE * (2 ** zoom)

    x = (lng + 180.0) / 360.0 * world

    lat = max(min(lat, 85.05112878), -85.05112878)
    lat_rad = math.radians(lat)

    y = (
        1.0
        - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi
    ) / 2.0 * world

    return x, y


def get_ctrl():
    t = op(CTRL)
    vals = {}

    if t is None:
        return 0.0, 20.0, 2.0

    for r in range(t.numRows):
        key = t[r, 0].val.strip()
        val = t[r, 1].val.strip()
        vals[key] = val

    lng = float(vals.get('lng', 0) or 0)
    lat = float(vals.get('lat', 20) or 20)
    zoom = float(vals.get('zoom', 2) or 2)

    return lng, lat, zoom


def get_ctrl_values():
    table = op(CTRL)
    values = {}

    if table is None:
        return values

    for row in range(table.numRows):
        try:
            key = table[row, 0].val.strip()
            value = table[row, 1].val.strip()
            if key:
                values[key] = value
        except Exception:
            pass

    return values


def apply_map_render_view(lng, lat, zoom):
    map_top = op(MAP_TOP)
    if map_top is None:
        return

    js = '''
    if (window.td_setView) {
        window.td_setView(%f, %f, %f);
    }
    ''' % (float(lng), float(lat), float(zoom))

    try:
        map_top.executeJavaScript(js)
    except Exception as e:
        debug_log('map_render view apply failed', e)


def read_chop_value(chop_name, channel_name=None, default=0.0):
    c = op(chop_name)
    if c is None:
        return default

    try:
        if channel_name and channel_name in c:
            return float(c[channel_name][0])
    except Exception:
        pass

    try:
        return float(c[0][0])
    except Exception:
        return default


def get_nav_index(nav_count):
    if nav_count <= 0:
        return 0

    raw_index = 0
    found = False
    for chop_name in NAV_INDEX_CHOPS:
        if op(chop_name) is not None:
            raw_index = int(round(read_chop_value(chop_name, None, 0.0)))
            found = True
            break

    if not found:
        values = get_ctrl_values()
        try:
            raw_index = int(round(float(values.get('nav_index', 0) or 0)))
        except Exception:
            raw_index = 0

    return raw_index % nav_count


def get_render_size():
    map_top = op(MAP_TOP)
    if map_top is None:
        return FALLBACK_PIXEL_W, FALLBACK_PIXEL_H

    w = float(map_top.width)
    h = float(map_top.height)

    if w <= 0 or h <= 0:
        return FALLBACK_PIXEL_W, FALLBACK_PIXEL_H

    return w, h


def get_world_size(render_w, render_h):
    if not COPY_MATCH_MAP_ASPECT:
        return COPY_LONG_EDGE, COPY_LONG_EDGE

    if render_w <= 0 or render_h <= 0:
        return COPY_LONG_EDGE, COPY_LONG_EDGE

    aspect = render_w / render_h

    if aspect >= 1.0:
        return COPY_LONG_EDGE, COPY_LONG_EDGE / aspect

    return COPY_LONG_EDGE * aspect, COPY_LONG_EDGE


def project_to_world(lng, lat, center_lng, center_lat, zoom, render_w, render_h):
    cx, cy = mercator(center_lng, center_lat, zoom)
    ox, oy = mercator(lng, lat, zoom)

    dx = ox - cx
    dy = oy - cy

    world_w, world_h = get_world_size(render_w, render_h)

    tx = dx / render_w * world_w
    ty = -dy / render_h * world_h

    dist_px = math.sqrt(dx * dx + dy * dy)

    return tx, ty, dx, dy, dist_px


def in_view(dx, dy, render_w, render_h):
    return (
        abs(dx) <= render_w * MARGIN * 0.5 and
        abs(dy) <= render_h * MARGIN * 0.5
    )


def active_lod(zoom):
    if zoom < LOD_GLOBAL_MAX:
        return 0
    if zoom < LOD_CLUSTER_MAX:
        return 1
    if zoom < LOD_SHORT_TEXT_MAX:
        return 2
    return 3


def list_to_text(items, sep=', '):
    if not items:
        return ''
    return sep.join([str(x) for x in items])


def dict_to_text(items, item_sep=', ', key_sep=':'):
    if not items:
        return ''
    parts = []
    for key, value in items.items():
        parts.append('{}{}{}'.format(key, key_sep, value))
    return item_sep.join(parts)


def row_classification(row):
    classification = row.get('classification') or {}
    return {
        'primary_theme': classification.get('primary_theme', ''),
        'confidence': classification.get('confidence', ''),
        'reason': classification.get('reason', ''),
    }


def row_text_scale(row):
    metrics = row.get('cluster_metrics') or {}
    try:
        return float(metrics.get('text_scale', 1.0))
    except Exception:
        return 1.0


def phase_poetry(row, phase, prefer_original=True):
    art = row.get('articulation', {}).get(phase, {})
    if prefer_original:
        lines = art.get('poetry_original') or art.get('poetry_en') or []
    else:
        lines = art.get('poetry_en') or art.get('poetry_original') or []
    return [str(x) for x in lines if str(x).strip()]


def short_label_for_row(row):
    future = row.get('articulation', {}).get('future', {})
    lines = future.get('poetry_original') or future.get('poetry_en') or []
    if lines:
        return str(lines[0])

    keywords = future.get('keywords_original') or future.get('keywords_en') or []
    if keywords:
        return list_to_text(keywords[:3])

    return ''


def english_label_for_row(row):
    future = row.get('articulation', {}).get('future', {})
    lines = future.get('poetry_en') or future.get('poetry_original') or []
    if lines:
        return str(lines[0])
    return short_label_for_row(row)


def cluster_label(cluster):
    lines = cluster.get('display_poetry_en') or []
    if lines:
        return str(lines[0])

    keywords = cluster.get('dominant_keywords') or []
    if keywords:
        return list_to_text(keywords[:3])

    return ''


def get_current_clusters(data, zoom):
    clusters = data.get('clusters', [])
    lod = active_lod(zoom)

    if lod == 0:
        return clusters[:MAX_CLUSTER_OBJECTS]

    if lod == 1:
        active = []
        for c in clusters:
            zmin = float(c.get('zoom_min', 0))
            zmax = float(c.get('zoom_max', 99))
            if zmin <= zoom < zmax:
                active.append(c)
        return active[:MAX_CLUSTER_OBJECTS]

    return []


def row_visible_at_zoom(row, zoom):
    lod = row.get('lod', {})
    show_from = float(lod.get('show_from_zoom', LOD_CLUSTER_MAX))
    return zoom >= show_from


def build_cluster_object(cluster, center_lng, center_lat, zoom, render_w, render_h):
    lng = float(cluster.get('center_lng', 0))
    lat = float(cluster.get('center_lat', 0))
    tx, ty, dx, dy, dist_px = project_to_world(
        lng, lat, center_lng, center_lat, zoom, render_w, render_h
    )

    if not in_view(dx, dy, render_w, render_h) and active_lod(zoom) > 1:
        return None

    members = cluster.get('member_row_ids') or []
    member_count = len(members)
    weight = max(1.0, math.sqrt(max(member_count, 1)))
    radius = 0.28 + min(member_count, 10) * 0.035
    strength = 0.45 + min(member_count, 10) * 0.06

    label = cluster_label(cluster)
    text_scale = float(cluster.get('text_scale', 1.0))

    return {
        'id': cluster.get('cluster_id', 'cluster'),
        'kind': 'cluster',
        'lod': active_lod(zoom),
        'cluster_id': cluster.get('cluster_id', ''),
        'row_id': '',
        'lng': lng,
        'lat': lat,
        'px': tx,
        'py': ty,
        'pz': 0.0,
        'strength': min(strength, 1.2),
        'radius': radius,
        'height': 0.45 + min(member_count, 10) * 0.04,
        'weight': weight,
        'member_count': member_count,
        'language': 'en',
        'seed_city': '',
        'text_key': list_to_text((cluster.get('dominant_keywords') or [])[:4]),
        'text_display': label,
        'primary_theme': cluster.get('primary_theme', ''),
        'classification_counts': dict_to_text(cluster.get('classification_counts') or {}),
        'keyword_counts': dict_to_text(cluster.get('keyword_counts') or {}),
        'theme_frequency': cluster.get('primary_theme_count', 0),
        'theme_ratio': cluster.get('primary_theme_ratio', 0),
        'text_scale': text_scale,
        'dist_px': dist_px,
        'source': cluster
    }


def build_unit_object(row, center_lng, center_lat, zoom, render_w, render_h):
    map_data = row.get('map', {})
    lng = map_data.get('lng')
    lat = map_data.get('lat')

    if lng is None or lat is None:
        return None

    lng = float(lng)
    lat = float(lat)

    tx, ty, dx, dy, dist_px = project_to_world(
        lng, lat, center_lng, center_lat, zoom, render_w, render_h
    )

    if not in_view(dx, dy, render_w, render_h):
        return None

    world = row.get('world_params', {})
    label = short_label_for_row(row)
    classification = row_classification(row)
    metrics = row.get('cluster_metrics') or {}

    return {
        'id': row.get('unit_id', row.get('row_id', 'unit')),
        'kind': 'unit',
        'lod': active_lod(zoom),
        'cluster_id': row.get('lod', {}).get('cluster_id', ''),
        'row_id': row.get('row_id', ''),
        'lng': lng,
        'lat': lat,
        'px': tx,
        'py': ty,
        'pz': 0.0,
        'strength': float(world.get('strength', 0.8)),
        'radius': float(world.get('radius', 0.3)),
        'height': float(world.get('height', 0.6)),
        'weight': float(world.get('cluster_weight', 1.0)),
        'member_count': 1,
        'language': row.get('language', ''),
        'seed_city': map_data.get('seed_city', ''),
        'text_key': list_to_text(row.get('lod', {}).get('cluster_seed', [])[:4]),
        'text_display': label,
        'primary_theme': classification.get('primary_theme', ''),
        'classification_counts': '',
        'keyword_counts': list_to_text((row.get('keywords') or {}).get('all_en') or []),
        'theme_frequency': metrics.get('theme_frequency_in_cluster', 1),
        'theme_ratio': metrics.get('theme_ratio_in_cluster', 1),
        'text_scale': row_text_scale(row),
        'dist_px': dist_px,
        'source': row
    }


def append_data_rows(table, objects):
    clear_with_header(table, [
        'id', 'kind', 'lod', 'cluster_id', 'row_id',
        'lng', 'lat',
        'strength', 'radius', 'height', 'weight', 'member_count',
        'language', 'seed_city', 'text_key', 'text_display',
        'primary_theme', 'theme_frequency', 'theme_ratio', 'text_scale'
    ])

    if table is None:
        return

    for item in objects:
        table.appendRow([
            item['id'],
            item['kind'],
            item['lod'],
            item['cluster_id'],
            item['row_id'],
            item['lng'],
            item['lat'],
            item['strength'],
            item['radius'],
            item['height'],
            item['weight'],
            item['member_count'],
            item['language'],
            item['seed_city'],
            item['text_key'],
            item['text_display'],
            item.get('primary_theme', ''),
            item.get('theme_frequency', ''),
            item.get('theme_ratio', ''),
            item.get('text_scale', 1.0)
        ])


def append_copy_points(table, objects):
    clear_with_header(table, ['P0', 'P1', 'P2'])

    if table is None:
        return

    for item in objects:
        table.appendRow([
            item.get('px', 0.0),
            item.get('py', 0.0),
            item.get('pz', 0.0)
        ])


def valid_pin_rows(data):
    rows = []
    for row in (data.get('rows', []) if isinstance(data, dict) else []):
        map_data = row.get('map') or {}
        if map_data.get('lng') is None or map_data.get('lat') is None:
            continue
        rows.append(row)
    return rows


def build_pin_points(data, center_lng, center_lat, zoom, render_w, render_h):
    points = []
    last_row_id = data.get('last_appended_row_id', '') if isinstance(data, dict) else ''
    rows = sorted(valid_pin_rows(data), key=row_created_at, reverse=True)

    for row in rows:
        if len(points) >= MAX_PIN_POINTS:
            break

        map_data = row.get('map') or {}
        lng = map_data.get('lng')
        lat = map_data.get('lat')
        if lng is None or lat is None:
            continue

        try:
            lng = float(lng)
            lat = float(lat)
        except Exception:
            continue

        px, py, dx, dy, dist_px = project_to_world(
            lng, lat, center_lng, center_lat, zoom, render_w, render_h
        )
        visible = in_view(dx, dy, render_w, render_h)
        if not visible:
            continue

        cluster_id = (row.get('lod') or {}).get('cluster_id', '')
        is_new = 1 if row.get('row_id') == last_row_id else 0

        points.append({
            'index': len(points),
            'P0': px,
            'P1': py,
            'P2': 0.03,
            'row_id': row.get('row_id', ''),
            'unit_id': row.get('unit_id', ''),
            'cluster_id': cluster_id,
            'lng': lng,
            'lat': lat,
            'dist_px': round(dist_px, 3),
            'in_view': 1,
            'is_new': is_new,
            'primary_theme': (row.get('classification') or {}).get('primary_theme', ''),
            'label': nav_label_for_row(row),
            'member_count': 1,
        })

    return points


def append_pin_points(table, points):
    clear_with_header(table, [
        'index', 'P0', 'P1', 'P2',
        'row_id', 'unit_id', 'cluster_id',
        'lng', 'lat', 'dist_px', 'in_view', 'is_new',
        'primary_theme', 'label', 'member_count'
    ])

    if table is None:
        return

    for point in points:
        table.appendRow([
            point.get('index', ''),
            point.get('P0', 0.0),
            point.get('P1', 0.0),
            point.get('P2', 0.0),
            point.get('row_id', ''),
            point.get('unit_id', ''),
            point.get('cluster_id', ''),
            point.get('lng', ''),
            point.get('lat', ''),
            point.get('dist_px', ''),
            point.get('in_view', 0),
            point.get('is_new', 0),
            point.get('primary_theme', ''),
            point.get('label', ''),
            point.get('member_count', 1),
        ])


def add_text_line(lines, parent, phase, line_index, line_count, text_original, text_en,
                  language, kind):
    if len(lines) >= MAX_TEXT_LINES:
        return

    lines.append({
        'text_id': '{}_{}_{}'.format(parent['id'], phase, line_index),
        'parent_id': parent['id'],
        'kind': kind,
        'phase': phase,
        'line_index': line_index,
        'line_count': line_count,
        'language': language,
        'text_original': text_original,
        'text_en': text_en,
        'text_display': text_original or text_en,
        'primary_theme': parent.get('primary_theme', ''),
        'theme_frequency': parent.get('theme_frequency', ''),
        'theme_ratio': parent.get('theme_ratio', ''),
        'text_scale': parent.get('text_scale', 1.0)
    })


def build_text_rows(objects, zoom):
    lines = []

    for item in objects:
        source = item.get('source', {})

        if item['kind'] == 'cluster':
            poem = source.get('display_poetry_en') or [item['text_display']]
            text = ' / '.join([str(x) for x in poem[:4]])
            add_text_line(
                lines, item, 'cluster', 0, 1, text, text,
                'en', 'cluster'
            )
            continue

        row = source
        language = row.get('language', '')
        poem_zoom = float(row.get('lod', {}).get('poem_from_zoom', LOD_SHORT_TEXT_MAX))

        if zoom < poem_zoom:
            text_original = short_label_for_row(row)
            text_en = english_label_for_row(row)
            add_text_line(
                lines, item, 'future', 0, 1, text_original, text_en,
                language, 'unit'
            )
            continue

        phases = ['future']
        if zoom >= LOD_FULL_CONTEXT_ZOOM:
            phases = ['past', 'present', 'future']

        original_parts = []
        english_parts = []
        for phase in phases:
            original_parts.extend(phase_poetry(row, phase, True)[:6])
            english_parts.extend(phase_poetry(row, phase, False)[:6])

        text_original = ' / '.join(original_parts)
        text_en = ' / '.join(english_parts)

        add_text_line(
            lines,
            item,
            'mixed' if len(phases) > 1 else 'future',
            0,
            1,
            text_original,
            text_en,
            language,
            'unit'
        )

    return lines[:MAX_TEXT_LINES]


def append_text_rows(table, lines):
    clear_with_header(table, [
        'text_id', 'parent_id', 'kind', 'phase', 'line_index', 'line_count',
        'language', 'text_original', 'text_en', 'text_display',
        'primary_theme', 'theme_frequency', 'theme_ratio', 'text_scale'
    ])

    if table is None:
        return

    for line in lines:
        table.appendRow([
            line['text_id'],
            line['parent_id'],
            line['kind'],
            line['phase'],
            line['line_index'],
            line['line_count'],
            line['language'],
            line['text_original'],
            line['text_en'],
            line['text_display'],
            line.get('primary_theme', ''),
            line.get('theme_frequency', ''),
            line.get('theme_ratio', ''),
            line.get('text_scale', 1.0)
        ])


def row_created_at(row):
    return row.get('created_at') or row.get('updated_at') or ''


def nav_label_for_row(row):
    label = short_label_for_row(row)
    if label:
        return label
    classification = row.get('classification') or {}
    return classification.get('primary_theme', '') or row.get('unit_id', '')


def nav_priority_for_row(row, is_new):
    metrics = row.get('cluster_metrics') or {}
    classification = row.get('classification') or {}
    try:
        text_scale = float(metrics.get('text_scale', 1.0))
    except Exception:
        text_scale = 1.0
    try:
        confidence = float(classification.get('confidence', 0.5) or 0.5)
    except Exception:
        confidence = 0.5
    priority = text_scale * 10.0 + confidence
    if is_new:
        priority += 1000.0
    return round(priority, 3)


def sorted_recent_rows(rows):
    eligible = []
    for row in rows or []:
        map_data = row.get('map') or {}
        if map_data.get('lng') is None or map_data.get('lat') is None:
            continue
        eligible.append(row)
    return sorted(eligible, key=row_created_at, reverse=True)


def build_nav_targets(data):
    targets = []
    last_appended_row_id = data.get('last_appended_row_id', '')
    cluster_lookup = {}

    for cluster in data.get('clusters', []) or []:
        cid = cluster.get('cluster_id', '')
        if cid:
            cluster_lookup[cid] = cluster

    for cluster in data.get('clusters', []) or []:
        lng = cluster.get('center_lng')
        lat = cluster.get('center_lat')
        if lng is None or lat is None:
            continue

        member_count = len(cluster.get('member_row_ids') or [])
        try:
            text_scale = float(cluster.get('text_scale', 1.0))
        except Exception:
            text_scale = 1.0

        targets.append({
            'kind': 'cluster',
            'target_id': 'nav_cluster_{}'.format(cluster.get('cluster_id', '')),
            'highlight_id': cluster.get('cluster_id', ''),
            'row_id': '',
            'unit_id': '',
            'cluster_id': cluster.get('cluster_id', ''),
            'lng': float(lng),
            'lat': float(lat),
            'pin_lng': '',
            'pin_lat': '',
            'cluster_center_lng': float(lng),
            'cluster_center_lat': float(lat),
            'zoom_in': 8.0,
            'zoom_out': 3.0,
            'hold_seconds': 8.0,
            'priority': round(20.0 + member_count + text_scale, 3),
            'primary_theme': cluster.get('primary_theme', ''),
            'theme_frequency': cluster.get('primary_theme_count', ''),
            'theme_ratio': cluster.get('primary_theme_ratio', ''),
            'text_scale': text_scale,
            'label': cluster_label(cluster),
            'is_new': 0,
            'created_at': '',
        })

    recent_rows = sorted_recent_rows(data.get('rows', []))[:RECENT_PIN_TARGETS]

    for recent_rank, row in enumerate(recent_rows):
        map_data = row.get('map') or {}
        lng = map_data.get('lng')
        lat = map_data.get('lat')
        if lng is None or lat is None:
            continue

        metrics = row.get('cluster_metrics') or {}
        classification = row.get('classification') or {}
        is_new = 1 if row.get('row_id') == last_appended_row_id else 0

        cluster_id = (row.get('lod') or {}).get('cluster_id', '')
        cluster = cluster_lookup.get(cluster_id, {})
        cluster_lng = cluster.get('center_lng', lng)
        cluster_lat = cluster.get('center_lat', lat)

        try:
            text_scale = float(metrics.get('text_scale', 1.0))
        except Exception:
            text_scale = 1.0

        targets.append({
            'kind': 'new_unit' if is_new else 'recent_unit',
            'target_id': 'nav_unit_{}'.format(row.get('row_id', '')),
            'highlight_id': row.get('unit_id', row.get('row_id', '')),
            'row_id': row.get('row_id', ''),
            'unit_id': row.get('unit_id', ''),
            'cluster_id': cluster_id,
            'lng': float(lng),
            'lat': float(lat),
            'pin_lng': float(lng),
            'pin_lat': float(lat),
            'cluster_center_lng': float(cluster_lng),
            'cluster_center_lat': float(cluster_lat),
            'zoom_in': float(map_data.get('zoom_hint', 13) or 13),
            'zoom_out': 6.0,
            'hold_seconds': 20.0 if is_new else 10.0,
            'priority': nav_priority_for_row(row, is_new) + max(0, RECENT_PIN_TARGETS - recent_rank),
            'primary_theme': classification.get('primary_theme', ''),
            'theme_frequency': metrics.get('theme_frequency_in_cluster', ''),
            'theme_ratio': metrics.get('theme_ratio_in_cluster', ''),
            'text_scale': text_scale,
            'label': nav_label_for_row(row),
            'is_new': is_new,
            'created_at': row_created_at(row),
        })

    targets.sort(key=lambda item: (int(item.get('is_new', 0)), float(item.get('priority', 0))), reverse=True)

    for index, target in enumerate(targets[:MAX_NAV_TARGETS]):
        target['target_index'] = index

    return targets[:MAX_NAV_TARGETS]


def append_nav_target_rows(table, targets):
    clear_with_header(table, [
        'target_index', 'target_id', 'kind', 'highlight_id',
        'row_id', 'unit_id', 'cluster_id',
        'lng', 'lat', 'pin_lng', 'pin_lat',
        'cluster_center_lng', 'cluster_center_lat',
        'zoom_in', 'zoom_out', 'hold_seconds',
        'priority', 'primary_theme', 'theme_frequency', 'theme_ratio',
        'text_scale', 'label', 'is_new', 'created_at'
    ])

    if table is None:
        return

    for target in targets:
        table.appendRow([
            target.get('target_index', ''),
            target.get('target_id', ''),
            target.get('kind', ''),
            target.get('highlight_id', ''),
            target.get('row_id', ''),
            target.get('unit_id', ''),
            target.get('cluster_id', ''),
            target.get('lng', ''),
            target.get('lat', ''),
            target.get('pin_lng', ''),
            target.get('pin_lat', ''),
            target.get('cluster_center_lng', ''),
            target.get('cluster_center_lat', ''),
            target.get('zoom_in', ''),
            target.get('zoom_out', ''),
            target.get('hold_seconds', ''),
            target.get('priority', ''),
            target.get('primary_theme', ''),
            target.get('theme_frequency', ''),
            target.get('theme_ratio', ''),
            target.get('text_scale', ''),
            target.get('label', ''),
            target.get('is_new', 0),
            target.get('created_at', ''),
        ])


def append_debug(table, data, center_lng, center_lat, zoom, lod, object_count, text_count,
                 render_w, render_h, nav_count=0, pin_count=0):
    clear_with_header(table, ['key', 'value'])

    if table is None:
        return

    table.appendRow(['data_file', DATA_FILE])
    table.appendRow(['schema_version', data.get('schema_version', '') if isinstance(data, dict) else ''])
    table.appendRow(['center_lng', center_lng])
    table.appendRow(['center_lat', center_lat])
    table.appendRow(['zoom', zoom])
    table.appendRow(['lod', lod])
    table.appendRow(['object_count', object_count])
    table.appendRow(['text_count', text_count])
    table.appendRow(['nav_target_count', nav_count])
    table.appendRow(['pin_point_count', pin_count])
    table.appendRow(['last_appended_row_id', data.get('last_appended_row_id', '') if isinstance(data, dict) else ''])
    table.appendRow(['render_w', render_w])
    table.appendRow(['render_h', render_h])
    table.appendRow(['render_aspect', render_w / render_h if render_h else 0])
    world_w, world_h = get_world_size(render_w, render_h)
    table.appendRow(['world_w', world_w])
    table.appendRow(['world_h', world_h])
    table.appendRow(['copy_long_edge', COPY_LONG_EDGE])
    table.appendRow(['copy_match_map_aspect', int(COPY_MATCH_MAP_ASPECT)])
    table.appendRow(['map_top', MAP_TOP])
    table.appendRow(['max_objects', MAX_OBJECTS])
    table.appendRow(['max_text_lines', MAX_TEXT_LINES])


def renew_pin_points_only():
    data = load_latent_table()
    center_lng, center_lat, zoom = get_ctrl()
    apply_map_render_view(center_lng, center_lat, zoom)
    render_w, render_h = get_render_size()
    pin_points = build_pin_points(data, center_lng, center_lat, zoom, render_w, render_h)
    append_pin_points(get_table(OUT_PIN_POINTS), pin_points)


def run():
    try:
        mode = fetch_value('renew_table_mode', 'full')
        if mode == 'pins':
            renew_pin_points_only()
            return

        data = load_latent_table()
        nav_targets = build_nav_targets(data)
        center_lng, center_lat, zoom = get_ctrl()
        apply_map_render_view(center_lng, center_lat, zoom)

        render_w, render_h = get_render_size()
        pin_points = build_pin_points(data, center_lng, center_lat, zoom, render_w, render_h)

        clear_legacy_outputs()
        append_pin_points(get_table(OUT_PIN_POINTS), pin_points)
        append_nav_target_rows(get_table(OUT_NAV_TARGETS), nav_targets)

    except Exception as e:
        debug_log('renew_table error', e)

    return


run()
