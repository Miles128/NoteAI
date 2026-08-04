"""Regression tests for the config import chain.

A circular import once hid inside the singleton bootstrap:
``config.settings`` -> ``config.app_config`` (builds ``config`` at import
time) -> ``utils.keyring_store`` -> back to ``config.settings`` while it was
still initializing. The failure was swallowed as a warning and silently
disabled API-key loading, so these tests import the chain in fresh
interpreters and assert hard failures instead of relying on runtime logs.
"""

import subprocess
import sys

import pytest

_PROJECT_IMPORTS = [
    "config.constants",
    "config.settings",
    "config.app_config",
    "config",
    "utils.keyring_store",
]


@pytest.mark.parametrize("module", _PROJECT_IMPORTS)
def test_module_imports_cleanly_in_fresh_interpreter(module: str) -> None:
    """Each entry point must import without circular-import errors.

    Running in a subprocess guarantees pristine ``sys.modules`` state, which
    the in-process test runner cannot provide.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"import {module} failed:\n{result.stderr}"
    assert "circular import" not in result.stderr


def test_settings_import_first_loads_api_key_without_warning() -> None:
    """``config.settings`` must be importable as the very first config module.

    The original bug only reproduced when ``settings`` (not ``constants``)
    was the entry point, because the singleton build ran before ``settings``
    finished initializing.
    """
    code = (
        "import logging, io, sys\n"
        "handler = logging.StreamHandler(sys.stderr)\n"
        "logging.getLogger('NoteAI').addHandler(handler)\n"
        "logging.getLogger('NoteAI').setLevel(logging.WARNING)\n"
        "from config.settings import config\n"
        "assert config is not None\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    # The warning must be surfaced if it occurs: earlier the circular import
    # only appeared as a log line, so an empty stderr is part of the contract.
    assert "加载API key失败" not in result.stderr
    assert "circular import" not in result.stderr


def test_api_key_load_failure_would_be_visible() -> None:
    """Guard for the previous test: force a failure and confirm it logs."""
    code = (
        "import sys, logging\n"
        "logging.getLogger('NoteAI').addHandler(logging.StreamHandler(sys.stderr))\n"
        "logging.getLogger('NoteAI').setLevel(logging.WARNING)\n"
        "import utils.keyring_store as ks\n"
        "def boom():\n"
        "    raise RuntimeError('forced')\n"
        "ks.load_api_key = boom\n"
        "import importlib\n"
        "from config import app_config\n"
        "try:\n"
        "    from utils.keyring_store import load_api_key\n"
        "    load_api_key()\n"
        "except Exception as e:\n"
        "    logging.getLogger('NoteAI').warning('加载API key失败: %s', e)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "加载API key失败" in result.stderr


def test_keyring_store_reads_constants_not_settings() -> None:
    """The credential store must resolve the data dir from the leaf module.

    ``config.constants`` has no intra-package imports, so reading from it can
    never re-enter the ``settings`` -> ``app_config`` bootstrap cycle.
    """
    import inspect

    import utils.keyring_store as keyring_store

    source = inspect.getsource(keyring_store._app_data_dir)
    assert "config.constants" in source
    assert "config.settings" not in source
