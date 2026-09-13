import json
import os

MAP_TYPES = ['map_live', 'map_end', 'map_confirm']
NAV_TYPES = ['nav_live', 'nav_end']
CONTROLLER_FILE = os.path.join('Assets', 'controller_html.html')
NAV_CONTROLLER_FILE = os.path.join('Assets', 'nav_controller_html.html')
CTRL_TABLE = 'ctrl_values'
PIN_TABLE = 'pin_values'
AUTO_NAV_RANDOM_OP = 'auto_nav_random'
AUTO_NAV_RANDOM_LERP_STATE = 'auto_nav_random_lerp_state'
NAV_TARGET_REFRESH_PHASE = 13
LAST_PHASE_STATE_KEY = 'webserver_last_phase'


def project_path(path):
    try:
        return os.path.join(project.folder, path)
    except Exception:
        return path


def read_controller_html():
    path = project_path(CONTROLLER_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return op('controller_html').text


def read_nav_controller_html():
    stop_auto_nav_random()
    path = project_path(NAV_CONTROLLER_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return '<!doctype html><body>nav_controller_html.html not found</body>'


def get_table(name):
    table = op(name)
    if table is not None:
        return table
    try:
        return me.parent().create(tableDAT, name)
    except Exception:
        return None


def set_key(table, key, value):
    if table is None:
        return
    for row in range(table.numRows):
        try:
            if table[row, 0].val == key:
                table[row, 1] = value
                return
        except Exception:
            pass
    table.appendRow([key, value])


def setup_ctrl_table():
    t = get_table(CTRL_TABLE)
    if t is None:
        return None

    if t.numRows < 4:
        t.clear()
        t.appendRow(['type', ''])
        t.appendRow(['lng', 0])
        t.appendRow(['lat', 0])
        t.appendRow(['zoom', 2])

    if t.numRows < 5:
        t.appendRow(['phase', 0])

    if t.numRows < 6:
        t.appendRow(['source', ''])
    elif t[5, 0].val in ['', 'confirmed']:
        t[5, 0] = 'source'

    return t


def setup_pin_table():
    t = get_table(PIN_TABLE)
    if t is None:
        return None

    if t.numRows < 6:
        t.clear()
        t.appendRow(['type', ''])
        t.appendRow(['lng', ''])
        t.appendRow(['lat', ''])
        t.appendRow(['zoom', ''])
        t.appendRow(['phase', ''])
        t.appendRow(['confirmed', 0])

    return t


def write_camera_state(typ, lng, lat, zoom, phase=None, source=''):
    t = setup_ctrl_table()
    if t is None:
        return

    set_key(t, 'type', typ)
    set_key(t, 'lng', lng)
    set_key(t, 'lat', lat)
    set_key(t, 'zoom', zoom)
    set_key(t, 'phase', current_phase() if phase is None else phase)
    set_key(t, 'source', source or typ)


def write_confirm_state(typ, phase=None):
    t = setup_ctrl_table()
    if t is None:
        return

    set_key(t, 'type', typ)
    set_key(t, 'phase', current_phase() if phase is None else phase)
    set_key(t, 'source', 'participant_confirm')


def write_pin_state(typ, lng, lat, zoom, phase=None):
    t = setup_pin_table()
    if t is None:
        return

    set_key(t, 'type', typ)
    set_key(t, 'lng', lng)
    set_key(t, 'lat', lat)
    set_key(t, 'zoom', zoom)
    set_key(t, 'phase', current_phase() if phase is None else phase)
    set_key(t, 'confirmed', 1)


def current_phase():
    p = op('MainPhase')
    if p is None:
        return 0
    try:
        return int(round(float(p['MainPhase'].eval())))
    except Exception:
        try:
            return int(round(float(p[0].eval())))
        except Exception:
            return 0


def handle_phase_state(phase):
    owner = me.parent()
    try:
        last_phase = owner.fetch(LAST_PHASE_STATE_KEY, None)
    except Exception:
        last_phase = None

    if phase == NAV_TARGET_REFRESH_PHASE and last_phase != NAV_TARGET_REFRESH_PHASE:
        run_renew_table('full')

    try:
        owner.store(LAST_PHASE_STATE_KEY, phase)
    except Exception:
        pass


def request_path(request):
    for key in ['path', 'uri', 'url']:
        value = request.get(key)
        if value:
            return str(value).split('?')[0]
    return '/'


def pulse_confirm():
    target = op('gotAnswer')
    if target is not None:
        target.par.trigger.pulse()


def apply_map_render(lng, lat, zoom):
    map_top = op('map_render')
    if map_top is None:
        return

    js = '''
    if (window.td_setView) {
        window.td_setView(%f, %f, %f);
    }
    ''' % (lng, lat, zoom)

    try:
        map_top.executeJavaScript(js)
    except Exception:
        pass


def run_renew_table(mode='full'):
    dat = op('renew_table')
    if dat is None:
        return
    try:
        dat.parent().store('renew_table_mode', mode)
        dat.run()
        dat.parent().store('renew_table_mode', 'full')
    except Exception:
        pass


def stop_auto_nav_random():
    try:
        me.parent().store(AUTO_NAV_RANDOM_LERP_STATE, None)
    except Exception:
        pass

    dat = op(AUTO_NAV_RANDOM_OP)
    if dat is None:
        return

    try:
        dat.text = "def run():\n    return\n\nrun()\n"
    except Exception:
        pass


def onHTTPRequest(webServerDAT, request, response):
    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'

    if request_path(request) == '/state':
        phase = current_phase()
        handle_phase_state(phase)
        response['data'] = json.dumps({'phase': phase})
        response['contentType'] = 'application/json'
        return response

    if request_path(request) == '/nav':
        response['data'] = read_nav_controller_html()
        response['contentType'] = 'text/html'
        return response

    response['data'] = read_controller_html()
    response['contentType'] = 'text/html'
    return response


def onWebSocketReceiveText(webServerDAT, client, data):
    msg = json.loads(data)

    typ = msg.get('type')

    if typ == 'confirm':
        phase = int(float(msg.get('phase', current_phase()) or 0))
        write_confirm_state(typ, phase)
        pulse_confirm()
        return

    if typ in NAV_TYPES:
        lng = float(msg.get('lng', 0))
        lat = float(msg.get('lat', 0))
        zoom = float(msg.get('zoom', 2))
        apply_map_render(lng, lat, zoom)
        write_camera_state(typ, lng, lat, zoom, current_phase(), 'nav_manual')
        if typ == 'nav_end':
            run_renew_table('pins')
        return

    if typ not in MAP_TYPES:
        return

    lng = float(msg.get('lng', 0))
    lat = float(msg.get('lat', 0))
    zoom = float(msg.get('zoom', 2))

    apply_map_render(lng, lat, zoom)
    phase = int(float(msg.get('phase', current_phase()) or 0))
    write_camera_state(typ, lng, lat, zoom, phase, 'participant_map')

    if typ in ['map_live', 'map_end']:
        run_renew_table('pins')
        return

    if typ == 'map_confirm':
        write_pin_state(typ, lng, lat, zoom, phase)
        run_renew_table('pins')
        pulse_confirm()

    return
