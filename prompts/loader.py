"""Prompt loader: reads prompts from YAML files, falls back to legacy Python modules."""

import sys
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent
_YAML_DIR = _PROMPTS_DIR / "yaml"


def load_prompt(name: str, **kwargs) -> str:
    """Load a prompt template by name, format with kwargs.

    Precedence:
    1. prompts/yaml/{name}.yaml  (YAML file, preferred)
    2. prompts/{name}.py         (legacy Python module)

    Example:
        from prompts import load_prompt
        system = load_prompt("rag_assistant", system=True)
    """
    result = _load_from_yaml(name, **kwargs)
    if result:
        return result
    return _load_from_legacy(name, **kwargs)


def _load_from_yaml(name: str, **kwargs) -> str | None:
    yaml_file = _YAML_DIR / f"{name}.yaml"
    if not yaml_file.exists():
        return None
    import yaml as _yaml
    with open(yaml_file, encoding="utf-8") as f:
        data = _yaml.safe_load(f)
    if not isinstance(data, dict):
        return str(data)
    if "system" in kwargs and kwargs["system"]:
        template = data.get("system", "")
    elif "user" in kwargs and kwargs["user"]:
        template = data.get("user", "")
    else:
        template = data.get("system", "")
    if template and kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            sys.stderr.write(f"[prompts] missing key in {name}.yaml: {e}\n")
            sys.stderr.flush()
            return template
    return template


def _load_from_legacy(name: str, **kwargs) -> str:
    try:
        mod = __import__(f"prompts.{name}", fromlist=["__all__"])
    except ImportError:
        raise ImportError(f"Prompt not found: {name} (no prompts/{name}.py or .yaml)")
    result = ""
    if hasattr(mod, "SYSTEM_PROMPT"):
        result = mod.SYSTEM_PROMPT
    elif hasattr(mod, "PROMPT"):
        result = mod.PROMPT
    else:
        for attr in dir(mod):
            if attr.upper() == attr and isinstance(getattr(mod, attr), str):
                result = getattr(mod, attr)
                break
    if kwargs and result:
        try:
            return result.format(**kwargs)
        except KeyError as e:
            sys.stderr.write(f"[prompts] missing key in {name}.py: {e}\n")
            sys.stderr.flush()
            return result
    return result if result else ""
