"""Host-side bottom RGB lighting, armed with a successfully applied profile.

The worker releases the mouse between polls and shares a transaction lock with
GUI device commands. Only the RGB palette and lighting parameters are written;
stable stages cause status reads, never repeated configuration writes.
"""
from copy import deepcopy
import threading

from .protocol import integer, plan
from .transport import Mouse


class DpiLightingSession:
    """One applied snapshot; independent of edits in the GUI."""
    def __init__(self, profile):
        plan(profile)
        self.profile = deepcopy(profile)
        if not profile.get('dpi_lighting', {}).get('enabled'):
            raise ValueError('DPI lighting is not enabled in this profile')
        self.colors = self.profile['dpi_lighting']['colors']
        self.last_stage = None
        self.setup_done = False
        lighting = self.profile['lighting']
        lighting['mode'] = 'static'
        lighting['selected_color'] = 0

    def _validate(self, status, check_lighting=True):
        # Firmware can retain a removed stage after reducing the stage count.
        # A real hardware stage outside the new mapping is not a corrupt report.
        stage = integer(status.get('dpi_stage'), 1, 8, 'Reported DPI stage')
        if status.get('polling_hz') != self.profile['polling_hz']:
            raise RuntimeError('Polling rate changed outside this profile. Apply the profile again to resume DPI colors.')
        if check_lighting and (status.get('lighting_mode') != 'static' or
                status.get('lighting_speed') != self.profile['lighting']['speed']):
            raise RuntimeError('Lighting settings changed or were not accepted. Apply the profile again to resume DPI colors.')
        return stage

    def setup_packets(self, status):
        self._validate(status, check_lighting=False)
        # Parameter 0 resets the active DPI stage on tested hardware. The worker
        # must read status again after this write, before choosing a color.
        return plan(self.profile, {'parameters'}) if not self.setup_done else []

    def setup_sent(self):
        self.setup_done = True

    def packets(self, status):
        stage = self._validate(status)
        if stage > len(self.colors):
            # Keep polling without guessing a color or writing configuration.
            return []
        if self.last_stage is not None and self.colors[stage - 1].lower() == self.colors[self.last_stage - 1].lower():
            return []
        # A single-slot update leaves other palette lookups showing unrelated
        # colors. Give every slot the active color while linking is enabled.
        self.profile['lighting']['colors'] = [self.colors[stage - 1]] * 8
        # The reserved DPI/button bytes in Parameter 1 are never applied.
        return plan(self.profile, {'colors'})

    def sent(self, stage):
        # Call only after every packet succeeded. On failure the worker disarms.
        self.last_stage = stage


class DpiLightingFollower:
    def __init__(self, device_lock, on_update, mouse_factory=Mouse, interval=0.5):
        self.device_lock = device_lock
        self.on_update = on_update
        self.mouse_factory = mouse_factory
        self.interval = interval
        self._state_lock = threading.Lock()
        self._wake = threading.Event()
        self._closed = threading.Event()
        self._paused = threading.Event()
        self._session = None
        self._revision = 0
        self._thread = None

    @property
    def revision(self):
        with self._state_lock:
            return self._revision

    def configure(self, profile=None):
        session = DpiLightingSession(profile) if profile and profile.get('dpi_lighting', {}).get('enabled') else None
        with self._state_lock:
            self._revision += 1
            self._session = session
            if session and not self._thread and not self._closed.is_set():
                self._thread = threading.Thread(target=self._run, name='pulsar-dpi-colors', daemon=True)
                self._thread.start()
        self._wake.set()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()
        self._wake.set()

    def close(self):
        self._closed.set()
        self._wake.set()
        # Let a bounded USB transaction finish and release interface 2.
        if self._thread:
            self._thread.join()

    def _current(self, revision):
        with self._state_lock:
            return (revision == self._revision and self._session is not None
                    and not self._paused.is_set() and not self._closed.is_set())

    def poll_once(self):
        """One serialized transaction. Also usable with a fake device in tests."""
        with self.device_lock:
            with self._state_lock:
                revision, session = self._revision, self._session
            if not self._current(revision):
                return
            try:
                with self.mouse_factory() as mouse:
                    status = mouse.status()
                    setup = session.setup_packets(status)
                    if not self._current(revision):
                        return
                    for packet in setup:
                        mouse.send(packet)
                    if setup:
                        session.setup_sent()
                        status = mouse.status()
                    packets = session.packets(status)
                    if not self._current(revision):
                        return
                    for packet in packets:
                        mouse.send(packet)
                    stage = status['dpi_stage']
                    mapped = stage <= len(session.colors)
                    if mapped:
                        session.sent(stage)
                    else:
                        session.last_stage = None
                update = {'status': status, 'stage': status['dpi_stage'],
                          'color': session.colors[stage - 1] if mapped else None,
                          'waiting_for_stage': not mapped, 'stage_count': len(session.colors),
                          'written': bool(setup or packets)}
            except (OSError, RuntimeError, ValueError) as error:
                with self._state_lock:
                    if revision != self._revision:
                        return
                    self._session = None
                update = {'error': str(error)}
            self.on_update(revision, update)

    def _run(self):
        while not self._closed.is_set():
            self._wake.wait(self.interval)
            self._wake.clear()
            if not self._closed.is_set():
                self.poll_once()
