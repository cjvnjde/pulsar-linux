#!/usr/bin/env python3
"""Build reproducible Linux tar.gz and Debian packages with the standard library.

Only explicitly listed runtime files are included. Personal profiles, write
journals, vendor software, and reverse-engineering extracts are never packaged.
"""
import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pulsar3 import __version__

DOCS = ['README.md', 'LICENSE', 'USER_GUIDE.md', 'UI_CAPABILITIES.md', 'PROTOCOL.md']


def tar_bytes(files, epoch):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.PAX_FORMAT) as archive:
        # dpkg requires parent directories in the archive before their files.
        # These entries also give the package manager ownership of new directories.
        directories = set()
        for name, _, _ in files:
            parent = name.rpartition('/')[0]
            while parent and parent != '.':
                directories.add(parent)
                parent = parent.rpartition('/')[0]
        for name in sorted(directories, key=lambda value: (value.count('/'), value)):
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            archive.addfile(info)
        for name, data, mode in sorted(files):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            archive.addfile(info, io.BytesIO(data))
    return gzip.compress(buffer.getvalue(), mtime=epoch)


def ar_bytes(members, epoch):
    result = bytearray(b'!<arch>\n')
    for name, data in members:
        header = f'{name+"/":<16}{epoch:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'
        if len(header) != 60:
            raise ValueError('Invalid ar member header')
        result.extend(header.encode('ascii'))
        result.extend(data)
        if len(data) % 2:
            result.extend(b'\n')
    return bytes(result)


def runtime_files():
    for path in sorted((ROOT/'pulsar3').rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.json', '.css', '.svg'} and '__pycache__' not in path.parts:
            yield str(path.relative_to(ROOT)), path.read_bytes(), 0o644


def build(output, version, epoch):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[+~.-][A-Za-z0-9.+~-]+)?', version):
        raise ValueError('Version must begin with major.minor.patch and contain only version characters')
    output.mkdir(parents=True, exist_ok=True)
    prefix = f'pulsar3-studio-{version}'
    runtime = list(runtime_files())
    docs = [(name, (ROOT/name).read_bytes(), 0o644) for name in DOCS]
    portable = runtime + docs + [('pulsar3-gui', (ROOT/'pulsar3-gui').read_bytes(), 0o755)]
    archive = output/f'{prefix}-linux.tar.gz'
    archive.write_bytes(tar_bytes([(f'{prefix}/{name}', data, mode) for name, data, mode in portable], epoch))

    payload = [(f'./usr/lib/pulsar3-studio/{name}', data, mode) for name, data, mode in runtime]
    payload += [(f'./usr/share/doc/pulsar3-studio/{name}', data, mode) for name, data, mode in docs]
    for executable in ('pulsar3', 'pulsar3-gui'):
        payload.append((f'./usr/bin/{executable}', (ROOT/'packaging'/executable).read_bytes(), 0o755))
    payload.append(('./usr/share/applications/local.hator.Pulsar3.Studio.desktop',
                    (ROOT/'packaging/local.hator.Pulsar3.Studio.desktop').read_bytes(), 0o644))
    payload.append(('./usr/share/icons/hicolor/scalable/apps/local.hator.Pulsar3.Studio.svg',
                    (ROOT/'packaging/icon.svg').read_bytes(), 0o644))
    installed_size = (sum(len(data) for _, data, _ in payload)+1023)//1024
    control = f'''Package: pulsar3-studio
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: cjvnjde <cjvnjde@users.noreply.github.com>
Installed-Size: {installed_size}
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.10), gir1.2-adw-1, pkexec, acl
Homepage: https://github.com/cjvnjde/pulsar-linux
Description: Native Linux configurator for the HATOR Pulsar 3 mouse
 GTK4 interface and command-line tool for USB device 379a:3910.
 Configure DPI, polling, RGB lighting, buttons, shortcuts and macros.
 No Windows software or replacement firmware is required.
'''
    deb = output/f'pulsar3-studio_{version}_all.deb'
    deb.write_bytes(ar_bytes([
        ('debian-binary', b'2.0\n'),
        ('control.tar.gz', tar_bytes([('./control', control.encode(), 0o644)], epoch)),
        ('data.tar.gz', tar_bytes(payload, epoch)),
    ], epoch))
    checksums = output/'SHA256SUMS'
    checksums.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in (archive, deb)))
    return archive, deb, checksums


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'dist')
    parser.add_argument('--version', default=__version__)
    args = parser.parse_args()
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
    for path in build(args.output, args.version, epoch):
        print(path)


if __name__ == '__main__':
    main()
