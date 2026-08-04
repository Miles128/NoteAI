"""Prompt loader: reads prompts from YAML files (single source of truth)."""

import sys
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent
_YAML_DIR = _PROMPTS_DIR / "yaml"

_yaml_cache: dict[str, dict[str, str]] = {}


def _load_yaml_module(module_name: str) -> dict[str, str] | None:
    if module_name in _yaml_cache:
        return _yaml_cache[module_name]
    yaml_file = _YAML_DIR / f"{module_name}.yaml"
    if not yaml_file.exists():
        return None
    try:
        import yaml as _yaml

        with open(yaml_file, encoding="utf-8") as f:
            data = _yaml.safe_load(f)
    except Exception as e:
        sys.stderr.write(f"[prompts] failed to load {yaml_file}: {e}\n")
        sys.stderr.flush()
        return None
    if not isinstance(data, dict):
        return None
    filtered = {k: v for k, v in data.items() if isinstance(v, str)}
    _yaml_cache[module_name] = filtered
    return filtered


def get_prompt(module_name: str, constant_name: str) -> str:
    yaml_data = _load_yaml_module(module_name)
    if yaml_data and constant_name in yaml_data:
        return yaml_data[constant_name]
    raise ValueError(f"Prompt not found: {module_name}.{constant_name}")
