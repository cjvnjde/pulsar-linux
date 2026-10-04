"""HATOR Pulsar 3 (379a:3910, IC571) configuration packet builders.
Derived from the user's 2025-02-27 application; see PROTOCOL.md for evidence.
No hardware access occurs in this module.
"""
from dataclasses import dataclass
import struct

POLLING = {125:8,250:4,500:2,1000:1}
MODES = {'off':0,'static':1,'breath':2,'neon':3,'wave':4,'press':5,'horse-race':7}
SPEEDS = (1,3,4,5,7)
BUTTONS = ('left','right','middle','forward','back','dpi')
ACTIONS = {'left':[0,0,240,0], 'right':[0,0,241,0], 'middle':[0,0,242,0],
           'forward':[0,0,244,0], 'back':[0,0,243,0], 'double-click':[0,240,30,2],
           'dpi-up':[5,0,1,0], 'dpi-down':[5,0,2,0], 'dpi-cycle':[5,0,3,0],
           'dpi-lock':[5,0,4,0], 'disabled':[0,0,0,0]}
for name,code in {'media-player':0x183,'next-track':0xb5,'previous-track':0xb6,'stop':0xb7,
                  'mute':0xe2,'play-pause':0xcd,'volume-up':0xe9,'volume-down':0xea}.items():
    ACTIONS[name]=[3,0,code&255,code>>8]
DEFAULT_KEYS=[ACTIONS[k][:] for k in BUTTONS[:-1]]+[ACTIONS['dpi-cycle'][:],ACTIONS['dpi-down'][:],ACTIONS['dpi-lock'][:]]+[[0,0,0,0] for _ in range(6)]+[[255,0,1,0],[255,0,2,0]]

@dataclass(frozen=True)
class Packet:
    name: str
    header: bytes  # HIDAPI format: report ID zero followed by 8 wire bytes
    payload: bytes = b''
    def as_dict(self):
        return {'name':self.name,'feature_report':self.header.hex(' '),
                'usb_feature_payload':self.header[1:].hex(' '),
                'output_reports':[self.payload[i:i+64].hex(' ') for i in range(0,len(self.payload),64)]}

def integer(value,lo,hi,name):
    if type(value) is not int or not lo<=value<=hi: raise ValueError(f'{name} must be an integer in {lo}..{hi}')
    return value

def only_keys(obj,allowed,name):
    if not isinstance(obj,dict): raise ValueError(f'{name} must be an object')
    unknown=set(obj)-set(allowed)
    if unknown: raise ValueError(f'Unknown {name} field(s): {", ".join(sorted(unknown))}')

def sync_packet(): return Packet('status sync',bytes.fromhex('00 80 00 00 00 00 00 00 7f'))

def parameter0(payload,profile=0):
    if len(payload)!=64: raise ValueError('Parameter 0 requires 64 bytes')
    return Packet('polling/lighting parameters',bytes([0,2,integer(profile,0,255,'profile'),0,0,0,0,1,0]),bytes(payload))

def parameter1(payload,mask):
    if len(payload)!=192: raise ValueError('Parameter 1 requires 192 bytes')
    return Packet('DPI/colors/button parameters',bytes([0,3,0,0,0,0,integer(mask,1,7,'mask'),3,0]),bytes(payload))

def macro_packet(slot,payload):
    if len(payload)!=128: raise ValueError('Macro requires 128 bytes')
    return Packet(f'macro slot {slot}',bytes([0,4,0,integer(slot,0,11,'macro slot'),0,0,0,0,0]),bytes(payload))

def stage_packet(stage):
    # Original mouseSetCurrentDPI argument; hardware support must be verified.
    integer(stage,1,6,'DPI stage')
    return Packet('active DPI stage',bytes([0,11,stage,0,0,0,0,0,(~(11+stage))&255]))

def translate_key(value):
    """Translate the four UI bytes exactly as FUN_00412aa0 does."""
    if not isinstance(value,(list,tuple)) or len(value)!=4: raise ValueError('ui_key must contain four bytes')
    a,b,c,d=[integer(v,0,255,'button byte') for v in value]
    skip=False
    if a==0:
        if (c,d)==(30,2): a,b,c,d=12,2,1,240
        else: a,c,d=2,0,c; skip=True
    elif a==1: a,b,d=12,d,b
    elif a in (2,3): a,b,c,d=(1 if a==2 else 3),0,d,c
    elif a==4: a,b,c,d=5,(b+1)&255,0,c; skip=True
    elif a==5:
        a,c,d=11,0,c
        if d==4: a,b,c=240,3,1
        skip=True
    elif a in (6,7): a=1
    elif a==255: a=4
    if not skip and (((c&253)==33 and d==2) or (c==148 and d==1)):
        a,b,c,d=3,0,d,c
    return bytes((d,c,b,a))

def key_action(action):
    if isinstance(action,str):
        if action not in ACTIONS: raise ValueError(f'Unknown button action {action!r}')
        return ACTIONS[action][:]
    only_keys(action,('ui_key','key','modifiers','macro','mode'),'button action')
    selectors=set(action)&{'ui_key','key','macro'}
    if len(selectors)!=1: raise ValueError('Button action needs exactly one of ui_key, key, macro')
    if 'ui_key' in action:
        if set(action)!={'ui_key'}: raise ValueError('ui_key cannot be combined with other fields')
        translate_key(action['ui_key']);return action['ui_key']
    if 'key' in action:
        if set(action)-{'key','modifiers'}: raise ValueError('Keyboard action accepts key and modifiers only')
        # Type 7 is the app shortcut representation; type 2 has different semantics.
        return [7,integer(action.get('modifiers',0),0,255,'modifier mask'),0,integer(action['key'],4,231,'USB keyboard usage')]
    if set(action)-{'macro','mode'}: raise ValueError('Macro binding accepts macro and mode only')
    modes={'once':0,'toggle':1,'hold':2}
    mode=action.get('mode','once')
    if mode not in modes: raise ValueError('Macro mode must be once, toggle, or hold')
    return [4,modes[mode],integer(action['macro'],0,11,'macro slot'),0]

def encode_macro(spec):
    only_keys(spec,('slot','repeat','events'),'macro')
    integer(spec.get('slot'),0,11,'macro slot')
    repeat=integer(spec.get('repeat',1),1,65535,'macro repeat count')
    events=spec.get('events')
    if not isinstance(events,list) or len(events)<2: raise ValueError('A macro needs at least two events')
    result=bytearray(struct.pack('<H',repeat)); pressed=set()
    for i,event in enumerate(events):
        only_keys(event,('key','action','delay_ms'),'macro event')
        key=integer(event.get('key'),4,244,'macro USB key/mouse code')
        action=event.get('action')
        if action not in ('down','up'): raise ValueError('Macro event action must be down or up')
        if action=='down':
            if key in pressed: raise ValueError('Duplicate macro key-down')
            pressed.add(key)
        else:
            if key not in pressed: raise ValueError('Macro key-up without key-down')
            pressed.remove(key)
        delay=integer(event.get('delay_ms',10),10,655350,'macro delay_ms')
        if delay%10: raise ValueError('Macro delays must be multiples of 10 ms')
        ticks=delay//10
        if i==len(events)-1 and ticks!=1: raise ValueError('The last event must use delay_ms 10, as in the original app')
        released=128 if action=='up' else 0
        if ticks<127: result.extend((ticks|released,key))
        else:
            # Original QML uses the 20 ms extended-delay format in this range.
            result.extend((released,key,0,1));result.extend(struct.pack('>H',ticks//2))
    if pressed: raise ValueError('Macro must release every pressed key/button')
    result.extend((0,0))
    if len(result)>128: raise ValueError(f'Macro is {len(result)} bytes; hardware limit is 128')
    return bytes(result).ljust(128,b'\0')

def plan(config,sections=None):
    """Require a complete explicit profile; sections select writes, not implicit defaults."""
    only_keys(config,('schema','name','polling_hz','dpi','lighting','buttons','macros'),'profile')
    if config.get('schema')!=1: raise ValueError('Profile schema must be 1')
    sections=set(sections or ('parameters','dpi','colors','buttons','macros'))
    if sections-{'parameters','dpi','colors','buttons','macros'}: raise ValueError('Unknown section')
    hz=config.get('polling_hz')
    if type(hz) is not int or hz not in POLLING: raise ValueError('polling_hz must be 125, 250, 500, or 1000')
    dpi=config.get('dpi')
    if not isinstance(dpi,list) or not 1<=len(dpi)<=6: raise ValueError('dpi must contain 1..6 stages')
    for n in dpi:
        integer(n,200,12000,'DPI')
        if n%100: raise ValueError('DPI values must be multiples of 100')
    lighting=config.get('lighting');only_keys(lighting,('mode','brightness','speed','selected_color','colors'),'lighting')
    if lighting.get('mode') not in MODES: raise ValueError('Unknown lighting mode')
    brightness=integer(lighting.get('brightness'),0,4,'brightness')
    speed=integer(lighting.get('speed'),0,4,'speed')
    color_index=integer(lighting.get('selected_color',0),0,7,'selected_color')
    colors=lighting.get('colors')
    if not isinstance(colors,list) or len(colors)!=8: raise ValueError('Exactly eight RGB colors are required')
    rgb=bytearray()
    for c in colors:
        if not isinstance(c,str) or len(c)!=7 or not c.startswith('#'): raise ValueError('Colors must use #RRGGBB')
        try: rgb.extend(bytes.fromhex(c[1:]))
        except ValueError: raise ValueError('Colors must use #RRGGBB') from None
    buttons=config.get('buttons');only_keys(buttons,BUTTONS,'buttons')
    if set(buttons)!=set(BUTTONS): raise ValueError('Specify all six button mappings explicitly')
    keys=[key_action(buttons[b]) for b in BUTTONS]
    if ACTIONS['left'] not in keys: raise ValueError('Keep at least one button assigned to left-click')
    keys+=DEFAULT_KEYS[6:]
    macros=config.get('macros',[])
    if not isinstance(macros,list): raise ValueError('macros must be an array')
    macro_packets=[];slots=set()
    for spec in macros:
        encoded=encode_macro(spec);slot=spec['slot']
        if slot in slots: raise ValueError('Duplicate macro slot')
        slots.add(slot);macro_packets.append(macro_packet(slot,encoded))
    for value in keys:
        if value[0]==4 and value[2] not in slots: raise ValueError(f'Macro slot {value[2]} has no definition')
    packets=macro_packets if 'macros' in sections else []
    if 'buttons' in sections and slots and 'macros' not in sections: raise ValueError('Include macros when applying macro bindings')
    if 'parameters' in sections:
        p0=bytes([POLLING[hz],len(dpi),MODES[lighting['mode']],brightness*63,SPEEDS[speed],color_index]).ljust(64,b'\0')
        packets.append(parameter0(p0))
    mask=sum(bit for name,bit in [('dpi',1),('colors',2),('buttons',4)] if name in sections)
    if mask:
        p1=bytearray(192);p1[4]=len(dpi)
        padded=dpi+[2000]*(8-len(dpi))
        for i,n in enumerate(padded):
            struct.pack_into('<H',p1,9+2*i,n);struct.pack_into('<H',p1,25+2*i,n)
        p1[88:112]=rgb
        for i,k in enumerate(keys):p1[128+4*i:132+4*i]=translate_key(k)
        packets.append(parameter1(p1,mask))
    return packets

def decode_status(report):
    if len(report)!=7 or report[:2]!=b'\x05\x00': raise ValueError('Not a Pulsar status report')
    _,_,period,stage,mode,speed,event=report
    return {'polling_hz':{v:k for k,v in POLLING.items()}.get(period),
            'dpi_stage':stage+1,'lighting_mode':{v:k for k,v in MODES.items()}.get(mode),
            'lighting_speed':SPEEDS.index(speed) if speed in SPEEDS else None,
            'event':event,'raw':report.hex(' '),
            'note':'Live status does not contain DPI values, brightness, colors, button mappings, or macros.'}
