"""Use current GTK dialogs when available, with GTK 4.6-compatible fallbacks."""
from gi.repository import Gdk, GLib, Gtk


def color_picker(title, color, *, legacy=False):
    rgba = Gdk.RGBA()
    rgba.parse(color)
    if not legacy and hasattr(Gtk, 'ColorDialogButton'):
        picker = Gtk.ColorDialogButton.new(Gtk.ColorDialog(title=title, with_alpha=False))
    else:
        picker = Gtk.ColorButton(title=title, use_alpha=False, modal=True)
    picker.set_rgba(rgba)
    return picker


def confirm(parent, title, description, accept, callback, *, legacy=False):
    if not legacy and hasattr(Gtk, 'AlertDialog'):
        dialog = Gtk.AlertDialog(message=title, detail=description,
                                 buttons=['Keep editing', accept], cancel_button=0, default_button=0)

        def done(dialog, result):
            try:
                if dialog.choose_finish(result) == 1:
                    callback()
            except GLib.Error:
                pass

        dialog.choose(parent, None, done)
    else:
        dialog = Gtk.MessageDialog(transient_for=parent, modal=True, text=title,
                                   secondary_text=description, buttons=Gtk.ButtonsType.NONE)
        dialog.add_button('Keep editing', Gtk.ResponseType.CANCEL)
        dialog.add_button(accept, Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        def done(dialog, response):
            dialog.destroy()
            if response == Gtk.ResponseType.ACCEPT:
                callback()

        dialog.connect('response', done)
        dialog.present()
    return dialog
