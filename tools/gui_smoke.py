"""Offline GTK interaction checks. Never reads/writes the mouse or user profiles."""
import json
from pathlib import Path
import sys
import tempfile
import traceback
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from pulsar3.gui import Editor,ROOT

app=Editor(offline=True,profile_path=ROOT/'profiles/default.json')
failed=[]

def later(callback,delay=300):
    def run():
        try:callback()
        except Exception:
            failed.append(traceback.format_exc());print(failed[-1],flush=True);app.quit()
        return False
    GLib.timeout_add(delay,run)

def screenshot(name):
    paintable=Gtk.WidgetPaintable.new(app.window)
    snapshot=Gtk.Snapshot()
    paintable.snapshot(snapshot,app.window.get_width(),app.window.get_height())
    node=snapshot.to_node()
    if node:
        renderer=app.window.get_renderer()
        texture=renderer.render_texture(node,None)
        texture.save_to_png(f'/tmp/pulsar-{name}.png')
    print('Rendered',name,flush=True)

pages=iter(['dpi','lighting','buttons','macros','profiles','device','advanced'])
def next_page():
    try:page=next(pages)
    except StopIteration:
        app.doc.config=app.doc.saved.copy();app.allow_close=True;app.quit();return
    app.navigate(page)
    later(lambda:(screenshot(page),next_page()),400)

def checks():
    # Shared DPI adjustment, bounds, stage count, rate and color state.
    app.dpi_widgets[0].set_value(850)
    assert app.config['dpi'][0]==800
    app.remove_stage(5);app.add_stage();assert len(app.config['dpi'])==6
    app.select_rate(500);assert app.config['polling_hz']==500
    app.select_effect('breath');app.select_color(3)
    assert app.config['lighting']['selected_color']==3
    # Macro editing and custom button bindings round-trip through plan and JSON.
    app.add_macro();assert app.config['macros'][0]['slot']==0
    spec=app.config['macros'][0];app.add_tap(spec,6,50,1)
    app.assign('back',{'macro':0,'mode':'hold'})
    app.assign('forward',{'key':25,'modifiers':1})
    assert app.doc.validated()['buttons']['back']['macro']==0
    # Invalid JSON cannot replace profile. Valid JSON updates graphical controls.
    original=app.config['polling_hz'];app.json_buffer.set_text('{');app.load_json()
    assert app.config['polling_hz']==original and app.raw_dirty
    app.reset_json();data=app.doc.validated();data['polling_hz']=1000
    app.json_buffer.set_text(json.dumps(data));app.load_json()
    assert not app.raw_dirty and app.config['polling_hz']==1000
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory)/'profile.json';app.write_profile(target,app.doc.validated())
        assert json.loads(target.read_text())==app.config
    assert not app.apply_button.get_sensitive()
    # Failed submissions do not overwrite the saved working profile or applied state.
    before=(ROOT/'profiles/linux.json').read_bytes()
    app.offline=False
    def failed_task(command,callback):callback(1,'','Simulated USB interruption')
    app.doc.mark_applied(app.config)
    with patch.object(app,'run_task',failed_task):app.apply()
    assert (ROOT/'profiles/linux.json').read_bytes()==before
    assert app.doc.applied is None and not app.ready
    assert 'Some settings may have been applied' in app.message.get_text()
    # Success updates the submitted snapshot, not arbitrary later edits.
    status={'polling_hz':1000,'dpi_stage':2,'lighting_mode':'static','lighting_speed':4}
    def successful_task(command,callback):callback(0,json.dumps({'status':status,'journal':'test'}),'')
    with patch.object(app,'run_task',successful_task), patch.object(app,'write_profile') as write:
        app.apply()
        assert write.call_count==1
    assert app.doc.applied==app.config and not app.doc.pending
    # Recorder controls and capture handlers must work without global hooks.
    from pulsar3.recorder import RecorderDialog
    from gi.repository import Gdk
    recorder=RecorderDialog(app.window,lambda events:None)
    recorder.begin()
    assert recorder.key_pressed(None,Gdk.KEY_a,38,0)
    recorder.key_released(None,Gdk.KEY_a,38,0)
    recorder.stop()
    assert recorder.use.get_sensitive()
    assert len(recorder.recording.events)==2
    recorder.window.destroy()
    app.offline=True;app.ready=False;app.connection.set_label('Offline preview');app.changed()
    for name,page in app.pages.items():
        minimum=page.measure(Gtk.Orientation.HORIZONTAL,-1).minimum
        print(f'{name} minimum content width: {minimum}',flush=True)
    print('GTK state and profile checks passed',flush=True)
    next_page()

app.connect('activate',lambda *_:later(checks,700))
app.run(['gui-smoke'])
sys.exit(bool(failed))
