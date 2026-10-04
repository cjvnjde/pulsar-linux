# Protocol evidence: HATOR Pulsar 3, 379a:3910

Source: local `Pulsar 3 Software_20250227.exe`, extracted with upstream innoextract
master built locally. Application: `HATOR_Pulsar3_Software.exe`, 32-bit MinGW/Qt4.
`modules/setting/apConfig.bin`: IC571, sensor3327, DPI base100, minimum200,
maximum12000, reportLength64, encryption false. Do not confuse this with
Pulsar Gaming Gears devices.

## Transport

Device has three USB HID interfaces:

| Interface | Role | Endpoint |
|---|---|---|
| 0 | Standard pointing device | 0x81 IN |
| 1 | Keyboard/media and vendor status report 5 | 0x82 IN |
| 2 | Vendor configuration, usage page/usage FF00 | 0x03 OUT, 64 bytes |

On this Linux host interface 2 has no kernel driver and no hidraw node. Its 28-byte
report descriptor was read and saved in `research/hardware-probe.json`. It declares
an eight-byte feature report and a 64-byte output report, with no report IDs.

Use USBFS on the matching `/dev/bus/usb/BBB/DDD`, claiming only interface 2.
Feature command: class/interface control transfer, bmRequestType=0x21,
bRequest=SET_REPORT (9), wValue=0x0300, wIndex=2, length=8.
Windows HIDAPI buffers include a leading zero report ID (nine bytes); Linux sends
the remaining eight bytes on the control endpoint. Output data is sent in 64-byte
interrupt OUT chunks to endpoint 3, without that artificial report-ID byte.
The USBFS bulk ioctl can transfer to this interrupt endpoint; tested on the device.

Original common sender `0x404e80`: send 9-byte HIDAPI feature report, wait helper,
then 65-byte HIDAPI output buffers (zero ID + 64 payload), 20 ms between chunks.
Wait helper `0x404780` effectively sleeps about 10 ms. No encryption for this model.
No reset or kernel-driver detach is needed.

## Commands (headers below include the artificial report ID)

| Operation | Header | Data | Original function |
|---|---|---|---|
| Status sync | `00 80 00 00 00 00 00 00 7f` | none | 0x407450 |
| Parameter 0 | `00 02 PP 00 00 00 00 01 00` | 64 bytes | 0x405b60 |
| Parameter 1 | `00 03 00 00 00 00 MM 03 00` | 192 bytes | 0x405860 |
| Macro upload | `00 04 00 SS 00 00 00 00 00` | 128 bytes | 0x405560 |

PP is the app profile number (tool uses 0). MM is a selective update mask:
1=DPI, 2=RGB colors, 4=button mappings. SS is macro slot 0–11.
Parameter/macro headers have zero final byte, **not** the legacy checksum.
The legacy checksum helper 0x404820 returns the one's complement of seven bytes.

`research/reference-packets.json` records original packet builders executed with
Unicorn, stopping at the sender *before any hardware I/O*. Reproduce with
`tools/reference_packets.py` (requires pefile/unicorn; not runtime dependencies).

## Parameter 0

First six bytes are copied from the UI by `0x40f7e0`; all remaining bytes are zero.

| Offset | Meaning |
|---|---|
| 0 | Poll interval: 8=125 Hz, 4=250, 2=500, 1=1000 |
| 1 | Number of DPI stages |
| 2 | Light mode: 0 off, 1 static, 2 breath, 3 neon, 4 wave, 5 press, 7 horse-race |
| 3 | Brightness: UI step 0–4 multiplied by 63 |
| 4 | Speed: UI step 0–4 mapped to 1,3,4,5,7 |
| 5 | Selected RGB color index |

Source: recovered `main.qml::o_saveData0`, `LightControl.qml`, English strings.
Hardware roundtrip verified in `research/parameters-roundtrip.json`.

## Parameter 1

Source: `main.qml::o_saveData1`, then button transformation in `0x412aa0`.
All fields not listed are zero, as in the original app.

| Offset | Meaning |
|---|---|
| 4 | DPI stage count |
| 9–24 | Eight little-endian uint16 X DPI values (inactive slots still supplied) |
| 25–40 | Same values for Y |
| 88–111 | Eight RGB triplets |
| 128–191 | Sixteen four-byte firmware button records |

Physical buttons are the first six entries: left, right, middle, forward, back,
DPI. Remaining records match the shipped configuration. The original UI presents
six DPI stages, though the protocol block reserves eight. This tool respects the
model's six-stage UI limit. Independent DPI measurement/button event validation
has not yet been performed; do not label successful USB writes as full readback.

Button conversion was verified by executing the original loop at 0x412de2 through
0x412e8e for 288 inputs. Fixtures: `research/reference-keys.json`.

## Macros

Macro body has a little-endian uint16 repeat count (the C++ layer swaps the
big-endian bytes initially produced by QML). Short events contain delay-in-10ms
(low seven bits, minimum1; high bit set for key-up), followed by the key usage.
Long delays contain `[release_flag, key, 0, 1, ticks20ms_hi, ticks20ms_lo]` within
the range exposed by this tool. Finish with a final event delayed 10ms and `00 00`;
pad to 128 bytes. Source: `MacroEditor.qml::deCode`, `0x40f610`, `0x405560`.
21 vectors, including the 127-tick boundary and multi-byte repeat counts, were
compared with the original embedded JavaScript. This verifies encoding, not
physical macro execution.

## Live status / readback limitations

Read hidraw for interface 1; ignore and do not log any report other than seven-byte
vendor report `05 00 RR DD LL SS TT`:
RR=poll interval; DD=zero-based DPI stage; LL=light mode; SS=speed code;
TT=event discriminator (FF for full sync). Parser grounded in the original receiver
at 0x40a3d0 and `main.qml::syncFwReport`.

Observed initial/restored status: `05 00 01 01 00 07 ff`.
Test status: `05 00 02 01 01 01 ff` (500 Hz, static, slow).

Full DPI values, brightness, colors, button definitions and macro contents are not
in this status. A plain GET_REPORT returned `80 06 01 03 0a 06 00 00`; its meaning
has not been established and it is not used as a backup.

The executable contains older IC553/IC560 functions, including full profile reads.
Their presence does not establish applicability to IC571. In particular, legacy
active-stage `0B` was tried, did not change live status, and is not exposed in the UI.
No speculative read/write opcodes, firmware flashing or hardware resets are used.

## Host-side DPI-linked lighting

`pulsar3/dpi_lighting.py` polls the existing status sync command roughly every
0.5 seconds while the GUI runs. After a successful Apply, an optional
`dpi_lighting` profile object supplies an `enabled` boolean and one `#RRGGBB`
color per DPI stage. It is host metadata; ordinary `plan`/CLI Apply packets are
unchanged, and no new firmware opcode or onboard association is assumed.

At startup after Apply, the follower establishes static mode and selected-color
index 0 using Parameter 0, preserving polling rate, stage count, brightness and
speed from the applied snapshot. It then writes the active stage’s RGB value
into palette slot 0 using Parameter 1 with **mask 2 only**. Subsequent stage
changes use only this palette command. The other seven palette entries retain
their normal profile values. An unchanged color causes no configuration write.
DPI values, button assignments and macros are never sent by the follower.

Hardware check on 2026-10-04: sending Parameter 0 on every color change caused
the active DPI stage to return to stage 2. Using palette-only updates instead
allowed the physical button to cycle through all six stages without that reset.
The user confirmed visible color changes. Keep Parameter 0 out of the stage-change
path; even an otherwise identical parameters write has this firmware side effect.
Full Apply (including the initial lighting setup) can still reset the active stage.

The worker shares a transaction lock with GUI Apply/status/access operations,
releases interface 2 between polls, and ignores stale profile revisions. Device
errors, invalid stages or unexpected polling/lighting status disarm it until
another successful Apply. It does not automatically resume after reconnecting,
because the mouse cannot provide a full profile readback. Disabling linking and
applying restores the ordinary lighting configuration. Closing leaves the last
color selected. Colors themselves remain unavailable in readback.
