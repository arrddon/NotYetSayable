"""Run in TouchDesigner's Textport. Creates a new /project1/nys_bridge only.

exec(open(project.folder + '/system/local/touchdesigner/install.py', encoding='utf-8').read())
"""
from pathlib import Path

target = op('/project1')
if target is None:
    raise RuntimeError('Open the V04 project with /project1 first')
if target.op('nys_bridge') is not None:
    raise RuntimeError('nys_bridge already exists. External adapter code can be reloaded by reopening the project; existing nodes were not overwritten.')

bridge = target.create(baseCOMP, 'nys_bridge')
bridge.nodeX = 0
bridge.nodeY = -300
settings = bridge.create(tableDAT, 'settings')
settings.appendRows([
    ['key', 'value'], ['camera_A', ''], ['camera_B', ''],
    ['python', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')],
])
copy = bridge.create(tableDAT, 'copy')
copy.appendRows([
    ['key', 'text'], ['consent', 'Please use your phone to begin.'],
    ['tutorial', 'Write your response on paper. Confirm on your phone when ready.'],
    ['Q1', ''], ['Q2', ''], ['Q3', ''], ['Q4', ''],
    ['processing', 'Please wait.'], ['error', 'Please try again on your phone.'],
    ['map', 'Choose a place on your phone.'], ['complete', 'Thank you.'],
])
hooks = bridge.create(textDAT, 'hooks')
hooks.text = '''# Custom integration hooks. Keep all TD operations on this main thread.
def on_consent(slot, participant):
    # Called once per participant generation; the slot's state is already restored.
    # Example: pulse an existing A/B animation trigger here.
    print('Participant ' + slot + ' consented')

def on_state(slot, participant):
    # Called on revision changes, including reset and browser navigation actions.
    pass
'''
for index, slot in enumerate(('A', 'B')):
    node = bridge.create(baseCOMP, slot)
    node.nodeX = index * 500
    node.nodeY = -200
    page = node.appendCustomPage('Participant')
    page.appendToggle('Consented', label='Consented')
    page.appendStr('Step', label='Step')
    page.appendStr('Status', label='Status')
    page.appendInt('Question', label='Question')
    page.appendInt('Generation', label='Generation')
    node.create(textDAT, 'state').text = '{}'
    text = node.create(textDAT, 'overlay_text')
    text.text = 'Waiting for connection.'
    camera = node.create(selectTOP, 'camera')
    mirror = node.create(transformTOP, 'mirror')
    mirror.inputConnectors[0].connect(camera)
    mirror.par.sx = -1
    overlay = node.create(textTOP, 'text')
    overlay.par.dat = text.path
    overlay.par.bgalpha = 0
    overlay.par.wordwrap = True
    # Match the camera resolution instead of stretching a small default text image.
    overlay.par.outputresolution = 'custom'
    overlay.par.resolutionw.expr = "op('camera').width"
    overlay.par.resolutionh.expr = "op('camera').height"
    composite = node.create(compositeTOP, 'composite')
    composite.par.operand = 'over'
    composite.inputConnectors[0].connect(overlay)
    composite.inputConnectors[1].connect(mirror)
    out = node.create(nullTOP, 'out')
    out.inputConnectors[0].connect(composite)
    for x, operator in enumerate((camera, mirror, overlay, composite, out)):
        operator.nodeX = x * 180

controller = bridge.create(textDAT, 'controller')
controller.text = '''import sys
from pathlib import Path
folder = str(Path(project.folder) / 'system/local/touchdesigner')
if folder not in sys.path:
    sys.path.insert(0, folder)
import td_adapter
runtime = td_adapter.Runtime(me.parent(), project.folder)

def tick():
    runtime.tick()

def start(session, demo=True, mock=True, processor=None):
    runtime.start_bridge(session, demo, mock, processor)

def stop():
    runtime.stop_bridge()
'''
execute = bridge.create(executeDAT, 'poll')
execute.text = '''def onFrameStart(frame):
    op('controller').module.tick()
    return

def onExit():
    op('controller').module.stop()
    return
'''
execute.par.framestart = True
execute.par.exit = True
print('Created ' + bridge.path + '. Set camera_A/camera_B in settings, then start the controller with a session ID. Save the .toe manually when ready.')
