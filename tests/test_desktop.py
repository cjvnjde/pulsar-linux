import unittest
from unittest.mock import patch

from pulsar3.desktop import device_access_command


class DesktopTests(unittest.TestCase):
    def test_access_uses_discovered_tools_and_keeps_paths_as_arguments(self):
        executables = {'pkexec': '/custom/bin/pkexec', 'setfacl': '/custom/bin/setfacl'}
        with patch('pulsar3.desktop.shutil.which', side_effect=executables.get), patch('pulsar3.desktop.os.getuid', return_value=1000):
            self.assertEqual(device_access_command(['/dev/bus/usb/001/005', '/dev/hidraw6']),
                             ['/custom/bin/pkexec', '/custom/bin/setfacl', '-m', 'u:1000:rw',
                              '/dev/bus/usb/001/005', '/dev/hidraw6'])

    def test_missing_authorization_tool_has_actionable_error(self):
        with patch('pulsar3.desktop.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'pkexec, setfacl'):
                device_access_command(['/dev/hidraw6'])
