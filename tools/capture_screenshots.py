#!/usr/bin/env python3
"""Capture real GUI screenshots with example data and hardware access disabled.

Requires a graphical session. Does not read or modify personal mouse profiles.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT/'docs/screenshots')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
scratch = tempfile.TemporaryDirectory(prefix='pulsar-screenshots-')
os.environ['XDG_DATA_HOME'] = str(Path(scratch.name)/'data')
os.environ['XDG_STATE_HOME'] = str(Path(scratch.name)/'state')

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from pulsar3.gui import Editor
from pulsar3.paths import DEFAULT_PROFILE
from pulsar3.editor_model import append_tap

example = json.loads(DEFAULT_PROFILE.read_text())
example['name'] = 'Everyday'
example['dpi'] = [400, 800, 1600, 3200]
example['lighting'].update(mode='static', brightness=4, speed=2, selected_color=0)
example['lighting']['colors'] = ['#f1df23', '#38bdf8', '#a78bfa', '#fb7185', '#4ade80', '#fb923c', '#22d3ee', '#ffffff']
example['dpi_lighting'] = {'enabled': True, 'colors': example['lighting']['colors'][:len(example['dpi'])]}
macro = {'slot': 0, 'repeat': 1, 'events': []}
append_tap(macro, 6, 50, 1)
example['macros'] = [macro]
example['buttons']['back'] = {'macro': 0, 'mode': 'once'}
example['buttons']['forward'] = {'key': 25, 'modifiers': 1}
profile = Path(scratch.name)/'example.json'
profile.write_text(json.dumps(example))
app = Editor(offline=True, profile_path=profile)
errors = []
pages = iter(['dpi', 'buttons', 'lighting', 'macros'])


def later(callback, delay=350):
    def run():
        try:
            callback()
        except Exception:
            errors.append(traceback.format_exc())
            print(errors[-1], flush=True)
            app.quit()
        return False
    GLib.timeout_add(delay, run)


def capture(page):
    window = app.preview_window
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError('Window did not produce a render node')
    texture = window.get_renderer().render_texture(node, None)
    target = args.output/f'{page}.png'
    if not texture.save_to_png(str(target)):
        raise RuntimeError(f'Could not save {target}')
    print(f'{target.name}: {window.get_width()}×{window.get_height()}', flush=True)
    next_page()


def next_page():
    try:
        page = next(pages)
    except StopIteration:
        app.allow_close = True
        app.preview_window.destroy()
        app.quit()
        return
    app.navigate(page)
    content = app.preview_window.get_child()
    app.preview_window.set_child(None)
    app.preview_window.destroy()
    preview = Gtk.Window(title='Pulsar 3 Studio · screenshot preview',
                         application=app, transient_for=app.window, modal=True,
                         default_width=1180,
                         default_height={'dpi':1200, 'buttons':1240, 'lighting':1380, 'macros':1360}[page])
    preview.add_css_class('pulsar')
    preview.set_child(content)
    app.preview_window = preview
    preview.present()
    later(lambda: capture(page), 500)


def start():
    # A transient preview window gets a useful fixed size under tiling desktops.
    # Capture the actual application widgets; no image compositing or fake UI.
    preview = Gtk.Window(title='Pulsar 3 Studio · screenshot preview',
                         application=app, transient_for=app.window, modal=True,
                         default_width=1180, default_height=1080)
    preview.add_css_class('pulsar')
    content = app.window.get_child()
    app.window.set_child(None)
    preview.set_child(content)
    app.preview_window = preview
    app.doc.config = deepcopy(example)
    app.rebuild()
    app.notify('Offline preview · example profile. No mouse settings are changed.')
    preview.present()
    later(next_page, 600)


app.connect('activate', lambda *_: later(start, 300))
app.run(['pulsar-screenshots'])
scratch.cleanup()
sys.exit(bool(errors))
