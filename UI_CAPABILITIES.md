# HATOR Pulsar 3 — UI design capabilities

This is a capability reference for the Linux mouse configurator, based on the native backend we built for the HATOR Pulsar 3 (`379a:3910`). It describes what a new interface can expose, what needs additional application code, and what still needs hardware verification. It does not require keeping the current GTK layout.

## Capability labels

- **Verified:** native communication or the stated behavior has been checked on this mouse.
- **Implemented, testing needed:** the backend can encode/send the setting, but its complete physical behavior has not been verified. These features can be designed now, but need testing before being presented as fully supported.
- **Application work:** feasible as a Linux application feature; not currently implemented and not a newly discovered mouse feature.
- **Unsupported/unknown:** no working implementation or sufficient hardware evidence. Do not promise these controls in the initial UI.

Matching the Windows application's packet format is useful evidence, but does not prove every action works on this mouse.

## Suggested navigation

| Area | Main contents |
|---|---|
| Device | Connection, access permission, last-read device status |
| Buttons | Mouse diagram with six selectable buttons and an action editor |
| Sensitivity | DPI stages and polling rate |
| Lighting | Effect, brightness, speed, and color palette |
| Macros | Macro library, event editor, capacity, playback settings |
| Profiles | Local configurations, import/export, save and apply |

Keep the selected profile and pending-change state visible across these areas. A persistent **Apply to mouse** action is a good fit because editing and writing are separate operations.

The redesigned Python/GTK4 interface now implements these areas, plus an Advanced JSON editor. The backend remains separate from the layout.

## Buttons

### Physical controls

| Control | Can be reassigned? | Default action |
|---|---|---|
| Left button | Yes | Left-click |
| Right button | Yes | Right-click |
| Wheel click | Yes | Middle-click |
| Forward side button | Yes | Forward navigation |
| Back side button | Yes | Back navigation |
| DPI button | Yes | Cycle DPI stages |
| Wheel rotation | No supported remapping | Ordinary scrolling |

Use six hotspots on the mouse illustration. Do not offer scroll-up/down as additional programmable buttons.

The current validator requires **at least one physical button assigned to ordinary left-click**. It does not have to be the original left button. Show a clear validation error if a profile removes the last left-click assignment.

### Action picker

| Category | Choices | Readiness |
|---|---|---|
| Mouse | Left, right, middle, forward, back | Encoding implemented; standard configuration has been sent successfully |
| Mouse | Double-click/double-fire | Implemented, testing needed |
| DPI | Up, down, cycle | Implemented; physical stage changes have been observed, individual alternative assignments need testing |
| DPI | Sniper action | Implemented, exact behavior needs testing; backend name is `dpi-lock` |
| Keyboard | A key plus optional Ctrl, Shift, Alt, Super modifiers | Implemented, testing needed |
| Media | Play/pause, stop, next, previous, mute, volume up/down, media player | Implemented, testing needed; Linux application handling also matters |
| Macro | Select a macro and playback mode | Implemented, testing needed |
| Disabled | No assigned action | Implemented, testing needed |

A friendly key/shortcut picker is **implemented** over the existing JSON capability. The backend expects USB HID keyboard usages, not characters or Linux keycodes. Include left/right modifier distinctions in an advanced view if needed. Keyboard layout can affect the resulting character.

Do not describe the sniper action as a verified temporary switch to a configurable DPI: neither its exact behavior nor a separate sniper-DPI parameter is established.

Launching a Linux application or shell command is not a known onboard action. It could be offered later through a desktop shortcut or a background helper, which would be a separate Linux integration.

## Sensitivity and polling

| Setting | UI control | Allowed values | Readiness |
|---|---|---|---|
| DPI stages | Add/remove stage cards | 1–6 stages | Implemented; configuration transfer succeeded |
| Stage DPI | Number field or stepped slider | 200–12000, steps of 100 | Implemented; no DPI-value readback |
| Polling rate | Segmented choice or dropdown | 125, 250, 500, 1000 Hz | Verified setting/status round trip |
| Active stage | Read-only indicator | Reported stage number | Verified readback |

The same DPI is written for X and Y. Do not offer separate axis controls in the initial UI.

The mouse's DPI button can switch stages. A recovered software command for selecting the active stage was ignored by this mouse, so **clicking a stage card must not imply that it activates that stage on the device**. Cards can select a stage for editing.

The device reports the active stage number, not its DPI value. If the UI shows a derived value, label its source: for example, “Stage 2 · 800 DPI in this profile.” Do not claim it is measured or read from the mouse.

Linux pointer speed and acceleration are separate OS settings, not these hardware controls.

## Lighting

| Setting | Allowed values | Suggested control | Readiness |
|---|---|---|---|
| Effect | Off, static, breath, neon, wave, press, horse-race | Effect cards or dropdown | Off/static status verified; remaining animations need testing |
| Brightness | 0–4 | Five-step slider | Implemented, testing needed |
| Effect speed | 0–4 | Five-step slider | Encoded and read in status; visual behavior needs testing |
| Palette | Exactly eight RGB colors | Eight editable swatches | Implemented, testing needed |
| Selected color | Palette index 0–7 | Select a swatch | Implemented, testing needed |

Display palette positions as 1–8 if desired and convert to backend indices 0–7. Store colors as `#RRGGBB`.

Eight colors are a palette, **not eight independently addressable lighting zones**. Avoid a mouse illustration with eight independently editable LEDs.

The exact relationship between each effect, speed, brightness, and palette has not been fully characterized. Until tested, do not invent effect-specific restrictions or promise an exact animated preview. A preview can be labeled illustrative.

## Macros

A graphical editor is feasible because macro encoding and upload already exist. **Actual playback still needs testing on the mouse.** The app now includes a graphical event editor, shortcut builder, and focused keyboard recorder.

### Editor scope

| Feature | Backend capability / design implication |
|---|---|
| Device slots | 12, numbered 0–11; UI can show 1–12 |
| Events | Keyboard and encoded mouse-button press/release |
| Delay | Per event; integer multiples of 10 ms accepted |
| Long delays | Encoded at 20 ms resolution; show the effective encoded delay if rounding occurs |
| Maximum event delay | 655350 ms accepted by current validation |
| Final event | Must have a 10 ms delay |
| Repeat count | 1–65535 in the encoded format |
| Minimum macro | Two events |
| Capacity | 128 bytes per device slot, including header and ending |
| Validation | Matching presses/releases; no duplicate press without release; capacity check |
| Assignment | Bind a defined slot to a physical button |

Show a **bytes-used indicator**, not a fixed “maximum actions” count. Longer delay encodings use more bytes. A friendly “tap key” editor can generate a down/up pair internally.

### Playback choices

| UI wording | Backend mode | Evidence |
|---|---|---|
| Play once | `once` | Original application's meaning; playback untested |
| Repeat until a mouse button is pressed | `toggle` | Original application's meaning; playback untested |
| Repeat while held | `hold` | Original application's meaning; playback untested |

Do not simplify the second option to “press the same button to stop”; the recovered description says any button. Repeat-count interaction with these modes also needs testing.

The same profile must contain definitions for the macro slots its buttons reference. Uploads happen before button assignments.

Twelve slots do not mean twelve physical triggers: there are six buttons and the current validator reserves at least one ordinary left-click assignment.

### Additional macro UI we can build

- **Event list editor, reorder, duplicate, delete:** implemented using the existing macro format.
- **Local named macro library and import/export:** application work; the local library need not be limited to twelve entries, but a device configuration is.
- **Recording inside the focused editor:** implemented with common-key translation, balanced releases, delay quantization, and capacity validation. It stops on Escape or focus loss.
- **Global recording outside the app:** separate Linux/Wayland integration and permission investigation; not an existing capability.
- **Text-to-key sequences:** application work with explicit keyboard-layout limitations; not arbitrary Unicode text playback supported by the mouse.

Do not offer pointer paths, arbitrary scripts, conditional logic, or shell execution as onboard macro features.

## Profiles

Profiles are **local configuration files**, not verified onboard profile banks. Each contains polling rate, DPI stages, lighting, six button assignments, and macro definitions.

| Feature | Readiness |
|---|---|
| Open/save JSON profiles | Already implemented |
| Apply one profile to the mouse | Already implemented |
| Any number of local profile files | Supported; no small application-imposed file limit |
| Profile list, name editing, duplication through Save as | Implemented |
| File deletion and profile search | Additional application work |
| Presets such as Work, Gaming, Media, Lights off | Application work; ordinary profiles, not extra mouse modes |
| Automatic per-app switching | Application work plus desktop integration; requires a running helper and careful switching behavior |
| Global shortcut to apply a profile | Application work plus desktop integration |
| Onboard bank selector / next onboard profile button | Unsupported/unknown |
| Guaranteed persistence of every setting across power loss | Not verified |

**Open**, **Save**, and **Apply** must have distinct meanings:

- Open loads a profile into the editor.
- Save writes a local file.
- Apply sends the configuration to the mouse.

The GUI tracks saved and applied states separately. Successful Apply saves the working profile after the transfer. Ordinary Save never writes hardware, and failed transfers can leave partially applied hardware settings.

## Linux connection and access flow

Configuration requires permission to access USB and status device nodes. Normal mouse movement and clicking do not need this extra configuration permission.

### Device states to design

| State | UI behavior |
|---|---|
| No supported mouse connected | Show connection instructions; allow offline profile editing |
| More than one matching mouse | Explain that the current backend expects exactly one |
| Connected, access required | Show **Enable device access** |
| Authentication in progress | Show pending state; prevent duplicate permission requests |
| Authentication canceled or denied | Keep access action available and show a clear result |
| Ready | Enable status reads and hardware Apply |
| Applying | Show activity and prevent concurrent writes |
| Disconnected during operation | Preserve edits and show the interrupted result |
| Transfer failed | Report failure; settings may have been partly applied |
| Status read failed | Show unavailable/stale status, not invented current values |

The implemented **Enable device access** action opens the system password dialog through `pkexec` and grants the current user temporary access with `setfacl`. The whole GUI stays unprivileged. Never ask the user to type their password into a custom app text field.

Access may need to be enabled again after unplugging, changing ports, or rebooting. Device paths are discovered dynamically. No permanent udev rule has been installed.

Persistent access could be added later through an explicitly installed device-specific permission rule. That is **additional system integration**, not an existing toggle. The ordinary settings UI should not depend on being run as root.

Current runtime: Linux USB access and Python 3; the existing GUI also uses GTK4/PyGObject. The permission action requires `pkexec`, a working graphical authentication agent, and `setfacl`. Windows, Wine, and a VM are unnecessary.

## Device status versus profile values

This distinction should be visible in the design.

| Value | Device readback available? |
|---|---|
| Polling rate | Yes |
| Active DPI stage number | Yes |
| Lighting effect | Yes |
| Lighting speed | Yes |
| DPI values | No established readback |
| Brightness and RGB palette | No established readback |
| Button assignments | No established readback |
| Macro contents | No established readback |

Show editable values as **profile settings**. Show available hardware observations separately as **last-read device status**, ideally with a refresh action and timestamp. The current GUI reads snapshots; automatic refresh would be application work.

There is no full “Import current settings from mouse” or “Back up mouse” capability. Likewise, “Reset to defaults” can mean applying the bundled default profile, but must not be called a verified firmware factory reset.

A successful transfer can be reported as “Configuration sent.” Only the fields actually available in status can be compared afterward. Avoid a blanket “All settings verified” message.

## Applying changes and recovery

For an initial design, use an explicit **Apply profile** button and let users edit offline. Dirty-state indicators and revert-to-last-saved are implemented. Multi-step local undo remains additional application work.

The backend can apply groups, but the groups do not exactly match UI pages:

| Protocol group | Includes |
|---|---|
| Parameters | Polling rate, stage count, lighting mode, brightness, speed, selected color |
| DPI | DPI stage data |
| Colors | RGB palette |
| Buttons | All six assignments |
| Macros | Supplied macro definitions |

A “lighting only” write may also write polling rate and stage count because these share the parameters command. The backend still validates a complete profile. A per-page Apply feature needs deliberate handling of these dependencies; it is not simply one independent command per slider.

Writes are not an atomic transaction. If communication fails, some groups may already have changed. Keep the user's profile and offer a retry after access/connection is restored. Local history records are useful diagnostics but are not full hardware backups or guaranteed rollback.

## Exclude from the initial design

There is no established support for:

- Firmware update or replacement.
- Battery level, charging, Bluetooth, or receiver management for this implementation.
- Independently addressable LED zones.
- Wheel-rotation remapping.
- Separate X/Y DPI controls.
- Software selection of the active DPI stage.
- Debounce, lift-off distance, angle snapping, or motion sync.
- Full settings readback, onboard profile-bank management, or firmware factory reset.

Linux pointer acceleration, pointer speed, scroll behavior, desktop shortcuts, and automatic profile switching could belong to a later **OS integration** area. They require separate implementation and should not be advertised as already supported mouse firmware settings.

## Implemented interface

The six main areas, persistent access indicator, selected local profile, pending changes, and Apply action are now implemented. Graphical shortcut and macro editors are available. Untested actions/effects and macro playback remain identified as experimental; implementing their editors does not establish hardware behavior.

For detailed JSON examples and command-line operation, see [USER_GUIDE.md](USER_GUIDE.md). For packet formats and evidence, see [PROTOCOL.md](PROTOCOL.md).
