"""Desktop helpers shared by Linux distributions; no compositor-specific APIs."""
import os
import shutil


def device_access_command(paths):
    commands = {name: shutil.which(name) for name in ('pkexec', 'setfacl')}
    missing = [name for name, path in commands.items() if path is None]
    if missing:
        raise RuntimeError('Device access needs ' + ', '.join(missing) + '. Install the polkit and ACL tools from your distribution.')
    return [commands['pkexec'], commands['setfacl'], '-m', f'u:{os.getuid()}:rw', *paths]
