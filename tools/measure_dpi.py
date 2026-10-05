"""Measure sensor DPI over a known horizontal distance, without changing settings.

Reads only this mouse's pointing interface; no keyboard reports or raw input logs.
Run from the checkout: sudo python3 tools/measure_dpi.py --distance-cm 5
"""
import argparse
import json
import math
import os
from pathlib import Path
import select
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pulsar3.transport import Mouse, discover

# Verified wired 379a:3910 descriptor: no report ID, one button byte, signed
# 16-bit X/Y, vertical and horizontal wheel bytes.
POINTING_DESCRIPTOR = bytes.fromhex(
    '05 01 09 02 a1 01 09 01 a1 00 05 09 15 00 25 01 19 01 29 05 '
    '75 01 95 05 81 02 95 03 81 01 05 01 16 01 80 26 ff 7f 09 30 '
    '09 31 75 10 95 02 81 06 15 81 25 7f 09 38 75 08 95 01 81 06 '
    '05 0c 0a 38 02 95 01 81 06 c0 c0')


def motion(report):
    if len(report) != 7:
        raise RuntimeError('Unexpected pointing report length; measurement stopped')
    return struct.unpack_from('<hh', report, 1)


def measured_dpi(horizontal_counts, distance_cm):
    if not math.isfinite(distance_cm) or distance_cm <= 0:
        raise ValueError('Distance must be positive and finite')
    return abs(horizontal_counts) * 2.54 / distance_cm


def pointing_node(info):
    nodes = list(Path(info['sysfs']).glob('*:1.0/*/hidraw/hidraw*'))
    if len(nodes) != 1:
        raise RuntimeError('Expected one pointing interface for the HATOR mouse')
    descriptor = nodes[0].parent.parent / 'report_descriptor'
    if descriptor.read_bytes() != POINTING_DESCRIPTOR:
        raise RuntimeError('Pointing descriptor differs from the supported format')
    return '/dev/' + nodes[0].name


def read_stage():
    with Mouse() as mouse:
        return mouse.status()['dpi_stage']


def measure(fd, seconds):
    deadline = time.monotonic() + 0.05
    while time.monotonic() < deadline and select.select([fd], [], [], 0)[0]:
        os.read(fd, 64)
    x = y = reports = 0
    print(f'MOVE NOW: one straight pass, then hold still for {seconds:g} seconds.', flush=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
            break
        dx, dy = motion(os.read(fd, 64))
        x += dx; y += dy; reports += 1
    return x, y, reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distance-cm', type=float, default=5)
    parser.add_argument('--seconds', type=float, default=8)
    args = parser.parse_args()
    measured_dpi(0, args.distance_cm)
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 60:
        raise ValueError('Measurement time must be between 1 and 60 seconds')
    info = discover()
    node = pointing_node(info)
    fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
    try:
        print('This test reads raw mouse motion; it does not change mouse or desktop settings.')
        print('Select the desired DPI stage, then place the mouse at the start of a ruler.')
        print(f'After MOVE NOW, move it {args.distance_cm:g} cm horizontally in one pass.')
        print('Do not move it back or change stages during the timed measurement.')
        input('Press Enter when ready; keep the mouse still until MOVE NOW: ')
        stage_before = read_stage()
        x, y, reports = measure(fd, args.seconds)
        stage_after = read_stage()
    finally:
        os.close(fd)
    if stage_before != stage_after:
        raise RuntimeError('DPI stage changed during measurement; repeat the test')
    if not x:
        raise RuntimeError('No net horizontal movement measured; repeat one straight pass')
    print(json.dumps({'stage': stage_before, 'distance_cm': args.distance_cm,
                      'horizontal_counts': x, 'vertical_counts': y, 'reports': reports,
                      'measured_dpi': round(measured_dpi(x, args.distance_cm)),
                      'note': 'Accuracy depends on measured sensor travel; this is raw motion, before desktop acceleration.'}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, EOFError) as error:
        print(f'Measurement failed: {error}', file=sys.stderr)
        sys.exit(1)
