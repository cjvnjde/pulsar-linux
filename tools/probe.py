#!/usr/bin/env python3
"""Compatibility wrapper: read descriptors and live status without configuration writes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pulsar3.__main__ import main
if __name__ == '__main__':
    raise SystemExit(main(['probe']))
