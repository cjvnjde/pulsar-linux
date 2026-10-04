import importlib.util
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pulsar3.paths import DEFAULT_PROFILE, history_dir, profiles_dir, xdg_dir

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_release',ROOT/'tools/build_release.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class PackagingTests(unittest.TestCase):
    def test_xdg_paths_are_writable_locations_not_installation_paths(self):
        with patch.dict(os.environ,{'XDG_DATA_HOME':'/tmp/pulsar-test-data','XDG_STATE_HOME':'/tmp/pulsar-test-state'}):
            self.assertEqual(profiles_dir(),Path('/tmp/pulsar-test-data/pulsar3/profiles'))
            self.assertEqual(history_dir(),Path('/tmp/pulsar-test-state/pulsar3/history'))
        with patch.dict(os.environ,{'XDG_DATA_HOME':'relative'}):
            self.assertEqual(xdg_dir('XDG_DATA_HOME','.local/share'),Path.home()/'.local/share')
        self.assertTrue(DEFAULT_PROFILE.is_file())

    def test_archive_contains_runtime_and_excludes_personal_or_vendor_files(self):
        with tempfile.TemporaryDirectory() as directory:
            archive,deb,checksums=builder.build(Path(directory),'0.1.0',1700000000)
            first=(archive.read_bytes(),deb.read_bytes(),checksums.read_bytes())
            builder.build(Path(directory),'0.1.0',1700000000)
            self.assertEqual(first,(archive.read_bytes(),deb.read_bytes(),checksums.read_bytes()))
            with tarfile.open(archive) as package:
                names=package.getnames()
                self.assertIn('pulsar3-studio-0.1.0/pulsar3/data/default.json',names)
                self.assertIn('pulsar3-studio-0.1.0/pulsar3/assets/style.css',names)
                self.assertEqual(package.getmember('pulsar3-studio-0.1.0/pulsar3-gui').mode,0o755)
                self.assertFalse(any('/research/' in n or '/history/' in n or '/profiles/' in n for n in names))
            # Independently parse the standard ar container and inspect its payload.
            raw=deb.read_bytes();self.assertEqual(raw[:8],b'!<arch>\n');offset=8;members={}
            while offset<len(raw):
                header=raw[offset:offset+60];self.assertEqual(header[58:],b'`\n')
                name=header[:16].decode().strip().rstrip('/');size=int(header[48:58])
                members[name]=raw[offset+60:offset+60+size];offset+=60+size+(size%2)
            self.assertEqual(members['debian-binary'],b'2.0\n')
            with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as payload:
                self.assertIn('./usr/bin/pulsar3-gui',payload.getnames())
                directory=payload.getmember('./usr/lib/pulsar3-studio/pulsar3')
                self.assertTrue(directory.isdir())
                self.assertLess(payload.getmembers().index(directory),payload.getnames().index('./usr/lib/pulsar3-studio/pulsar3/__init__.py'))
                self.assertIn('./usr/lib/pulsar3-studio/pulsar3/data/default.json',payload.getnames())
                self.assertFalse(any('linux.json' in n for n in payload.getnames()))

if __name__=='__main__':unittest.main()
