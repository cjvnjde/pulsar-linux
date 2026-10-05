"""Native GTK4 profile studio for the HATOR Pulsar 3."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .editor_model import (ACTION_LABELS, BUTTON_LABELS, DPI_INDICATOR_COLORS, DPI_INDICATOR_NAMES, KEY_NAMES, MODIFIERS, PLAYBACK,
    ProfileDocument, action_label, append_tap, effective_delay, key_label, macro_bytes,
    move_dpi_stage, new_macro, remove_macro)
from .desktop import device_access_command
from .gtk_compat import color_picker, confirm
from .protocol import ACTIONS, BUTTONS, MODES, encode_macro, plan
from .dpi_lighting import DpiLightingFollower
from .transport import discover
from .paths import DEFAULT_PROFILE, ROOT, initial_profile, profiles_dir, working_profile

ASSETS = Path(__file__).with_name('assets')
WORKING = working_profile()
PAGE_INFO = {
    'buttons': ('Button assignments', 'Make every click yours. Select a button to change its action.'),
    'dpi': ('Sensitivity', 'Dial in your movement with up to six DPI stages.'),
    'lighting': ('Lighting', 'Set the mood with RGB colors and onboard effects.'),
    'macros': ('Macro studio', 'Build key sequences and assign them to a mouse button.'),
    'profiles': ('Your profiles', 'Save configurations locally and apply them when you need them.'),
    'device': ('Device & access', 'Connection, Linux permissions, and the last status read from your mouse.'),
    'advanced': ('Advanced profile', 'Inspect or import the complete configuration as JSON.'),
}
EFFECT_LABELS = {'off':'Off', 'static':'Static', 'breath':'Breathing', 'neon':'Neon',
                  'wave':'Wave', 'press':'On press', 'horse-race':'Chase'}


def box(vertical=False, spacing=10, css=None):
    widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)
    if css:
        widget.add_css_class(css)
    return widget


def label(text, css=None, wrap=False):
    widget = Gtk.Label(label=text, xalign=0, wrap=wrap)
    if css:
        for item in css.split():
            widget.add_css_class(item)
    return widget


def button(text, callback, css=None, tooltip=None):
    widget = Gtk.Button(label=text)
    if callback:
        widget.connect('clicked', callback)
    if css:
        for item in css.split():
            widget.add_css_class(item)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    return widget


def clear(widget):
    while widget.get_first_child():
        widget.remove(widget.get_first_child())


def spin(value, lo, hi, step=1, width=4):
    widget = Gtk.SpinButton.new_with_range(lo, hi, step)
    widget.set_numeric(True)
    widget.set_value(value)
    widget.set_width_chars(width)
    widget.set_snap_to_ticks(True)
    return widget


def dropdown(items, selected=0):
    widget = Gtk.DropDown.new_from_strings(items)
    widget.set_selected(selected)
    widget.set_enable_search(True)
    return widget


def field(title, widget):
    row = box(True, 7)
    row.append(label(title, 'muted small'))
    row.append(widget)
    return row


def card(title=None, description=None):
    widget = box(True, 14, 'card')
    if title:
        widget.append(label(title, 'card-title'))
    if description:
        widget.append(label(description, 'subtitle', True))
    return widget


def key_picker(value=4, mouse=False):
    # Named keys first; all accepted usages remain accessible by their numeric name.
    limit = 244 if mouse else 231
    values = sorted(k for k in KEY_NAMES if 4 <= k <= limit)
    values += [k for k in range(4, limit + 1) if k not in KEY_NAMES]
    widget = dropdown([key_label(k) for k in values], values.index(value))
    return widget, values


class Editor(Gtk.Application):
    def __init__(self, offline=False, profile_path=None):
        super().__init__(application_id='local.hator.Pulsar3.Studio',
                         flags=Gio.ApplicationFlags.NON_UNIQUE if offline else Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect('activate', self.activate)
        self.profile_path = Path(profile_path) if profile_path else initial_profile()
        self.startup_error = None
        try:
            config = json.loads(self.profile_path.read_text())
            plan(config)
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.startup_error = f'Could not load the saved profile: {error}. Open a valid file to recover it.'
            config = json.loads((DEFAULT_PROFILE).read_text())
            self.profile_path = None
        if not profile_path:
            self.profile_path = WORKING
        self.doc = ProfileDocument(config)
        self.offline = offline
        self.busy = False
        self.ready = False
        self.raw_dirty = False
        self.live = None
        self.live_time = None
        self.device_info = None
        self.selected_button = 'back'
        self.selected_macro = config.get('macros', [{}])[0].get('slot') if config.get('macros') else None
        self.last_config_page = 'dpi'
        self.page = 'dpi'
        self.allow_close = False
        self.device_lock = threading.Lock()
        self.follower = DpiLightingFollower(self.device_lock,
            lambda revision, update: GLib.idle_add(self.follow_update, revision, update))
        self.follow_message = None
        self.connect('shutdown', lambda *_: self.follower.close())

    @property
    def config(self):
        return self.doc.config

    def activate(self, *_):
        if hasattr(self, 'window'):
            self.window.present()
            return
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        self.css = Gtk.CssProvider()
        self.css.load_from_path(str(ASSETS/'style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title='HATOR · Pulsar 3 Studio')
        self.window.add_css_class('pulsar')
        self.window.set_default_size(1180, 820)
        self.window.set_size_request(940, 650)
        self.window.connect('close-request', self.close_requested)
        layout = box(spacing=0)
        self.window.set_child(layout)
        self.sidebar = box(True, 8, 'sidebar')
        self.sidebar.set_size_request(188, -1)
        layout.append(self.sidebar)
        brand = box(True, 5)
        brand.set_margin_start(16)
        brand.set_margin_bottom(28)
        brand.append(label('HATOR', 'brand'))
        brand.append(label('PULSAR 3  /  LINUX', 'eyebrow'))
        self.sidebar.append(brand)
        self.nav = {}
        for name, icon, title in [('buttons','input-mouse-symbolic','Buttons'),('dpi','find-location-symbolic','DPI & polling'),
                                  ('lighting','display-brightness-symbolic','Lighting'),('macros','media-playlist-repeat-symbolic','Macros')]:
            self.nav[name] = self.nav_button(self.sidebar, title, icon, lambda _, n=name: self.navigate(n))
        spacer = box(); spacer.set_vexpand(True); self.sidebar.append(spacer)
        self.nav['advanced'] = self.nav_button(self.sidebar, 'Advanced', 'preferences-system-symbolic', lambda _: self.navigate('advanced'))
        bottom = box(True, 8)
        bottom.set_margin_top(16); bottom.set_margin_start(10); bottom.set_margin_end(10)
        bottom.append(label('EDITING PROFILE', 'eyebrow'))
        self.profile_label = label('', wrap=True)
        self.profile_label.set_max_width_chars(22)
        bottom.append(self.profile_label)
        bottom.append(label('Saved on this computer', 'muted small'))
        self.sidebar.append(bottom)
        main = box(True, 0); main.set_hexpand(True); layout.append(main)
        top = box(spacing=10, css='topbar'); main.append(top)
        self.top_nav = {}
        for key, title in [('configuration','Configuration'),('profiles','Profiles'),('device','Device')]:
            self.top_nav[key] = button(title, lambda _, n=key: self.navigate(self.last_config_page if n=='configuration' else n), 'top-tab')
            top.append(self.top_nav[key])
        gap = box(); gap.set_hexpand(True); top.append(gap)
        self.connection = button('Checking mouse…', lambda _: self.navigate('device'), 'badge')
        top.append(self.connection)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=100)
        self.stack.set_vexpand(True); self.stack.set_hexpand(True); main.append(self.stack)
        self.pages = {}
        for name in PAGE_INFO:
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            content = box(True, 20, 'page')
            clamp = Adw.Clamp(maximum_size=1180, tightening_threshold=900)
            clamp.set_child(content)
            scroll.set_child(clamp)
            self.stack.add_named(scroll, name)
            self.pages[name] = content
        footer = box(True, 9, 'footer'); main.append(footer)
        row = box(spacing=8); footer.append(row)
        state = box(True, 4); state.set_hexpand(True); row.append(state)
        self.save_state = label('', 'small'); state.append(self.save_state)
        self.apply_state = label('', 'muted small'); state.append(self.apply_state)
        self.spinner = Gtk.Spinner(); row.append(self.spinner)
        self.validate_button = button('Validate', self.validate)
        self.save_button = button('Save profile', lambda _: self.save_profile())
        self.apply_button = button('Apply to mouse', self.apply, 'primary')
        for widget in (self.validate_button, self.save_button, self.apply_button): row.append(widget)
        self.message = label('Edit a profile, then apply it to the mouse.', 'message', True)
        self.message.set_max_width_chars(100); footer.append(self.message)
        self.rebuild()
        self.navigate('dpi')
        self.window.present()
        if self.startup_error:
            self.notify(self.startup_error, True)
        if self.offline:
            self.connection.set_label('Offline preview')
        else:
            self.read_status()

    def nav_button(self, parent, title, icon, callback):
        widget = button('', callback, 'nav-button')
        row = box(spacing=14)
        row.append(Gtk.Image.new_from_icon_name(icon)); row.append(label(title))
        widget.set_child(row); parent.append(widget)
        return widget

    def navigate(self, name):
        if self.raw_dirty and name not in ('advanced', 'device'):
            self.notify('Load or reset the pending JSON edits before using other editors.', True)
            return
        self.page = name
        if name not in ('profiles','device'):
            self.last_config_page = name
        self.stack.set_visible_child_name(name)
        for key, widget in self.nav.items():
            (widget.add_css_class if name==key else widget.remove_css_class)('active')
        top_key = name if name in ('profiles','device') else 'configuration'
        for key, widget in self.top_nav.items():
            (widget.add_css_class if key==top_key else widget.remove_css_class)('active')
        if name == 'profiles': self.build_profiles()

    def page_header(self, name):
        content = self.pages[name]; clear(content)
        header = box(True, 7)
        title, subtitle = PAGE_INFO[name]
        header.append(label(title, 'page-title'))
        header.append(label(subtitle, 'subtitle', True))
        content.append(header)
        return content

    def rebuild(self):
        self.build_dpi(); self.build_lighting(); self.build_buttons(); self.build_macros()
        self.build_profiles(); self.build_device(); self.build_advanced()
        self.changed()

    def changed(self, *_):
        self.profile_label.set_text(self.config.get('name') or 'Untitled profile')
        self.save_state.set_text('● Unsaved changes' if self.doc.dirty or self.raw_dirty else 'Profile saved locally')
        self.apply_state.set_text('Not applied in this session' if self.doc.applied is None else ('Changes waiting to be applied' if self.doc.pending else 'Configuration sent to mouse'))
        enabled = not self.busy and not self.raw_dirty
        self.save_button.set_sensitive(enabled)
        self.apply_button.set_sensitive(enabled and self.ready and not self.offline)
        self.validate_button.set_sensitive(not self.busy)
        if hasattr(self,'json_buffer') and not self.raw_dirty:
            self.sync_json()
        self.update_follow_labels()

    def notify(self, text, error=False):
        self.message.set_text(text)
        (self.message.add_css_class if error else self.message.remove_css_class)('error')

    def set_value(self, obj, key, value):
        obj[key] = value
        self.changed()

    # Sensitivity ---------------------------------------------------------
    def build_dpi(self):
        content = self.page_header('dpi')
        panel = card(); content.append(panel)
        heading = box(); title = label('DPI stages', 'card-title'); title.set_hexpand(True); heading.append(title)
        heading.append(label(f"{len(self.config['dpi'])} / 6 stages", 'muted small'))
        add = button('+ Add stage', lambda _: self.add_stage(), 'primary'); add.set_sensitive(len(self.config['dpi'])<6); heading.append(add)
        panel.append(heading)
        link = box(spacing=12)
        text = label('Link bottom RGB lighting to DPI stage'); text.set_hexpand(True); link.append(text)
        self.dpi_link_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        linked = self.config.get('dpi_lighting', {}).get('enabled', False)
        self.dpi_link_switch.set_active(linked)
        self.dpi_link_switch.set_tooltip_text('Change the bottom lighting with each stage while this app is running')
        self.dpi_link_switch.connect('notify::active', self.toggle_dpi_lighting)
        link.append(self.dpi_link_switch); panel.append(link)
        panel.append(label('The scroll wheel uses its built-in stage colors, shown beside each stage. Custom colors affect only the bottom RGB lighting. Enable linking, then Apply and keep the app open.', 'muted small', True))
        self.dpi_widgets = []
        self.dpi_color_pickers = []
        self.dpi_wheel_labels = []
        self.dpi_move_buttons = []
        stage_colors = self.config.get('dpi_lighting', {}).get('colors', DPI_INDICATOR_COLORS)
        for index, value in enumerate(self.config['dpi']):
            row = box(spacing=14, css='stage-row')
            number = label(f'{index+1:02}', 'accent-text'); number.set_width_chars(2); row.append(number)
            name = box(True, 3)
            name.append(label(f'Stage {index+1}'))
            wheel = label('', 'small')
            wheel.set_markup(f'<span foreground="{DPI_INDICATOR_COLORS[index]}">●</span> {DPI_INDICATOR_NAMES[index]} wheel')
            wheel.set_tooltip_text('Built-in wheel indicator color from the mouse manual; not editable or read back')
            self.dpi_wheel_labels.append(wheel); name.append(wheel); row.append(name)
            picker = color_picker(f'Stage {index+1} bottom RGB color', stage_colors[index])
            picker.set_sensitive(linked)
            picker.set_tooltip_text(f'Stage {index+1} bottom RGB color · {stage_colors[index]}')
            picker.connect('notify::rgba', self.dpi_color_picked, index)
            bottom = box(True, 3)
            bottom.append(label('Bottom RGB', 'muted small')); bottom.append(picker)
            row.append(bottom); self.dpi_color_pickers.append(picker)
            adjustment = Gtk.Adjustment(value=value, lower=200, upper=12000, step_increment=100, page_increment=500)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment, digits=0, draw_value=False)
            scale.set_hexpand(True); row.append(scale)
            entry = Gtk.SpinButton(adjustment=adjustment, climb_rate=100, digits=0)
            entry.set_numeric(True); entry.set_snap_to_ticks(True); entry.set_width_chars(5); row.append(entry)
            row.append(label('DPI', 'muted small'))
            order = box(spacing=3, css='stage-order')
            up = button('↑', lambda _, i=index: self.move_stage(i, i-1), 'flat', 'Move this stage earlier')
            down = button('↓', lambda _, i=index: self.move_stage(i, i+1), 'flat', 'Move this stage later')
            up.set_sensitive(index > 0); down.set_sensitive(index < len(self.config['dpi'])-1)
            self.dpi_move_buttons.append((up, down)); order.append(up); order.append(down); row.append(order)
            remove = button('−', lambda _, i=index: self.remove_stage(i), 'flat', 'Remove this stage')
            remove.set_sensitive(len(self.config['dpi'])>1); row.append(remove)
            adjustment.connect('value-changed', self.change_dpi, index)
            self.dpi_widgets.append(adjustment); panel.append(row)
        panel.append(label('Use ↑ and ↓ to change the cycle order. DPI values and custom bottom colors move together; wheel colors belong to the numbered slots. Apply to send changes.', 'muted small', True))
        binding = box(spacing=12)
        self.dpi_button_label = label('DPI button: ' + action_label(self.config['buttons']['dpi']), 'muted small', True)
        self.dpi_button_label.set_hexpand(True); binding.append(self.dpi_button_label)
        binding.append(button('Edit DPI button', lambda _: (self.navigate('buttons'), self.choose_button('dpi'))))
        panel.append(binding)
        self.dpi_follow_label = label('', 'muted small', True); panel.append(self.dpi_follow_label)
        self.update_follow_labels()
        rates = card('Polling rate', 'How often the mouse reports input to your computer.'); content.append(rates)
        row = box(spacing=10); rates.append(row)
        self.rate_buttons = {}
        for hz, latency in ((125,'8 ms'),(250,'4 ms'),(500,'2 ms'),(1000,'1 ms')):
            widget = button(f'{hz} Hz  ·  {latency}', lambda _, h=hz: self.select_rate(h))
            widget.set_hexpand(True); row.append(widget); self.rate_buttons[hz]=widget
            if self.config['polling_hz']==hz: widget.add_css_class('selected')
        info = card('Last-read mouse status')
        self.dpi_live_label = label(self.live_summary(), 'muted', True); info.append(self.dpi_live_label)
        info.append(label('The mouse reports a stage number. DPI values shown above belong to the profile.', 'muted small', True))
        content.append(info)

    def change_dpi(self, adjustment, index):
        value = max(200, min(12000, round(adjustment.get_value()/100)*100))
        if adjustment.get_value()!=value: adjustment.set_value(value)
        self.config['dpi'][index] = value; self.changed()

    def add_stage(self):
        if len(self.config['dpi']) < 6:
            if 'dpi_lighting' in self.config:
                self.config['dpi_lighting']['colors'].append(DPI_INDICATOR_COLORS[len(self.config['dpi'])])
            self.config['dpi'].append(min(12000,self.config['dpi'][-1]+400)); self.build_dpi(); self.changed()

    def remove_stage(self, index):
        if len(self.config['dpi']) > 1:
            if 'dpi_lighting' in self.config:
                del self.config['dpi_lighting']['colors'][index]
            del self.config['dpi'][index]; self.build_dpi(); self.changed()

    def move_stage(self, source, destination):
        if 0 <= destination < len(self.config['dpi']):
            move_dpi_stage(self.config, source, destination)
            self.build_dpi(); self.changed()

    def dpi_lighting_config(self):
        return self.config.setdefault('dpi_lighting', {'enabled': False,
            'colors': list(DPI_INDICATOR_COLORS[:len(self.config['dpi'])])})

    def toggle_dpi_lighting(self, widget, *_):
        self.dpi_lighting_config()['enabled'] = widget.get_active()
        self.build_dpi()
        self.changed()

    def dpi_color_picked(self, widget, _, index):
        rgba = widget.get_rgba()
        color = '#' + ''.join(f'{round(x*255):02x}' for x in (rgba.red, rgba.green, rgba.blue))
        self.dpi_lighting_config()['colors'][index] = color
        widget.set_tooltip_text(f'Stage {index+1} bottom RGB color · {color}')
        self.changed()

    def update_follow_labels(self):
        text = self.follow_message or ('Apply this profile to start linking bottom RGB colors.'
            if self.config.get('dpi_lighting', {}).get('enabled') else 'Bottom RGB linking is off. The wheel indicator works independently.')
        if self.follow_message and self.doc.pending:
            text += ' Editor changes take effect after Apply.'
        if self.config.get('dpi_lighting', {}).get('enabled') and self.config['lighting']['brightness'] == 0:
            text += ' Brightness is zero: increase it on Lighting to see colors.'
        for name in ('dpi_follow_label', 'lighting_follow_label'):
            if hasattr(self, name): getattr(self, name).set_text(text)

    def follow_update(self, revision, update):
        # Ignore queued results from a replaced profile or a foreground command.
        if revision != self.follower.revision or (self.busy and 'error' not in update):
            return False
        if 'error' in update:
            self.device_error(update['error'])
            self.follow_message = 'Bottom RGB linking stopped. Fix device access or connection, then Apply to restart.'
        else:
            self.receive_status(update['status'])
            name = (self.doc.applied or {}).get('name') or 'Untitled profile'
            if update.get('waiting_for_stage'):
                self.follow_message = f'Mouse reports stage {update["stage"]}, outside this {update["stage_count"]}-stage profile. Bottom RGB linking will resume at a configured stage.'
            else:
                self.follow_message = f'Following applied profile “{name}” · Stage {update["stage"]} → bottom RGB {update["color"]}'
        self.update_follow_labels()
        self.apply_button.set_sensitive(not self.busy and not self.raw_dirty and self.ready and not self.offline)
        return False

    def select_rate(self, hz):
        self.config['polling_hz']=hz
        for rate, widget in self.rate_buttons.items():
            (widget.add_css_class if rate==hz else widget.remove_css_class)('selected')
        self.changed()

    # Lighting ------------------------------------------------------------
    def build_lighting(self):
        content = self.page_header('lighting'); lighting = self.config['lighting']
        linked = card('Bottom RGB colors by DPI stage', 'Linking changes the bottom lighting, using a static color and this page’s brightness. The wheel has a separate built-in indicator. Disable linking and Apply to restore the normal bottom effect and palette.')
        self.lighting_follow_label = label('', 'muted small', True); linked.append(self.lighting_follow_label)
        linked.append(button('Edit bottom stage colors', lambda _: self.navigate('dpi')))
        content.append(linked); self.update_follow_labels()
        effects = card('Bottom RGB lighting effect'); content.append(effects)
        grid = Gtk.Grid(column_spacing=10,row_spacing=10); effects.append(grid)
        self.effect_buttons = {}
        for i, name in enumerate(MODES):
            widget = button(EFFECT_LABELS[name], lambda _, n=name: self.select_effect(n))
            widget.set_hexpand(True); widget.set_size_request(-1,48)
            grid.attach(widget, i%4, i//4, 1, 1); self.effect_buttons[name]=widget
            if name==lighting['mode']: widget.add_css_class('selected')
        effects.append(label('Effect names come from the original software. Animation behavior beyond Off and Static still needs testing.', 'muted small', True))
        settings = card('Effect settings'); content.append(settings)
        for key, title in [('brightness','Brightness'),('speed','Animation speed')]:
            row = box(spacing=20); settings.append(row)
            text = label(title); text.set_size_request(145,-1); row.append(text)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,4,1)
            scale.set_digits(0); scale.set_draw_value(True); scale.set_value_pos(Gtk.PositionType.RIGHT)
            scale.set_value(lighting[key]); scale.set_hexpand(True)
            scale.connect('value-changed',lambda w,k=key:self.set_value(lighting,k,round(w.get_value())))
            row.append(scale)
        colors = card('Color palette', 'Choose a swatch to use it. Edit its RGB color with the color picker or hex field.')
        content.append(colors)
        grid = Gtk.Grid(column_spacing=12,row_spacing=14); colors.append(grid)
        self.swatches=[]
        for i, color in enumerate(lighting['colors']):
            cell = box(True,7)
            choice = button(f'Color {i+1}',lambda _,n=i:self.select_color(n))
            if i==lighting.get('selected_color',0):choice.add_css_class('selected')
            cell.append(choice)
            picker = color_picker(f'Bottom palette color {i+1}', color)
            picker.set_hexpand(True); picker.add_css_class('swatch'); cell.append(picker)
            entry = Gtk.Entry(text=color,max_length=7,width_chars=8)
            entry.set_hexpand(True); cell.append(entry)
            picker.connect('notify::rgba',self.color_picked,i,entry)
            entry.connect('activate',self.color_entered,i,picker)
            focus=Gtk.EventControllerFocus(); focus.connect('leave',lambda _,e=entry,n=i,p=picker:self.color_entered(e,n,p)); entry.add_controller(focus)
            self.swatches.append(choice); grid.attach(cell,i%4,i//4,1,1)
        colors.append(label('Eight palette colors, not eight LED zones. Which colors appear depends on the effect.', 'muted small', True))

    def select_effect(self, name):
        self.config['lighting']['mode']=name
        for key,w in self.effect_buttons.items():(w.add_css_class if key==name else w.remove_css_class)('selected')
        self.changed()

    def select_color(self,index):
        self.config['lighting']['selected_color']=index
        for i,w in enumerate(self.swatches):(w.add_css_class if i==index else w.remove_css_class)('selected')
        self.changed()

    def color_picked(self,widget,_,index,entry):
        rgba=widget.get_rgba(); color='#'+''.join(f'{round(x*255):02x}' for x in (rgba.red,rgba.green,rgba.blue))
        self.config['lighting']['colors'][index]=color; entry.set_text(color); self.changed()

    def color_entered(self,entry,index,picker):
        value=entry.get_text().strip()
        try:
            if len(value)!=7 or value[0]!='#': raise ValueError()
            int(value[1:],16)
        except (ValueError,IndexError):
            self.notify('Use a six-digit RGB color, for example #ff8800.', True)
            entry.set_text(self.config['lighting']['colors'][index]); return
        rgba=Gdk.RGBA(); rgba.parse(value); picker.set_rgba(rgba)
        self.config['lighting']['colors'][index]=value.lower(); self.changed()

    # Button mapping ------------------------------------------------------
    def build_buttons(self):
        content = self.page_header('buttons')
        layout = box(spacing=18); content.append(layout)
        visual = card(); visual.set_valign(Gtk.Align.START); layout.append(visual)
        visual.append(label('PULSAR 3', 'eyebrow'))
        canvas = Gtk.Fixed(); canvas.set_size_request(280,370); visual.append(canvas)
        picture=Gtk.Picture.new_for_filename(str(ASSETS/'mouse.svg')); picture.set_size_request(280,370); canvas.put(picture,0,0)
        positions = [(87,98),(179,98),(127,49),(25,177),(20,225),(127,177)]
        self.hotspots={}
        for i,(name,(x,y)) in enumerate(zip(BUTTONS,positions)):
            widget=button(str(i+1),lambda _,n=name:self.choose_button(n),'hotspot',BUTTON_LABELS[name]);canvas.put(widget,x,y)
            self.hotspots[name]=widget
        visual.append(label('Click a numbered button to edit.', 'muted small'))
        right=box(True,12); right.set_hexpand(True); layout.append(right)
        self.binding_rows={}
        for i,name in enumerate(BUTTONS):
            widget=button('',lambda _,n=name:self.choose_button(n),'binding')
            row=box(spacing=12); row.append(label(f'{i+1:02}', 'accent-text'))
            texts=box(True,3);texts.set_hexpand(True)
            texts.append(label(BUTTON_LABELS[name])); detail=label(action_label(self.config['buttons'][name]),'muted small',True)
            texts.append(detail);row.append(texts);row.append(label('›','muted'));widget.set_child(row)
            right.append(widget);self.binding_rows[name]=(widget,detail)
        self.binding_editor=card();content.append(self.binding_editor)
        self.choose_button(self.selected_button)
        content.append(label('Keep at least one button assigned to left click. Custom actions and media keys need functional testing on your mouse.', 'muted small', True))

    def choose_button(self, name):
        self.selected_button=name
        for key,(widget,_) in self.binding_rows.items():
            (widget.add_css_class if name==key else widget.remove_css_class)('active')
            (self.hotspots[key].add_css_class if name==key else self.hotspots[key].remove_css_class)('selected')
        self.build_binding_editor()

    def build_binding_editor(self):
        parent=self.binding_editor; clear(parent)
        name=self.selected_button; action=self.config['buttons'][name]
        parent.append(label('Assign · '+BUTTON_LABELS[name], 'card-title'))
        types=['Mouse & DPI','Media control','Keyboard shortcut','Macro','Advanced bytes']
        kind=0
        if isinstance(action,str):kind=1 if action in list(ACTIONS)[11:] else 0
        elif 'key' in action:kind=2
        elif 'macro' in action:kind=3
        else:kind=4
        category=dropdown(types,kind); parent.append(field('Action type',category))
        options=box(True,12);parent.append(options)
        def render(*_):
            clear(options); selected=category.get_selected()
            if selected in (0,1):
                values=list(ACTIONS)[:11] if selected==0 else list(ACTIONS)[11:]
                current=self.config['buttons'][name]
                choice=dropdown([ACTION_LABELS[v] for v in values],values.index(current) if isinstance(current,str) and current in values else 0)
                options.append(choice)
                options.append(button('Assign action',lambda _:self.assign(name,values[choice.get_selected()]),'primary'))
                if selected==0:options.append(label('Hold the sniper action to lower DPI for slow, precise movement. A separate sniper DPI setting is not available.', 'muted small',True))
            elif selected==2:
                current=self.config['buttons'][name]; current=current if isinstance(current,dict) and 'key' in current else {'key':6,'modifiers':1}
                picker,values=key_picker(current['key']); options.append(field('Key',picker))
                modifiers=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,max_children_per_line=4,min_children_per_line=2,column_spacing=12,row_spacing=8)
                checks=[]
                for title,bit in MODIFIERS:
                    check=Gtk.CheckButton(label=title,active=bool(current.get('modifiers',0)&bit));modifiers.append(check);checks.append((check,bit))
                options.append(modifiers)
                options.append(button('Assign shortcut',lambda _:self.assign(name,{'key':values[picker.get_selected()],'modifiers':sum(bit for w,bit in checks if w.get_active())}),'primary'))
            elif selected==3:
                macros=sorted(self.config.get('macros',[]),key=lambda m:m['slot'])
                if not macros:
                    options.append(label('Create a macro first, then assign it to this button.', 'muted',True))
                    options.append(button('Open macro studio',lambda _:self.navigate('macros')));return
                current=self.config['buttons'][name]; current=current if isinstance(current,dict) and 'macro' in current else {}
                slots=[m['slot'] for m in macros]
                picker=dropdown([f"Macro {m['slot']+1} · {len(m['events'])} events" for m in macros],slots.index(current['macro']) if current.get('macro') in slots else 0)
                mode=dropdown(list(PLAYBACK.values()),list(PLAYBACK).index(current.get('mode','once')))
                options.append(field('Macro',picker));options.append(field('Playback',mode))
                options.append(button('Assign macro',lambda _:self.assign(name,{'macro':slots[picker.get_selected()],'mode':list(PLAYBACK)[mode.get_selected()]}),'primary'))
                options.append(label('Experimental: format verified against the Windows app; playback still needs a mouse test.', 'muted small',True))
            else:
                current=self.config['buttons'][name]; raw=current.get('ui_key',[0,0,243,0]) if isinstance(current,dict) else [0,0,243,0]
                row=box();widgets=[spin(v,0,255) for v in raw]
                for i,w in enumerate(widgets):row.append(field(f'Byte {i+1}',w))
                options.append(row)
                options.append(button('Assign advanced action',lambda _:self.assign(name,{'ui_key':[w.get_value_as_int() for w in widgets]})))
                options.append(label('Original-app action bytes. Generic action types may not work on this model.', 'muted small',True))
        category.connect('notify::selected',render);render()

    def assign(self,name,action):
        candidate=deepcopy(self.config);candidate['buttons'][name]=action
        try:plan(candidate)
        except (ValueError,KeyError,TypeError) as error:self.notify(str(error),True);return
        self.config['buttons'][name]=action
        if name=='dpi':self.dpi_button_label.set_text('DPI button: ' + action_label(action))
        self.binding_rows[name][1].set_text(action_label(action));self.changed()
        self.notify(f'{BUTTON_LABELS[name]} assigned to {action_label(action)}. Apply to send it.')

    # Macro studio --------------------------------------------------------
    def build_macros(self):
        content=self.page_header('macros')
        heading=box();badge=label('EXPERIMENTAL PLAYBACK','badge experimental');heading.append(badge)
        spacer=box();spacer.set_hexpand(True);heading.append(spacer)
        add=button('+ New macro',lambda _:self.add_macro(),'primary');add.set_sensitive(len(self.config.get('macros',[]))<12);heading.append(add);content.append(heading)
        macros=sorted(self.config.get('macros',[]),key=lambda m:m['slot'])
        if not macros:
            empty=card('Your first macro', 'Create a sequence of key presses, mouse clicks, and delays. Then assign it on the Buttons page.')
            empty.append(label('12 device slots · 128 bytes each · no background playback service', 'muted small',True))
            empty.append(label('A new macro starts with an editable A-key tap. Recording replaces its events.', 'muted small',True));content.append(empty);return
        slots=[m['slot'] for m in macros]
        if self.selected_macro not in slots:self.selected_macro=slots[0]
        strip=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,max_children_per_line=6,min_children_per_line=3,column_spacing=8,row_spacing=8)
        for m in macros:
            w=button(f"Macro {m['slot']+1}",lambda _,s=m['slot']:self.select_macro(s))
            if m['slot']==self.selected_macro:w.add_css_class('selected')
            strip.append(w)
        content.append(strip)
        spec=next(m for m in macros if m['slot']==self.selected_macro)
        panel=card();content.append(panel)
        head=box();title=label(f"Macro {spec['slot']+1}",'card-title');title.set_hexpand(True);head.append(title)
        head.append(button('Duplicate',lambda _:self.duplicate_macro(spec)))
        head.append(button('Delete',lambda _:self.delete_macro(spec['slot']),'danger'));panel.append(head)
        repeats=spin(spec.get('repeat',1),1,65535,width=6)
        repeats.connect('value-changed',lambda w:self.macro_repeat(spec,w.get_value_as_int()))
        repeatrow=box(spacing=20);repeatrow.append(field('Repeat count',repeats))
        hint=label('Playback mode is chosen when assigning a button.', 'muted small',True);hint.set_hexpand(True);repeatrow.append(hint);panel.append(repeatrow)
        self.macro_meter=Gtk.ProgressBar(show_text=True);panel.append(self.macro_meter)
        self.macro_error=label('', 'message',True);panel.append(self.macro_error)
        self.event_list=box(True,7);panel.append(self.event_list)
        self.render_events(spec)
        tools=box(spacing=8);tools.append(button('+ Press / release event',lambda _:self.add_event(spec)))
        tools.append(button('Record keyboard…',lambda _:self.record_macro(spec)))
        panel.append(tools)
        tapcard=card('Add a key or shortcut', 'Creates matching press and release events. Modifiers are pressed first and released last.');content.append(tapcard)
        pick,values=key_picker(4,mouse=True)
        row=box();pick.set_hexpand(True);row.append(pick)
        duration=spin(50,10,655350,10,6);row.append(field('Hold (ms)',duration));tapcard.append(row)
        modifierrow=box();checks=[]
        for title,bit in MODIFIERS[:4]:
            check=Gtk.CheckButton(label=title);modifierrow.append(check);checks.append((check,bit))
        tapcard.append(modifierrow)
        tapcard.append(button('+ Add tap / shortcut',lambda _:self.add_tap(spec,values[pick.get_selected()],duration.get_value_as_int(),sum(bit for w,bit in checks if w.get_active()))))
        content.append(label('Delays follow each event. Long delays use 20 ms steps; the final delay must be 10 ms. Every press needs a release. Playback and repeat-mode interaction still need hardware testing.', 'muted small',True))
        self.update_macro_validation(spec)

    def select_macro(self,slot):
        self.selected_macro=slot;self.build_macros()

    def add_macro(self):
        slots={m['slot'] for m in self.config.get('macros',[])}
        free=next((s for s in range(12) if s not in slots),None)
        if free is None:return
        self.config.setdefault('macros',[]).append(new_macro(free));self.selected_macro=free
        self.build_macros();self.build_binding_editor();self.changed()

    def duplicate_macro(self,spec):
        slots={m['slot'] for m in self.config['macros']}
        free=next((s for s in range(12) if s not in slots),None)
        if free is None:self.notify('All 12 macro slots are in use.',True);return
        copied=deepcopy(spec);copied['slot']=free;self.config['macros'].append(copied)
        self.selected_macro=free;self.build_macros();self.build_binding_editor();self.changed()

    def delete_macro(self,slot):
        def remove():
            restored=remove_macro(self.config,slot);self.build_macros();self.build_buttons();self.changed()
            self.notify('Macro deleted.'+(' Referencing buttons restored to their standard actions.' if restored else ''))
        self.confirm('Delete this macro?', 'Any buttons assigned to it will return to their standard actions.', 'Delete macro',remove)

    def render_events(self,spec):
        clear(self.event_list)
        for i,event in enumerate(spec['events']):
            row=box(spacing=7,css='stage-row');row.append(label(f'{i+1:02}','muted small'))
            picker,values=key_picker(event['key'],mouse=True);picker.set_hexpand(True)
            picker.connect('notify::selected',lambda w,_,e=event,v=values:self.change_event(spec,e,'key',v[w.get_selected()]))
            row.append(picker)
            action=dropdown(['Press','Release'],0 if event['action']=='down' else 1)
            action.connect('notify::selected',lambda w,_,e=event:self.change_event(spec,e,'action','down' if w.get_selected()==0 else 'up'));row.append(action)
            delay=spin(event.get('delay_ms',10),10,655350,10,5)
            delay.connect('value-changed',lambda w,e=event:self.change_event(spec,e,'delay_ms',w.get_value_as_int()));row.append(delay);row.append(label('ms','muted small'))
            up=button('↑',lambda _,n=i:self.move_event(spec,n,-1),'flat','Move earlier');up.set_sensitive(i>0);row.append(up)
            down=button('↓',lambda _,n=i:self.move_event(spec,n,1),'flat','Move later');down.set_sensitive(i<len(spec['events'])-1);row.append(down)
            row.append(button('×',lambda _,n=i:self.delete_event(spec,n),'flat danger','Delete event'));self.event_list.append(row)

    def change_event(self,spec,event,key,value):
        event[key]=value;self.update_macro_validation(spec);self.changed()

    def update_macro_validation(self,spec):
        used=macro_bytes(spec);self.macro_meter.set_fraction(min(1,used/128));self.macro_meter.set_text(f'{used} / 128 bytes · {len(spec["events"])} events')
        try:
            encode_macro(spec)
            rounded=[e['delay_ms'] for e in spec['events'] if e.get('delay_ms',10)!=effective_delay(e.get('delay_ms',10))]
            self.macro_error.set_text('Ready to assign to a button.' if not rounded else 'Long delays will round down to the nearest 20 ms.')
            self.macro_error.remove_css_class('error')
        except (ValueError,KeyError,TypeError) as error:
            self.macro_error.set_text(str(error));self.macro_error.add_css_class('error')

    def macro_repeat(self,spec,value):
        spec['repeat']=value;self.update_macro_validation(spec);self.changed()

    def add_tap(self,spec,key,delay,modifiers):
        candidate=deepcopy(spec);append_tap(candidate,key,delay,modifiers)
        if macro_bytes(candidate)>128:self.notify('This tap exceeds the 128-byte macro limit. Remove events first.',True);return
        spec['events']=candidate['events'];self.render_events(spec);self.update_macro_validation(spec);self.changed()

    def add_event(self,spec):
        if macro_bytes(spec)+2>128:self.notify('This macro has no room for another event.',True);return
        spec['events'].append({'key':4,'action':'down','delay_ms':10})
        self.render_events(spec);self.update_macro_validation(spec);self.changed()

    def delete_event(self,spec,index):
        del spec['events'][index];self.render_events(spec);self.update_macro_validation(spec);self.changed()

    def move_event(self,spec,index,delta):
        other=index+delta
        if 0<=other<len(spec['events']):
            spec['events'][index],spec['events'][other]=spec['events'][other],spec['events'][index]
            self.render_events(spec);self.update_macro_validation(spec);self.changed()

    def record_macro(self,spec):
        from .recorder import RecorderDialog
        def accept(events):
            candidate=deepcopy(spec);candidate['events']=events
            try:encode_macro(candidate)
            except ValueError as error:self.notify(str(error),True);return
            spec['events']=events;self.build_macros();self.changed()
        RecorderDialog(self.window,accept).present()

    # Profiles, advanced and device --------------------------------------
    def build_profiles(self):
        content=self.page_header('profiles')
        panel=card('Current profile');content.append(panel)
        name=Gtk.Entry(text=self.config.get('name',''),hexpand=True)
        name.connect('changed',lambda w:self.set_value(self.config,'name',w.get_text()));panel.append(field('Profile name',name))
        source=str(self.profile_path) if self.profile_path else 'Unsaved profile'
        panel.append(label(source,'muted small',True))
        actions=box();panel.append(actions)
        actions.append(button('Save',lambda _:self.save_profile(),'primary'))
        actions.append(button('Save as…',lambda _:self.file_dialog(True)))
        actions.append(button('Open JSON…',lambda _:self.guard_discard(lambda:self.file_dialog(False))))
        actions.append(button('Revert edits',lambda _:self.guard_discard(self.revert)))
        library=card('Local profiles','Open a profile to edit it. Applying is always a separate action.');content.append(library)
        for path in [DEFAULT_PROFILE, *sorted(profiles_dir().glob('*.json'))]:
            try:
                data=json.loads(path.read_text());title=data.get('name') or path.stem
                description=f"{len(data['dpi'])} DPI stages · {data['polling_hz']} Hz · {EFFECT_LABELS.get(data['lighting']['mode'],data['lighting']['mode'])}"
            except (ValueError,KeyError,TypeError,OSError):continue
            row=box(spacing=12);texts=box(True,4);texts.set_hexpand(True)
            texts.append(label(title,wrap=True));texts.append(label(description+' · '+path.name,'muted small',True));row.append(texts)
            row.append(button('Open',lambda _,p=path:self.guard_discard(lambda:self.load_profile(p))))
            library.append(row)
        content.append(label('Profiles live on this computer. Onboard profile banks and persistence after power loss have not been verified.', 'muted small',True))

    def build_advanced(self):
        content=self.page_header('advanced')
        content.append(label('JSON edits are staged here. Load them into the editor before saving or applying. Invalid data is never sent.', 'muted small',True))
        self.json_buffer=Gtk.TextBuffer();self.raw_dirty=False;self.sync_json()
        self.json_buffer.connect('changed',self.json_changed)
        view=Gtk.TextView(buffer=self.json_buffer,monospace=True,left_margin=14,right_margin=14,top_margin=12,bottom_margin=12)
        scroll=Gtk.ScrolledWindow(min_content_height=350,vexpand=True);scroll.set_child(view);content.append(scroll)
        actions=box();content.append(actions)
        actions.append(button('Load JSON into editor',self.load_json,'primary'))
        actions.append(button('Reset JSON to current profile',lambda _:self.reset_json()))

    def sync_json(self):
        self.syncing_json=True
        self.json_buffer.set_text(json.dumps(self.config,indent=2))
        self.syncing_json=False

    def json_changed(self,*_):
        if not self.syncing_json:
            self.raw_dirty=True;self.changed();self.notify('JSON has pending edits. Load it into the editor before Save or Apply.')

    def reset_json(self):
        self.raw_dirty=False;self.sync_json();self.changed();self.notify('JSON reset to the current editor profile.')

    def parsed_json(self):
        buf=self.json_buffer
        data=json.loads(buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False));plan(data);return data

    def load_json(self,*_):
        try:data=self.parsed_json()
        except (ValueError,KeyError,TypeError) as error:self.notify(str(error),True);return
        self.doc.config=data;self.raw_dirty=False;self.rebuild();self.notify('JSON loaded into the editor. Nothing sent to the mouse.')

    def build_device(self):
        content=self.page_header('device')
        panel=card('HATOR Pulsar 3','USB 379a:3910 · native Linux configuration');content.append(panel)
        self.device_state=label('Offline preview' if self.offline else 'Checking connection…',wrap=True);panel.append(self.device_state)
        actions=box();panel.append(actions)
        self.access_button=button('Enable device access',self.authorize,'primary');actions.append(self.access_button)
        self.refresh_button=button('Refresh status',self.read_status);actions.append(self.refresh_button)
        self.access_button.set_sensitive(not self.offline);self.refresh_button.set_sensitive(not self.offline)
        panel.append(label('The system password dialog grants temporary access. Repeat after reconnecting or rebooting. The application stays unprivileged.', 'muted small',True))
        live=card('Last-read device status');content.append(live)
        self.device_live=label(self.live_summary(),wrap=True);live.append(self.device_live)
        self.status_time=label(self.live_time or 'No status received this session.','muted small');live.append(self.status_time)
        live.append(label('Available: polling rate, active DPI stage, lighting mode and speed. DPI values, colors, brightness, button bindings and macros cannot currently be read back.', 'muted small',True))
        details=card('Configuration notes');content.append(details)
        details.append(label('Apply sends the complete profile, including supplied macros. A failed transfer can leave only some settings applied. Keep the profile and retry after fixing access or connection.', 'muted',True))
        details.append(label('The app does not update firmware. “Apply” writes configuration settings. No Windows installation or virtual machine is required.', 'muted small',True))
        self.device_paths=label('', 'muted small',True);details.append(self.device_paths)
        self.update_live()

    def live_summary(self):
        if not self.live:return 'No device status yet. Connect your mouse and enable access if needed.'
        s=self.live
        return f"{s['polling_hz']} Hz  ·  DPI stage {s['dpi_stage']}  ·  {EFFECT_LABELS.get(s['lighting_mode'],s['lighting_mode'])} lighting  ·  speed {s['lighting_speed']}"

    def update_live(self):
        if not hasattr(self,'device_live'):return
        self.device_live.set_text(self.live_summary());self.dpi_live_label.set_text(self.live_summary())
        self.status_time.set_text(self.live_time or 'No status received this session.')
        if self.device_info:
            self.device_paths.set_text(f"USB: {self.device_info['usb']}\nStatus: {self.device_info['status_hidraw']}")
        if self.ready:self.device_state.set_text('Connected · device access enabled')

    # File and hardware operations ---------------------------------------
    def validate(self,*_):
        try:
            config=self.parsed_json() if self.raw_dirty else self.doc.validated()
            packets=plan(config);self.notify(f'Profile valid · {len(packets)} USB transactions. No settings changed.')
        except (ValueError,KeyError,TypeError) as error:self.notify(str(error),True)

    @staticmethod
    def write_profile(path,snapshot):
        path=Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name+'.',delete=False) as f:
            temporary=Path(f.name);f.write(json.dumps(snapshot,indent=2)+'\n')
        try:temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)

    def save_profile(self):
        if self.raw_dirty:self.notify('Load the JSON changes into the editor first.',True);return
        # Keep the bundled defaults intact.
        if not self.profile_path or self.profile_path==DEFAULT_PROFILE:self.file_dialog(True);return
        try:
            snapshot=self.doc.validated();self.write_profile(self.profile_path,snapshot);self.doc.mark_saved(snapshot)
            self.changed();self.notify(f'Profile saved · {self.profile_path.name}. Mouse settings were not changed.')
        except (ValueError,KeyError,TypeError,OSError) as error:self.notify(str(error),True)

    def file_dialog(self,save):
        if save and self.raw_dirty:
            self.notify('Load the JSON changes into the editor first.', True);return
        if save:
            try:snapshot=self.doc.validated()
            except (ValueError,KeyError,TypeError) as error:self.notify(str(error),True);return
        dialog=Gtk.FileChooserNative(title='Save profile as' if save else 'Open profile',transient_for=self.window,
            action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN,
            accept_label='Save' if save else 'Open',cancel_label='Cancel')
        filt=Gtk.FileFilter();filt.set_name('JSON profiles');filt.add_pattern('*.json');dialog.add_filter(filt)
        profiles_dir().mkdir(parents=True, exist_ok=True)
        dialog.set_current_folder(Gio.File.new_for_path(str(profiles_dir())))
        if save:dialog.set_current_name('pulsar-profile.json')
        def response(d,result):
            if result==Gtk.ResponseType.ACCEPT:
                try:
                    path=Path(d.get_file().get_path())
                    if save:
                        if path.suffix.lower()!='.json':path=path.with_suffix('.json')
                        self.write_profile(path,snapshot);self.profile_path=path;self.doc.mark_saved(snapshot);self.changed();self.build_profiles()
                        self.notify(f'Saved {path.name}. Nothing sent to the mouse.')
                    else:self.load_profile(path)
                except (ValueError,KeyError,TypeError,OSError) as error:self.notify(str(error),True)
            d.destroy()
        dialog.connect('response',response);dialog.show()

    def load_profile(self,path):
        try:
            self.doc.load(json.loads(path.read_text()));self.profile_path=path;self.raw_dirty=False;self.rebuild()
            self.notify(f'Opened {path.name}. Apply to send this profile to the mouse.')
        except (ValueError,KeyError,TypeError,OSError) as error:self.notify(str(error),True)

    def revert(self):
        self.doc.config=deepcopy(self.doc.saved);self.raw_dirty=False;self.rebuild();self.notify('Restored the last saved profile in the editor.')

    def confirm(self,title,description,accept,callback):
        return confirm(self.window,title,description,accept,callback)

    def guard_discard(self,callback):
        if self.doc.dirty or self.raw_dirty:self.confirm('Discard unsaved edits?', 'Your saved profile and current mouse settings will stay as they are.', 'Discard edits',callback)
        else:callback()

    def close_requested(self,*_):
        if self.allow_close:return False
        if self.busy:self.notify('Wait for the current device operation to finish before closing.',True);return True
        if self.doc.dirty or self.raw_dirty:
            def close():self.allow_close=True;self.window.close()
            self.guard_discard(close);return True
        return False

    def run_task(self,command,callback):
        if self.busy:return
        self.follower.pause()
        self.busy=True;self.stack.set_sensitive(False);self.spinner.start();self.changed()
        def worker():
            try:
                with self.device_lock:
                    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180)
                values=(result.returncode,result.stdout,result.stderr)
            except Exception as error:values=(1,'',str(error))
            GLib.idle_add(done,*values)
        def done(code,out,err):
            self.busy=False;self.stack.set_sensitive(True);self.spinner.stop()
            try:callback(code,out,err)
            except (ValueError,KeyError,TypeError,OSError) as error:self.notify(f'Could not finish operation: {error}',True)
            # A callback can start another task (authorization -> status).
            if not self.busy:self.follower.resume()
            self.changed();return False
        threading.Thread(target=worker,daemon=True).start()

    def read_status(self,*_):
        if self.offline or self.busy:return
        self.notify('Reading mouse status…')
        def finish(code,out,err):
            if code:self.device_error(err);return
            result=json.loads(out);self.device_info=result['device'];self.receive_status(result['status'])
            self.notify('Device status refreshed. Profile values were not replaced.')
        self.run_task([sys.executable,'-m','pulsar3','status'],finish)

    def receive_status(self,status):
        self.live=status;self.live_time='Read at '+datetime.now().strftime('%H:%M:%S')
        self.ready=True;self.connection.set_label('● Connected');self.update_live()

    def device_error(self,error):
        self.follower.configure()
        if self.follow_message:
            self.follow_message='DPI colors stopped. Fix device access or connection, then Apply to restart.'
        self.ready=False
        if 'Permission denied' in error:
            title='Access required';message='Click Device → Enable device access, then use the system password dialog.'
        elif 'found 0' in error:
            title='Mouse disconnected';message='Connect your HATOR Pulsar 3. You can keep editing profiles offline.'
        elif 'found ' in error:
            title='Check connected mice';message='The current backend expects exactly one matching mouse.'
        else:title='Device unavailable';message=error.strip() or 'Device operation failed.'
        self.connection.set_label(title);self.device_state.set_text(title)
        if self.live_time:self.live_time=self.live_time.split(' · ')[0]+' · stale';self.update_live()
        self.notify(message,True)

    def authorize(self,*_):
        if self.offline or self.busy:return
        try:
            info=discover();paths=[info['usb'],info['status_hidraw']]
            if not all(paths):raise RuntimeError('Mouse status interface missing')
            self.device_info=info;self.notify('Enter your password in the system authentication dialog.')
            def finish(code,out,err):
                if code:self.device_error(err or 'Authentication canceled. Device access was not enabled.')
                else:self.read_status()
            self.run_task(device_access_command(paths),finish)
        except (OSError,RuntimeError) as error:self.device_error(str(error));self.changed()

    def apply(self,*_):
        if self.busy or self.raw_dirty or self.offline:return
        try:
            snapshot=self.doc.validated()
            with tempfile.NamedTemporaryFile(mode='w',suffix='.json',prefix='pulsar-apply-',delete=False) as f:
                json.dump(snapshot,f);temporary=Path(f.name)
            self.follower.configure();self.follow_message=None
            self.notify('Applying profile, including macro definitions…')
            def finish(code,out,err):
                temporary.unlink(missing_ok=True)
                if code:
                    self.doc.applied=None
                    self.device_error(err);self.notify((err.strip() or 'Transfer failed.')+' Some settings may have been applied. Fix access/connection and retry.',True);return
                result=json.loads(out);self.doc.mark_applied(snapshot);self.receive_status(result['status'])
                self.follower.configure(snapshot)
                if snapshot.get('dpi_lighting', {}).get('enabled'):
                    self.follow_message='Starting bottom RGB colors for the applied profile…'
                try:
                    self.write_profile(WORKING,snapshot)
                    if self.profile_path==WORKING:self.doc.mark_saved(snapshot)
                    self.notify('Configuration sent. Available device status refreshed; full settings readback is not supported.')
                except OSError as error:self.notify(f'Configuration sent, but the working profile could not be saved: {error}',True)
            self.run_task([sys.executable,'-m','pulsar3','apply',str(temporary),'--commit'],finish)
        except (ValueError,KeyError,TypeError,OSError) as error:self.notify(str(error),True)


def main():
    offline='--offline' in sys.argv
    return Editor(offline=offline).run([a for a in sys.argv if a!='--offline'])


if __name__=='__main__':
    sys.exit(main())
