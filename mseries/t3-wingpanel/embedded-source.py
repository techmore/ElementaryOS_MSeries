#!/usr/bin/env python3
"""Remove only the standalone module entrypoint; retain the maintained widget."""
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
marker = '\npublic Wingpanel.Indicator? get_indicator ('
assert source.count(marker) == 1, 'unexpected standalone entrypoint'
Path(sys.argv[2]).write_text(source[:source.index(marker)])
