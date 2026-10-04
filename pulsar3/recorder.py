"""Focused keyboard recorder; never installs a global keyboard hook."""
import time
from .editor_model import key_label, macro_bytes

# GDK key names -> USB keyboard usages. Recording is intentionally limited to
# familiar keyboard keys. The manual picker supports every accepted usage.
KEYVAL_USAGES = {chr(97+i):4+i for i in range(26)}
KEYVAL_USAGES.update({str((i+1)%10):30+i for i in range(10)})
KEYVAL_USAGES.update({f'F{i+1}':58+i for i in range(12)})
KEYVAL_USAGES.update({f'F{i+13}':104+i for i in range(12)})
KEYVAL_USAGES.update(dict(zip(['exclam','at','numbersign','dollar','percent','asciicircum','ampersand','asterisk','parenleft','parenright'],range(30,40))))
KEYVAL_USAGES.update({'Return':40,'BackSpace':42,'Tab':43,'ISO_Left_Tab':43,'space':44,
    'minus':45,'underscore':45,'equal':46,'plus':46,'bracketleft':47,'braceleft':47,
    'bracketright':48,'braceright':48,'backslash':49,'bar':49,'semicolon':51,'colon':51,
    'apostrophe':52,'quotedbl':52,'grave':53,'asciitilde':53,'comma':54,'less':54,
    'period':55,'greater':55,'slash':56,'question':56,'Caps_Lock':57,'Print':70,
    'Scroll_Lock':71,'Pause':72,'Insert':73,'Home':74,'Page_Up':75,'Delete':76,'End':77,
    'Page_Down':78,'Right':79,'Left':80,'Down':81,'Up':82,'Num_Lock':83,
    'KP_Divide':84,'KP_Multiply':85,'KP_Subtract':86,'KP_Add':87,'KP_Enter':88,
    'KP_0':98,'KP_Decimal':99,'Menu':101,'Control_L':224,'Shift_L':225,'Alt_L':226,
    'Super_L':227,'Control_R':228,'Shift_R':229,'Alt_R':230,'ISO_Level3_Shift':230,'Super_R':231})
KEYVAL_USAGES.update({f'KP_{i+1}':89+i for i in range(9)})


class Recording:
    """Build balanced events and quantize elapsed time to the wire resolution."""
    def __init__(self):
        self.events=[]
        self.pressed={}
        self.last_time=None

    def _append(self,usage,action,now):
        if self.events and self.last_time is not None:
            delay=max(10,min(655350,round((now-self.last_time)*100)*10))
            if delay>=1270:delay=delay//20*20
            self.events[-1]['delay_ms']=delay
        self.events.append({'key':usage,'action':action,'delay_ms':10})
        self.last_time=now

    def press(self,physical_key,usage,now):
        if physical_key in self.pressed:return  # suppress auto-repeat
        if usage in self.pressed.values():return
        self.pressed[physical_key]=usage;self._append(usage,'down',now)

    def release(self,physical_key,now):
        if physical_key in self.pressed:self._append(self.pressed.pop(physical_key),'up',now)

    def stop(self,now):
        for physical_key in list(reversed(self.pressed)):
            self.release(physical_key,now)
        if self.events:self.events[-1]['delay_ms']=10
        return self.events


class RecorderDialog:
    def __init__(self,parent,on_accept):
        import gi
        gi.require_version('Gtk','4.0')
        from gi.repository import Gdk,Gtk
        from .gui import box,button,label
        self.Gdk=Gdk;self.Gtk=Gtk;self.recording=Recording();self.active=False
        self.window=Gtk.Window(title='Record a macro',transient_for=parent,modal=True,default_width=540)
        self.window.add_css_class('pulsar')
        body=box(True,18,'page');self.window.set_child(body)
        body.append(label('Record keyboard','page-title'))
        body.append(label('Records only while this window has focus. Click Start, type your sequence, then press Escape to stop. Use the event editor for mouse clicks or Escape.', 'subtitle',True))
        body.append(label('Recording replaces this macro’s events when you choose Use recording. Common keys use their standard USB positions; check the result if you use another layout.', 'muted small',True))
        self.state=label('Ready to record.',wrap=True);body.append(self.state)
        self.preview=Gtk.TextView(editable=False,cursor_visible=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll=Gtk.ScrolledWindow(min_content_height=160);scroll.set_child(self.preview);body.append(scroll)
        row=box();body.append(row)
        self.start=button('Start recording',self.begin,'primary');row.append(self.start)
        self.stop_button=button('Stop',lambda _:self.stop());self.stop_button.set_sensitive(False);row.append(self.stop_button)
        self.use=button('Use recording',lambda _:(on_accept(self.recording.events),self.window.destroy()))
        self.use.set_sensitive(False);row.append(self.use)
        row.append(button('Cancel',lambda _:self.window.destroy()))
        controller=Gtk.EventControllerKey();controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect('key-pressed',self.key_pressed);controller.connect('key-released',self.key_released);self.window.add_controller(controller)
        self.window.connect('notify::is-active',self.focus_changed)

    def present(self):self.window.present()

    def begin(self,*_):
        self.recording=Recording();self.active=True;self.start.set_sensitive(False)
        self.stop_button.set_sensitive(True);self.use.set_sensitive(False)
        self.state.set_text('Recording… Escape stops. Desktop-reserved shortcuts may not reach this window.')
        self.preview.get_buffer().set_text('')

    def stop(self):
        if not self.active:return
        from .protocol import encode_macro
        self.recording.stop(time.monotonic());self.active=False
        self.start.set_sensitive(True);self.start.set_label('Record again');self.stop_button.set_sensitive(False)
        try:
            spec={'slot':0,'repeat':1,'events':self.recording.events};encode_macro(spec)
            self.use.set_sensitive(True);self.state.set_text(f"{len(self.recording.events)} events · {macro_bytes(spec)} / 128 bytes. Ready to use.")
        except ValueError as error:self.state.set_text(str(error));self.use.set_sensitive(False)
        self.show_events()

    def focus_changed(self,*_):
        if self.active and not self.window.is_active():self.stop()

    def key_pressed(self,_,keyval,keycode,state):
        if not self.active:return False
        name=self.Gdk.keyval_name(keyval)
        if name=='Escape':self.stop();return True
        usage=KEYVAL_USAGES.get(name,KEYVAL_USAGES.get(name.lower()) if name else None)
        if usage is None:
            self.state.set_text('This key cannot be recorded. Add it with the manual key picker.');return True
        self.recording.press(keycode,usage,time.monotonic());self.show_events()
        # Reserve enough capacity for held-key releases and possible long delays.
        size=macro_bytes({'events':self.recording.events})+6*len(self.recording.pressed)
        if size>=118:self.stop()
        return True

    def key_released(self,_,keyval,keycode,state):
        if self.active:self.recording.release(keycode,time.monotonic());self.show_events()

    def show_events(self):
        text='\n'.join(f"{i+1:02}  {e['action']:4}  {key_label(e['key']):14}  {e['delay_ms']} ms" for i,e in enumerate(self.recording.events))
        self.preview.get_buffer().set_text(text)
