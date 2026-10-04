# HATOR Pulsar 3 — Linux user guide

This guide describes your **HATOR Pulsar 3 (`379a:3910`)** and the native Linux configurator we built for it. It covers the current interface and the functions recovered from your Windows software.

The configurator works directly over USB. It does not need Windows, Wine, a virtual machine, or replacement mouse firmware. These instructions apply to this particular HATOR model, not mice from the separate Pulsar Gaming Gears brand.

## 1. Open the configurator

Run:

```bash
/path/to/pulsar-linux/pulsar3-gui
```

Or:

```bash
cd /path/to/pulsar-linux
./pulsar3-gui
```

The application opens `~/.local/share/pulsar3/profiles/linux.json` (or its `XDG_DATA_HOME` equivalent). If it is absent, an old checkout’s `profiles/linux.json` is used when present; otherwise the bundled `pulsar3/data/default.json` provides the original application’s defaults. New saves use the user-data directory.

**Values in the editor come from a profile file. They are not a full reading of the settings currently inside the mouse.**

## 2. Linux device access

### Enable device access

Linux allows ordinary mouse movement and clicks without granting an application permission to configure the hardware. Configuration needs additional access.

When the application reports a permission error:

1. Connect the mouse.
2. Click **Device → Enable device access**.
3. Enter your password in the system authentication dialog.
4. The application grants your user account access to this mouse's configuration and status device files, then reads its status.

The application continues running as your normal user. Only the permission change uses administrator privileges. You do not need to launch the entire application with `sudo`.

### When to repeat it

Access is temporary. You may need to enable it again after unplugging the mouse, changing USB ports, or rebooting. Linux can assign different device paths when the mouse reconnects; the button discovers the current paths automatically.

No permanent udev rule or startup service has been installed. The tool does not detach the normal mouse/keyboard drivers.

### Requirements

| Component | Purpose |
|---|---|
| Linux and a USB connection to this mouse | Direct hardware communication |
| Python 3 | Application and command-line tool |
| PyGObject, GTK4 (4.10+), and libadwaita | Graphical interface |
| `pkexec`, a graphical authentication agent, and `setfacl` | The **Enable device access** button |
| Writable user data/state directories | Saving profiles and write history without changing installed application files |

Install these dependencies through your Linux distribution; see the README for Arch/Omarchy and Ubuntu commands. The command-line tool uses Python's standard library; the extraction and reverse-engineering tools are not runtime requirements.

The current tool expects exactly one matching mouse to be connected. Support for other HATOR models, multiple matching mice, Bluetooth, or wireless receivers has not been established.

## 3. Application interface

### Navigation

The dark interface uses a sidebar for **Buttons**, **DPI & polling**, **Lighting**, and **Macros**. The top bar opens **Configuration**, **Profiles**, and **Device**. **Advanced** opens the complete JSON profile.

| Page | Controls |
|---|---|
| Buttons | Click the mouse diagram or a button row, select an action category, configure the action, and click **Assign** |
| DPI & polling | Add/remove stages, edit stepped sliders or numeric values, select polling rate |
| Lighting | Choose an effect, brightness and speed, edit eight RGB swatches with color pickers or hex fields, select the active palette color |
| Macros | Create/duplicate/delete macros, edit/reorder events, add shortcuts, record keyboard input, and inspect validation/capacity |
| Profiles | Profile name, Save, Save as, Open JSON, Revert edits, and local profile list |
| Device | **Enable device access**, **Refresh status**, connection details and readback |
| Advanced | Edit JSON, then **Load JSON into editor**; **Reset JSON to current profile** discards unimported JSON edits |

The selected local profile and save/apply state remain visible. Editing a control does not send it to the mouse.

### Save, validate, and apply

| Control | Meaning |
|---|---|
| **Validate** | Validate the profile and build packets without hardware access |
| **Save profile** | Write the current profile to its local file; bundled defaults prompt for a new filename |
| **Apply to mouse** | Send the complete valid profile, then save the successfully submitted configuration to `~/.local/share/pulsar3/profiles/linux.json` |

**Save as** can duplicate a configuration under a new filename. **Open** only loads a file into the editor. **Revert edits** restores the last saved editor state. Closing or loading a different profile asks before discarding unsaved edits.

Apply remains unavailable until device access/status works. A failed transfer leaves the previous working profile file intact, but some hardware settings may already have changed. Restore access/connection and retry. Successful transfers verify only the fields available in device status.

### Advanced JSON

The graphical controls and JSON share one profile. JSON text is staged until you choose **Load JSON into editor**. Save/Apply are unavailable while JSON edits are waiting to be loaded. Invalid JSON does not replace the graphical profile. There is no need to manually copy graphical controls into JSON.

### Status versus editing

**Device → Refresh status** reads a snapshot of polling rate, active DPI stage, lighting mode, and speed. It does not replace editable profile values. These snapshots may become stale after unplugging or pressing the physical DPI button.

## 4. Physical buttons and scrolling

The configurator exposes **six physical buttons**:

| Button field | Physical control | Standard assignment |
|---|---|---|
| `left` | Left mouse button | Left-click |
| `right` | Right mouse button | Right-click |
| `middle` | Pressing the scroll wheel | Middle-click |
| `forward` | Forward side button | Forward navigation |
| `back` | Back side button | Back navigation |
| `dpi` | DPI button | Cycle through DPI stages |

Wheel rotation remains ordinary scrolling. The current interface does not expose separate remapping controls for scroll-up and scroll-down.

Any of the six buttons can be reassigned. The validator requires at least one physical button to remain assigned to ordinary left-click.

### Mouse actions

| Action | Intended behavior |
|---|---|
| `left`, `right`, `middle` | Corresponding mouse click |
| `forward`, `back` | Corresponding navigation button; the receiving application decides what it does |
| `double-click` | The original application's double-fire/double-click action |
| `disabled` | Disable that button's assigned action |

### DPI actions

| Action | Intended behavior |
|---|---|
| `dpi-up` | Move up through configured DPI stages |
| `dpi-down` | Move down through configured DPI stages |
| `dpi-cycle` | Cycle through the configured stages |
| `dpi-lock` | The original application's **Sniper Key** action; exact hold/release behavior and target DPI have not been verified |

The `dpi-lock` name is a label in our current tool, not a promise that it permanently locks DPI. There is no separate sniper-DPI setting in the interface.

### Media actions

Available actions are:

- `play-pause`
- `stop`
- `next-track`
- `previous-track`
- `mute`
- `volume-up`
- `volume-down`
- `media-player`

These send media-control commands. Their effect depends on the Linux desktop and the application receiving them. For example, `media-player` is not a configurable command for launching an arbitrary Linux program.

### Keyboard keys and shortcuts

A button can send a keyboard usage with a modifier combination. On **Buttons**, select **Keyboard shortcut**, choose a key and modifiers, and click **Assign shortcut**. The same action can be expressed in Advanced JSON.

For example, this assigns **Ctrl+C** to the Back button:

```json
"back": {"key": 6, "modifiers": 1}
```

Replace the `back` entry inside the profile's `buttons` object. The key number is a USB HID keyboard usage, not an ASCII code or Linux keycode. Usage `6` is the keyboard position for C; the active keyboard layout and receiving application still matter.

| Modifier | Bit value |
|---|---:|
| Left Ctrl | 1 |
| Left Shift | 2 |
| Left Alt | 4 |
| Left Super/Windows | 8 |
| Right Ctrl | 16 |
| Right Shift | 32 |
| Right Alt | 64 |
| Right Super/Windows | 128 |

Add distinct values to combine modifiers. Ctrl+Shift uses `3`; no modifier uses `0`.

A mouse-generated shortcut does not define a desktop shortcut by itself. For launching an application or running a Linux command, the corresponding key combination must be configured in the desktop environment separately.

### Advanced original-app actions

The JSON form below accepts an original-app action record:

```json
"back": {"ui_key": [0, 0, 243, 0]}
```

This example is ordinary Back. The four bytes use the original application's action format, which the tool converts to firmware format.

The recovered application also contains repeated-key/fire, grouped-key, and Windows shortcut action types. They do not all have friendly controls in our interface, and their hardware/Linux behavior is not fully tested. Their presence in the executable should not be treated as proof that every action works on this model.

## 5. DPI and polling rate

### DPI stages

| Setting | Supported by the current configurator |
|---|---|
| Number of active stages | 1–6 |
| DPI per stage | 200–12000 |
| DPI increment | 100 |
| X and Y sensitivity | The same value is written for both axes |

Use **Add stage**, the minus buttons, and each stage’s slider or numeric field. For example, a six-stage profile can contain:

```text
400, 800, 1000, 1200, 1600, 3200
```

The physical button assigned to `dpi-cycle` selects the active stage. With the example above, stage 2 corresponds to 800 DPI **if this profile has been applied**.

The live-status report exposes the stage number, not its actual DPI value. The old direct active-stage command found in the Windows program was ignored by this mouse, so the GUI does not offer a software “select active stage” control.

### Polling rate

| Rate | Nominal interval between reports |
|---|---:|
| 125 Hz | 8 ms |
| 250 Hz | 4 ms |
| 500 Hz | 2 ms |
| 1000 Hz | 1 ms |

Polling rate controls how frequently the mouse reports input. DPI controls movement sensitivity. Linux pointer speed and acceleration are separate desktop settings; this application does not change them.

## 6. Lighting

### Available modes

| Mode | Description |
|---|---|
| `off` | Disable lighting |
| `static` | Steady lighting |
| `breath` | Breathing/pulsing effect |
| `neon` | Original application's neon effect |
| `wave` | Original application's wave effect |
| `press` | Original application's press-reactive effect |
| `horse-race` | Original application's running/chasing effect |

The names come from the recovered software. Off and static were verified through device status; the exact animation, color selection, and behavior of every other effect have not been individually characterized.

### Lighting controls

| Control | Values | Meaning |
|---|---|---|
| Brightness | 0–4 | Five encoded brightness levels |
| Speed | 0–4 | Five effect-speed settings |
| Selected color | 0–7 | Index into the eight-color list |
| Colors | Exactly eight `#RRGGBB` values | RGB palette sent to the mouse |

Example palette:

```text
#ff0000, #0000ff, #00ff00, #ffff00, #00ffff, #ff00ff, #ff8000, #ffffff
```

Index `0` is the first color. Eight palette entries do **not** mean eight independently controllable physical lighting zones. Which colors and controls affect the display depends on the selected effect; the GUI does not offer individual LED addressing.

## 7. Macros

The original application has macro upload commands for **12 slots, numbered 0–11**, with **128 bytes per macro**. Our tool implements that format and provides a graphical editor and button assignment controls.

**Encoding has been checked against the original software, but actual macro playback on this mouse has not yet been functionally tested.** The precise interaction between repeat count and playback mode also needs hardware testing.

### Macro contents and limits

| Capability | Current support |
|---|---|
| Keyboard events | Key-down and key-up |
| Mouse button events | Encoded mouse button presses/releases |
| Delays | Between events |
| Repeat count | 1–65535 in the profile format |
| Storage | 128 bytes per slot, including header and ending |
| Short delays | 10 ms resolution |
| Extended delays | 20 ms resolution, following the original app |
| Maximum accepted event delay | 655350 ms |
| Last event delay | 10 ms |
| Key/button balance | Every press must have a matching release |

Storage capacity is measured in bytes, not a fixed number of actions. Longer delay encodings consume more space. A macro must contain at least two events.

### Graphical macro workflow

1. Open **Macros → New macro**. A new macro starts with an editable A-key tap.
2. Edit each event’s key, Press/Release action, and delay. Use arrows to reorder or × to remove an event.
3. **Add a key or shortcut** creates balanced down/up events with optional modifiers. The picker also contains mouse buttons.
4. Alternatively, choose **Record keyboard**, start recording, type your sequence, and press Escape to stop. **Use recording** replaces the selected macro’s events.
5. Check the byte meter and inline validation. Every press must have a release, and the final delay must be 10 ms.
6. On **Buttons**, choose a physical button, select **Macro**, choose the slot and playback mode, then **Assign macro**.
7. Save the profile and use **Apply to mouse** to upload it.

Recording happens only inside the focused dialog. Losing focus stops recording and adds releases for held keys. Desktop-reserved shortcuts may not reach the recorder. Use the manual picker for mouse events, Escape, or unsupported keyboard-layout symbols.

Deleting a macro restores buttons referencing it to their standard actions after confirmation. Macro names are currently slot labels (**Macro 1** through **Macro 12**).

There is no text-to-macro editor, pointer-movement path editor, or shell-command executor.

### Playback modes

| JSON mode | Meaning in the original application |
|---|---|
| `once` | Run once after pressing the assigned button |
| `toggle` | Repeat until a mouse button is pressed |
| `hold` | Repeat until the assigned button is released |

`toggle` is our label for the original app's “repeat until any button is pressed” mode. It should not be assumed to mean that only pressing the same button stops playback.

### Example: assign an A-key tap to Back

Add this object to the profile's `macros` array:

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

Then replace the Back entry in `buttons` with:

```json
"back": {"macro": 4, "mode": "once"}
```

Here, key usage `4` is the A-key position. Slot `4` is a storage index, not a physical button number. The referenced slot must have a definition in the same profile. The tool uploads macros before applying button bindings.

Only six physical buttons are exposed, and at least one must retain left-click. Twelve storage slots therefore do not mean twelve independently accessible physical macro buttons.

## 8. Profiles

### What a profile contains

A JSON profile contains:

- A name and format version.
- Polling rate.
- DPI stages.
- Lighting effect, brightness, speed, palette, and color selection.
- Assignments for all six physical buttons.
- Any macro definitions used by those assignments.

You can save as many profile files as you need. There is no small fixed limit imposed by the application on the number of files.

### Possible profile arrangements

These are examples of how to organize files, not built-in presets:

| Profile | Possible setup |
|---|---|
| Everyday | Preferred DPI, standard navigation buttons, steady lighting |
| Gaming | A short DPI list, selected polling rate, simple button mappings |
| Work | Copy/Paste or other shortcuts on side buttons |
| Media | Playback or volume actions on side buttons |
| Lights off | Your normal settings with lighting disabled |

To switch, choose **Profiles → Open JSON**, select the file, and click **Apply to mouse**. Opening the file alone does not switch the hardware settings.

There is no automatic per-game switching, application detection, profile hotkey, or verified onboard profile-bank selector. The tool applies one configuration at a time.

### Files versus hardware memory

Profile files are local saved configurations. They are not complete backups read from the mouse. Independent onboard profile banks and persistence of all settings after power loss have not been verified.

The app sends configuration commands rather than continuously implementing button actions in the background. It does not need to keep sending the profile after Apply, but retain the file so you can reapply it after reconnecting if needed.

The GUI updates `~/.local/share/pulsar3/profiles/linux.json` after a successful hardware transfer. Saving a file separately does not apply it, and a complete hardware readback is unavailable.

## 9. Live status and verification

| Information | Read directly from the mouse? |
|---|---|
| Polling rate | Yes |
| Active DPI stage number | Yes |
| Lighting mode | Yes |
| Lighting speed | Yes |
| DPI values for each stage | Not established |
| Brightness | Not established |
| RGB palette | Not established |
| Button assignments | Not established |
| Macro contents | Not established |

Native communication works, and polling/lighting changes were verified by changing settings and reading the changed status back. DPI and standard button configuration transfers completed successfully. Their full values cannot currently be read back for independent comparison.

Packet construction was checked against the Windows application, including 288 button conversion cases and 21 macro encoding cases. Those checks establish matching data formats, not functional proof for every possible mouse action.

## 10. Command-line use

Run commands from the project directory:

```bash
cd /path/to/pulsar-linux
```

| Command | Purpose |
|---|---|
| `python -m pulsar3 detect` | Identify the mouse and its current device paths |
| `python -m pulsar3 status` | Read live status |
| `python -m pulsar3 probe` | Read USB report descriptors and status |
| `python3 -m pulsar3 plan ~/.local/share/pulsar3/profiles/linux.json` | Validate a profile and preview its packets |
| `python3 -m pulsar3 apply ~/.local/share/pulsar3/profiles/linux.json` | Preview only; does not write settings |
| `python3 -m pulsar3 apply ~/.local/share/pulsar3/profiles/linux.json --commit` | Apply the profile |

The same Linux device permissions are required for hardware access from the CLI. You can use **Enable device access** in the GUI first.

### Apply selected groups

For example, write only DPI data:

```bash
python3 -m pulsar3 apply ~/.local/share/pulsar3/profiles/linux.json --sections dpi --commit
```

Or lighting-related groups:

```bash
python3 -m pulsar3 apply ~/.local/share/pulsar3/profiles/linux.json --sections parameters,colors --commit
```

| Group | Fields written |
|---|---|
| `parameters` | Polling rate, stage count, lighting mode, brightness, speed, selected color |
| `dpi` | DPI stage data |
| `colors` | RGB palette |
| `buttons` | Button assignment block |
| `macros` | Macro definitions supplied in the profile |

These groups reflect the device's command format. `parameters` includes polling and stage count even if your intention is only to change lighting. The input file must still be a complete valid profile. Include `macros` when applying button bindings that reference macros.

Write records in `~/.local/state/pulsar3/history/` contain the requested profile, completed transfer groups, and available before/after status. They are diagnostic records, not full device backups or an automatic rollback mechanism.

## 11. Troubleshooting

| Problem | What to do |
|---|---|
| Permission denied | Click **Device → Enable device access** and authenticate |
| Worked before unplugging, then stopped | Enable access again; USB and hidraw paths may have changed |
| Mouse not found | Check the USB connection and that this is the `379a:3910` model |
| More than one matching mouse found | Leave only one connected while configuring |
| A field changed but the mouse did not | Click **Apply to mouse** and check its result |
| Opened another profile but behavior stayed the same | Opening loads the editor; Apply sends it |
| JSON edits are pending | Choose **Load JSON into editor**, or **Reset JSON to current profile** to discard them |
| Device or resource busy | Close other configuration instances and try again |
| No status response | Reconnect, enable access again, and retry; the tool requires status before applying a profile |
| Media key or shortcut does nothing | Check the target application's behavior and Linux desktop keybindings |
| Cannot remove left-click | Keep one physical button assigned to `left`; this is a validator requirement |
| Macro rejected | Check slot references, matching down/up events, delay values, and the 128-byte limit |

## 12. Functions not currently provided

- Firmware updates or firmware replacement.
- A complete hardware-settings backup/restore reader.
- Verified onboard profile-bank switching.
- Automatic per-application profiles.
- A verified software control for selecting the active DPI stage.
- Separate X/Y DPI controls.
- Remapping wheel rotation.
- Individual LED-zone control.
- Debounce, lift-off distance, angle snapping, or motion-sync controls.
- Linux pointer acceleration, pointer speed, scrolling behavior, or double-click timing controls.

Some generic functions exist in the vendor application's shared code for other devices. They are not automatically abilities of this mouse. This guide lists what our current tool exposes and identifies what remains unverified.

## Reference files

- [README](README.md): quick start and development commands.
- [Protocol notes](PROTOCOL.md): command formats and reverse-engineering evidence.
- Current GUI profile: `~/.local/share/pulsar3/profiles/linux.json` (respects `XDG_DATA_HOME`). Successful Apply saves here; Save can also update it.
- [Original application defaults](pulsar3/data/default.json): shipped defaults, not a device backup.
