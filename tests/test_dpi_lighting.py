from copy import deepcopy
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from pulsar3.dpi_lighting import DpiLightingFollower, DpiLightingSession
from pulsar3.protocol import MODES, POLLING, SPEEDS, plan

DEFAULT = Path(__file__).resolve().parents[1] / 'pulsar3/data/default.json'


class DpiLightingTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(DEFAULT.read_text())
        self.profile['dpi'] = [400, 800, 1600]
        self.profile['dpi_lighting'] = {'enabled': True, 'colors': ['#ff0000', '#00ff00', '#0000ff']}
        self.status = {'dpi_stage': 2, 'polling_hz': self.profile['polling_hz'],
                       'lighting_mode': 'static', 'lighting_speed': self.profile['lighting']['speed']}

    def test_old_profiles_and_host_metadata_have_identical_apply_packets(self):
        plain = deepcopy(self.profile); del plain['dpi_lighting']
        self.assertEqual(plan(plain), plan(self.profile))
        for mapping in (None, {}, {'enabled': 1, 'colors': ['#ff0000'] * 3},
                        {'enabled': True, 'colors': ['#ff0000'] * 2},
                        {'enabled': False, 'colors': ['#  0000'] * 3},
                        {'enabled': False, 'colors': ['#xx0000'] * 3},
                        {'enabled': True, 'colors': ['#ff0000'] * 3, 'unknown': 1}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                plan(dict(self.profile, dpi_lighting=mapping))

    def test_initial_color_palette_and_stage_selection_preserve_other_settings(self):
        original = deepcopy(self.profile)
        session = DpiLightingSession(self.profile)
        self.profile['dpi_lighting']['colors'][1] = '#abcdef'
        parameters, = session.setup_packets(self.status)
        colors, = session.packets(self.status)
        self.assertEqual(colors.header[1], 3)
        self.assertEqual(colors.header[6], 2)  # colors only, no DPI/buttons
        self.assertEqual(colors.payload[88:112], bytes.fromhex('00ff00') * 8)
        self.assertEqual(parameters.header[1], 2)
        self.assertEqual(parameters.payload[:6], bytes([
            POLLING[original['polling_hz']], 3, MODES['static'],
            original['lighting']['brightness'] * 63, SPEEDS[original['lighting']['speed']], 0]))
        self.assertEqual(self.profile['lighting'], original['lighting'])
        session.sent(2)
        session.setup_sent()
        self.assertEqual(session.setup_packets(self.status), [])
        self.assertEqual(session.packets(self.status), [])
        switched = session.packets(dict(self.status, dpi_stage=3))
        self.assertEqual(len(switched), 1)
        self.assertEqual(switched[0].header[1], 3)
        self.assertEqual(switched[0].header[6], 2)
        self.assertEqual(switched[0].payload[88:112], bytes.fromhex('0000ff') * 8)

    def test_invalid_stage_or_external_parameter_change_never_writes(self):
        session = DpiLightingSession(self.profile)
        for stage in (None, False, 0, 9):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                session.packets(dict(self.status, dpi_stage=stage))
        with self.assertRaises(RuntimeError):
            session.packets(dict(self.status, polling_hz=123))
        session.sent(2)
        with self.assertRaises(RuntimeError):
            session.packets(dict(self.status, lighting_mode='breath'))

    def test_reduced_stage_counts_wait_without_resetting_then_resume(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                self.profile['dpi'] = [400, 800, 1600][:count]
                self.profile['dpi_lighting']['colors'] = ['#ff0000', '#00ff00', '#ffff00'][:count]
                follower, mouse, updates = self.follower()
                mouse.status.return_value = dict(self.status, dpi_stage=6)
                follower.poll_once()
                self.assertEqual(mouse.send.call_count, 1)  # establish static mode once
                self.assertTrue(updates.call_args.args[1]['waiting_for_stage'])
                self.assertIsNone(updates.call_args.args[1]['color'])
                self.assertEqual(updates.call_args.args[1]['stage'], 6)
                for _ in range(5):
                    follower.poll_once()
                self.assertEqual(mouse.send.call_count, 1)
                self.assertNotIn('error', updates.call_args.args[1])
                mouse.status.return_value['dpi_stage'] = count
                follower.poll_once()
                self.assertEqual(mouse.send.call_count, 2)
                self.assertEqual(mouse.send.call_args.args[0].header[6], 2)
                self.assertFalse(updates.call_args.args[1]['waiting_for_stage'])
                self.assertEqual(updates.call_args.args[1]['color'], self.profile['dpi_lighting']['colors'][count-1])
                # Leaving a valid slot and returning must refresh the bottom color.
                mouse.status.return_value['dpi_stage'] = 6
                follower.poll_once()
                mouse.status.return_value['dpi_stage'] = count
                follower.poll_once()
                self.assertEqual(mouse.send.call_count, 3)

    def test_all_stage_changes_use_only_rgb_mask_and_identical_colors_skip_writes(self):
        self.profile['dpi'] = [400, 800, 1000, 1200, 1600, 3200]
        self.profile['dpi_lighting']['colors'] = ['#ff0000', '#0000ff', '#00ff00', '#ffff00', '#00ffff', '#ff00ff']
        session = DpiLightingSession(self.profile)
        session.packets(self.status); session.sent(2)
        for stage in (3, 4, 5, 6, 1, 2):
            packets = session.packets(dict(self.status, dpi_stage=stage))
            self.assertEqual(len(packets), 1)
            # Regression: Parameter 0 resets this mouse to stage 2. Never use it
            # to follow changes, nor use the DPI/button mask bits in Parameter 1.
            self.assertEqual(packets[0].header[1], 3)
            self.assertEqual(packets[0].header[6], 2)
            self.assertEqual(packets[0].payload[88:112], bytes.fromhex(session.colors[stage-1][1:]) * 8)
            session.sent(stage)
        session.colors[2] = '#0000FF'
        self.assertEqual(session.packets(dict(self.status, dpi_stage=3)), [])

    def follower(self):
        mouse = Mock()
        mouse.__enter__ = Mock(return_value=mouse)
        mouse.__exit__ = Mock(return_value=False)
        mouse.status.return_value = self.status.copy()
        updates = Mock()
        follower = DpiLightingFollower(threading.Lock(), updates, lambda: mouse)
        with patch('pulsar3.dpi_lighting.threading.Thread'):
            follower.configure(self.profile)
        return follower, mouse, updates

    def test_following_pause_resume_disable_and_stable_stage(self):
        follower, mouse, updates = self.follower()
        follower.pause(); follower.poll_once()
        mouse.status.assert_not_called()
        follower.resume(); follower.poll_once()
        self.assertEqual(mouse.send.call_count, 2)
        for _ in range(10): follower.poll_once()
        self.assertEqual(mouse.send.call_count, 2)
        mouse.status.return_value['dpi_stage'] = 1
        follower.poll_once()
        self.assertEqual(mouse.send.call_count, 3)
        self.assertEqual(updates.call_args.args[1]['color'], '#ff0000')
        follower.configure(); follower.poll_once()
        self.assertEqual(mouse.send.call_count, 3)

    def test_setup_reset_uses_fresh_stage_before_writing_color(self):
        follower, mouse, updates = self.follower()
        status = dict(self.status, dpi_stage=3, lighting_mode='breath')
        mouse.status.side_effect = lambda: status.copy()

        def firmware_send(packet):
            if packet.header[1] == 2:
                status.update(dpi_stage=2, lighting_mode='static')
            else:
                self.assertEqual(packet.header[6], 2)
                self.assertEqual(packet.payload[88:112], bytes.fromhex('00ff00') * 8)

        mouse.send.side_effect = firmware_send
        follower.poll_once()
        self.assertEqual(mouse.status.call_count, 2)
        self.assertEqual(mouse.send.call_count, 2)
        self.assertEqual(updates.call_args.args[1]['stage'], 2)
        self.assertEqual(updates.call_args.args[1]['status']['dpi_stage'], 2)
        self.assertEqual(updates.call_args.args[1]['color'], '#00ff00')
        follower.poll_once()
        self.assertEqual(mouse.send.call_count, 2)

    def test_setup_rejected_or_second_status_failed_never_writes_a_color(self):
        for after in (dict(self.status, lighting_mode='breath'), OSError('Mouse disconnected')):
            with self.subTest(after=after):
                follower, mouse, updates = self.follower()
                mouse.status.side_effect = [self.status, after]
                follower.poll_once()
                self.assertEqual(mouse.send.call_count, 1)
                self.assertEqual(mouse.send.call_args.args[0].header[1], 2)
                self.assertIn('error', updates.call_args.args[1])
                follower.poll_once()
                self.assertEqual(mouse.status.call_count, 2)

    def test_pausing_after_setup_prevents_stale_color_write(self):
        follower, mouse, _ = self.follower()

        def read_status():
            if mouse.status.call_count == 2:
                follower.pause()
            return self.status

        mouse.status.side_effect = read_status
        follower.poll_once()
        self.assertEqual(mouse.send.call_count, 1)
        self.assertEqual(mouse.send.call_args.args[0].header[1], 2)

    def test_disconnect_and_partial_write_failure_disarm_until_reapplied(self):
        for fail_at in ('status', 'second_write'):
            with self.subTest(fail_at=fail_at):
                follower, mouse, updates = self.follower()
                if fail_at == 'status': mouse.status.side_effect = OSError('Mouse disconnected')
                else: mouse.send.side_effect = [None, OSError('USB interrupted')]
                follower.poll_once()
                self.assertIn('error', updates.call_args.args[1])
                mouse.status.reset_mock(); mouse.send.reset_mock()
                follower.poll_once()
                mouse.status.assert_not_called(); mouse.send.assert_not_called()
                mouse.status.side_effect = None; mouse.send.side_effect = None
                follower.configure(self.profile); follower.poll_once()
                self.assertEqual(mouse.send.call_count, 2)

    def test_foreground_command_pausing_during_status_prevents_writes(self):
        follower, mouse, _ = self.follower()
        def pause_during_read():
            follower.pause()
            return self.status
        mouse.status.side_effect = pause_during_read
        follower.poll_once()
        mouse.send.assert_not_called()

    def test_replacing_profile_during_status_prevents_stale_writes(self):
        follower, mouse, _ = self.follower()
        replacement = deepcopy(self.profile)
        replacement['dpi_lighting']['colors'][1] = '#aabbcc'
        def replace_during_read():
            follower.configure(replacement)
            return self.status
        mouse.status.side_effect = replace_during_read
        follower.poll_once(); mouse.send.assert_not_called()
        mouse.status.side_effect = None
        follower.poll_once()
        self.assertEqual(mouse.send.call_args_list[1].args[0].payload[88:91], bytes.fromhex('aabbcc'))

    def test_serializes_with_foreground_transactions_and_stops_cleanly(self):
        lock = threading.Lock(); read = threading.Event(); written = threading.Event()
        mouse = Mock()
        mouse.__enter__ = Mock(return_value=mouse); mouse.__exit__ = Mock(return_value=False)
        mouse.status.side_effect = lambda: (read.set(), self.status)[1]
        mouse.send.side_effect = lambda _: written.set()
        follower = DpiLightingFollower(lock, Mock(), lambda: mouse, interval=0.01)
        try:
            with lock:
                follower.configure(self.profile)
                self.assertFalse(read.wait(0.05))
                follower.pause()
            self.assertFalse(read.wait(0.05))
            follower.resume()
            self.assertTrue(written.wait(1))
        finally:
            follower.close()
        self.assertFalse(follower._thread.is_alive())
        count = mouse.send.call_count
        follower.poll_once()
        self.assertEqual(mouse.send.call_count, count)


if __name__ == '__main__':
    unittest.main()
