#!/usr/bin/env python3
"""Run upstream's parakeet_dictation worker against the installed mlx-omarchy 0.7.33 CLI.

Upstream drift (found 2026-10-18): parakeet_dictation calls cli._verify_assets(), which the
installed CLI no longer has, and builds AneIsland without the seal_assets that `transcribe`
passes. This shim restores the same guarantee without editing the installed wheel: the cache
is still verified against the lock by the module, and every byte the ANE loads is sealed
against pin["assets"] exactly as the CLI does. Env: PYTHONPATH must contain <prefix>/.../mlx.
"""
import sys
from coreml import parakeet_dictation as pd

_load = pd.load_cli_module


def _patched_cli():  # the module loads a fresh CLI copy on every call, so patch each one
    cli = _load()
    cli._verify_assets = lambda _pin: None  # superseded by seal_assets below
    return cli


pd.load_cli_module = _patched_cli
pin = _patched_cli()._load_pin()

from coreml import vulkan_encoder as ve
_Island = ve.AneIsland


def _sealed(*a, **kw):
    kw.setdefault("seal_assets", pin["assets"])
    return _Island(*a, **kw)


ve.AneIsland = _sealed
sys.exit(pd.main(["--worker"]))
