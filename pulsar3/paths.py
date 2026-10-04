"""Installed resources and writable per-user paths (XDG base directories)."""
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
DEFAULT_PROFILE = PACKAGE / 'data/default.json'


def xdg_dir(variable, fallback):
    value = os.environ.get(variable, '')
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def profiles_dir():
    return xdg_dir('XDG_DATA_HOME', '.local/share') / 'pulsar3/profiles'


def working_profile():
    return profiles_dir() / 'linux.json'


def history_dir():
    return xdg_dir('XDG_STATE_HOME', '.local/state') / 'pulsar3/history'


def initial_profile():
    """Read legacy checkout settings without overwriting or publishing them."""
    current = working_profile()
    if current.exists():
        return current
    legacy = ROOT / 'profiles/linux.json'
    return legacy if legacy.exists() else DEFAULT_PROFILE
