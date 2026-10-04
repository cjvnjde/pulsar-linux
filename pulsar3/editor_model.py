"""UI-facing profile operations. No device or desktop access."""
from copy import deepcopy
from .protocol import BUTTONS, encode_macro, plan

KEY_NAMES = {i + 4: chr(65 + i) for i in range(26)}
KEY_NAMES.update({30 + i: str((i + 1) % 10) for i in range(10)})
KEY_NAMES.update({40:'Enter',41:'Escape',42:'Backspace',43:'Tab',44:'Space',45:'Minus',46:'Equals',
    47:'Left bracket',48:'Right bracket',49:'Backslash',50:'Non-US hash',51:'Semicolon',52:'Quote',
    53:'Grave',54:'Comma',55:'Period',56:'Slash',57:'Caps Lock',70:'Print Screen',71:'Scroll Lock',
    72:'Pause',73:'Insert',74:'Home',75:'Page Up',76:'Delete',77:'End',78:'Page Down',
    79:'Right arrow',80:'Left arrow',81:'Down arrow',82:'Up arrow',83:'Num Lock',84:'Keypad /',
    85:'Keypad *',86:'Keypad -',87:'Keypad +',88:'Keypad Enter',98:'Keypad 0',99:'Keypad .',
    100:'Non-US backslash',101:'Menu',103:'Keypad =',224:'Left Ctrl',225:'Left Shift',
    226:'Left Alt',227:'Left Super',228:'Right Ctrl',229:'Right Shift',230:'Right Alt',231:'Right Super',
    240:'Mouse left',241:'Mouse right',242:'Mouse middle',243:'Mouse back',244:'Mouse forward'})
KEY_NAMES.update({58+i:f'F{i+1}' for i in range(12)})
KEY_NAMES.update({104+i:f'F{i+13}' for i in range(12)})
KEY_NAMES.update({89+i:f'Keypad {i+1}' for i in range(9)})
MODIFIERS = [('Ctrl',1),('Shift',2),('Alt',4),('Super',8),('Right Ctrl',16),('Right Shift',32),('Right Alt',64),('Right Super',128)]
ACTION_LABELS = {'left':'Left click','right':'Right click','middle':'Wheel click','forward':'Forward',
    'back':'Back','double-click':'Double click','dpi-up':'DPI up','dpi-down':'DPI down',
    'dpi-cycle':'Cycle DPI stages','dpi-lock':'Sniper action (experimental)','disabled':'Disabled',
    'media-player':'Open media player','next-track':'Next track','previous-track':'Previous track',
    'stop':'Stop playback','mute':'Mute','play-pause':'Play / pause','volume-up':'Volume up','volume-down':'Volume down'}
BUTTON_LABELS = dict(zip(BUTTONS,('Left button','Right button','Wheel click','Forward button','Back button','DPI button')))
PLAYBACK = {'once':'Play once','toggle':'Repeat until a mouse button is pressed','hold':'Repeat while held'}


def key_label(usage):
    return KEY_NAMES.get(usage, f'HID usage {usage}')


def action_label(action):
    if isinstance(action,str):
        return ACTION_LABELS.get(action,action)
    if 'key' in action:
        names = [name for name,bit in MODIFIERS if action.get('modifiers',0)&bit]
        return ' + '.join(names+[key_label(action['key'])])
    if 'macro' in action:
        return f"Macro {action['macro']+1} · {PLAYBACK[action.get('mode','once')]}"
    return 'Advanced action'


def macro_bytes(spec):
    """Meaningful encoded length (the encoder pads to 128 bytes)."""
    return 4 + sum(2 if e.get('delay_ms',10) < 1270 else 6 for e in spec['events'])


def effective_delay(milliseconds):
    return milliseconds if milliseconds < 1270 else milliseconds // 20 * 20


def append_tap(spec, key, delay=50, modifiers=0):
    """Append a balanced shortcut or mouse tap, preserving final-event rules."""
    keys = [224+i for i in range(8) if modifiers & (1 << i)]
    if key not in keys:
        keys.append(key)
    events = spec['events']
    for usage in keys:
        events.append({'key':usage,'action':'down','delay_ms':10})
    events[-1]['delay_ms'] = delay
    for usage in reversed(keys):
        events.append({'key':usage,'action':'up','delay_ms':10})


def new_macro(slot):
    spec = {'slot':slot,'repeat':1,'events':[]}
    append_tap(spec,4)
    return spec


def remove_macro(config, slot):
    """Remove a slot and restore any referencing buttons to their standard action."""
    config['macros'] = [m for m in config.get('macros',[]) if m['slot'] != slot]
    restored=[]
    for button,action in config['buttons'].items():
        # Advanced original-app bindings can reference a macro too.
        raw = action.get('ui_key') if isinstance(action,dict) else None
        if isinstance(action,dict) and (action.get('macro') == slot or (raw and raw[0] == 4 and raw[2] == slot)):
            config['buttons'][button] = 'dpi-cycle' if button == 'dpi' else button
            restored.append(button)
    return restored


class ProfileDocument:
    """Keep file state and the last successful hardware submission independent."""
    def __init__(self, config):
        self.config = deepcopy(config)
        self.saved = deepcopy(config)
        self.applied = None

    @property
    def dirty(self):
        return self.config != self.saved

    @property
    def pending(self):
        return self.applied is None or self.config != self.applied

    def validated(self):
        snapshot = deepcopy(self.config)
        plan(snapshot)
        return snapshot

    def load(self, config):
        plan(config)
        self.config = deepcopy(config)
        self.saved = deepcopy(config)

    def mark_saved(self, snapshot):
        self.saved = deepcopy(snapshot)

    def mark_applied(self, snapshot):
        self.applied = deepcopy(snapshot)
