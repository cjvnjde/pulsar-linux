# HATOR Pulsar 3 on Linux

For UI design scope and implementation readiness, see [UI_CAPABILITIES.md](UI_CAPABILITIES.md). For operating instructions, see [USER_GUIDE.md](USER_GUIDE.md).

Native Python/GTK4 configurator for the **HATOR Pulsar 3, USB 379a:3910**.
Reverse-engineered from the supplied `Pulsar 3 Software_20250227.exe`.
It communicates directly with USB: no Windows, Wine, VM, or replacement firmware.

## Start

```sh
cd /home/cjvnjde/Work/pulsar-linux
./pulsar3-gui
```

Python 3, PyGObject, GTK4 (4.10+), and libadwaita are already present on this machine. The CLI only
needs Python's standard library. No reverse-engineering tools are required to run it.

Click **Enable device access** if needed. The system password dialog grants your
account access to this mouse's USB node and its status HID node. This is temporary;
repeat after reconnecting the mouse. The application itself runs as your normal user.
It never detaches the regular mouse/keyboard drivers.

The controls edit a local profile. **Apply to mouse** writes it to the device.
**Device → Refresh status** reports actual polling rate, active DPI stage, lighting mode and speed;
it does not overwrite the profile editor.

After a successful Apply, the GUI saves the submitted configuration to `profiles/linux.json`. **Save profile** writes a local file without changing the mouse. Failed transfers preserve the previous working file; they can still leave some device settings changed.
The initial requested profile was 1000 Hz, DPI stages 400/800/1000/1200/1600/3200,
lighting off, and standard buttons; subsequent GUI edits update that file.
`default.json` contains
values shipped with the Windows app; neither file is a backup of settings read
from the mouse. The physical DPI button selects the active stage.

## Verification and limits

- Native status reads work on your connected device.
- Changing polling to 500 Hz and lighting to static/slow, then restoring 1000 Hz
  and lighting off/fast, was verified through live device responses.
- The selected DPI values and standard button mappings were transmitted successfully.
  Full configuration readback has not been established, so those settings are not
  independently verified by reading their values from the device.
- Packet builders match the original executable; 288 button conversions were
  checked against its machine code, and 21 macro vectors against its embedded JS.
- Macros and non-default button assignments are implemented but have not been
  functionally exercised on this mouse. Test them in an appropriate application.
- The old direct active-DPI command is ignored by this model; it is not exposed.
- Persistence after unplugging has not been tested. Save profiles on disk so they
  can be reapplied. Software profiles are not claimed to be independent onboard banks.
- Firmware updates, full hardware backups, and settings the supplied app does not
  expose (such as debounce or lift-off distance) are not implemented.

## CLI

From this directory:

```sh
python -m pulsar3 detect
python -m pulsar3 status
python -m pulsar3 probe
python -m pulsar3 plan profiles/linux.json
python -m pulsar3 apply profiles/linux.json --commit
```

`apply` without `--commit` only previews packets. All fields are validated before
opening the device. Completed writes and before/after status are recorded in
`history/`; this journal is **not a full device backup**.

A selective write avoids replacing unrelated groups:

```sh
python -m pulsar3 apply profiles/linux.json --sections dpi --commit
python -m pulsar3 apply profiles/linux.json --sections parameters,colors --commit
```

Groups: `parameters` (polling, DPI stage count, lighting mode/brightness/speed/color
selection), `dpi`, `colors`, `buttons`, `macros`. These follow the original app's
transaction grouping. Each profile must still contain all six physical button
assignments. Macro bindings must have corresponding macro definitions.

## Editing profiles

The redesigned native GUI uses a dark theme with yellow accents:

- **Buttons:** interactive mouse diagram, standard actions, media controls, keyboard
  shortcuts with modifiers, macro bindings, and advanced action bytes.
- **DPI & polling:** add/remove up to six stages, stepped sliders and numeric fields,
  and 125–1000 Hz polling choices. The physical DPI button switches active stages.
- **Lighting:** effect cards, brightness/speed sliders, eight color pickers and hex
  fields, and palette selection.
- **Macros:** twelve slots, editable press/release events, delays, repeat count,
  reorder/delete, shortcut builder, duplication, and a 128-byte capacity meter.
  **Record keyboard** captures keys only in its focused dialog; Escape stops recording.
  Assign a macro and its playback mode on the Buttons page.
- **Profiles:** name, open, save, save as, and revert edits. Files are local profiles,
  not verified onboard banks.
- **Device:** graphical access permission and live status refresh.
- **Advanced:** JSON import/editing. Choose **Load JSON into editor** before Save/Apply.

Editing does not write hardware. The footer distinguishes unsaved edits from settings
sent to the mouse. Invalid macros are shown inline and cannot be saved/applied.
Closing or loading another file asks before discarding unsaved edits.

For an offline editor/preview (no device operations):

```sh
./pulsar3-gui --offline
```

DPI: 1–6 stages, 200–12000 in steps of 100. Polling: 125/250/500/1000 Hz.
Lighting: `off`, `static`, `breath`, `neon`, `wave`, `press`, `horse-race`.
Brightness and speed: 0–4. Colors: eight `#RRGGBB` strings.

Button names: `left`, `right`, `middle`, `forward`, `back`, `dpi`.
Named actions include these mouse buttons, `double-click`, `dpi-up`, `dpi-down`,
`dpi-cycle`, `dpi-lock`, `disabled`, `media-player`, `next-track`, `previous-track`,
`stop`, `mute`, `play-pause`, `volume-up`, and `volume-down`.

A keyboard shortcut uses a USB HID keyboard usage and modifier bitmask. For Ctrl+C:

```json
"back": {"key": 6, "modifiers": 1}
```

Modifier bits: left Ctrl=1, Shift=2, Alt=4, Super=8; right equivalents=16/32/64/128.
A raw original-app action can be expressed as `{"ui_key": [type, byte1, byte2, byte3]}`;
these are UI-format bytes, converted to the firmware format by the tool. At least
one of the six physical buttons must remain assigned to ordinary left-click.

Example macro definition (inside `macros`) and binding:

```json
{
  "slot": 4,
  "repeat": 1,
  "events": [
    {"key": 4, "action": "down", "delay_ms": 50},
    {"key": 4, "action": "up", "delay_ms": 10}
  ]
}
```

```json
"back": {"macro": 4, "mode": "once"}
```

That macro taps the USB key usage for A. Modes are `once`, `toggle`, `hold`.
There are 12 macro slots (0–11), 128 bytes per macro including its header/terminator.
Delays are in 10 ms increments; extended delays use 20 ms resolution, matching the
original software. Every key-down must be paired with key-up; the last event uses
10 ms. Macro mouse codes are 240–244. Macro uploads precede button assignments.

## Development

```sh
python -m unittest discover -s tests -v
# With an accessible graphical session; never writes device settings:
python tools/gui_smoke.py
```

See `PROTOCOL.md` for packet formats and executable addresses. `research/` contains
local proprietary extraction/decompilation artifacts for investigation, not a
redistributable copy of the Windows application. Runtime code is in `pulsar3/`.
The original installer and ZIP have not been modified.
