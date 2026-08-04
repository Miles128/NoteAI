"""prompts YAML 单源契约守护测试。

prompts/__init__.py 在导入期通过 get_prompt(module, key) 解析全部常量，
任一 YAML key 缺失都会导致 sidecar 进程 import 失败。本测试在提交前
交叉校验常量清单与 prompts/yaml/*.yaml 的实际 key，把错误前移到测试阶段。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_INIT = PROJECT_ROOT / "prompts" / "__init__.py"
YAML_DIR = PROJECT_ROOT / "prompts" / "yaml"


def _get_prompt_calls() -> list[tuple[str, str]]:
    """解析 prompts/__init__.py 中全部 get_prompt(module, key) 调用。"""
    tree = ast.parse(PROMPTS_INIT.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "get_prompt"):
            continue
        assert len(node.args) == 2, f"get_prompt 调用参数异常: line {node.lineno}"
        module_arg, key_arg = node.args
        assert isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str), (
            f"get_prompt module 参数必须是字符串字面量: line {node.lineno}"
        )
        assert isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str), (
            f"get_prompt key 参数必须是字符串字面量: line {node.lineno}"
        )
        pairs.append((module_arg.value, key_arg.value))
    return pairs


@pytest.fixture(scope="module")
def yaml_data_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    for yaml_file in YAML_DIR.glob("*.yaml"):
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        cache[yaml_file.stem] = data if isinstance(data, dict) else {}
    return cache


def test_init_parses_and_has_calls():
    pairs = _get_prompt_calls()
    assert len(pairs) >= 30, f"prompts/__init__.py 中 get_prompt 调用数量异常: {len(pairs)}"


def test_every_constant_resolves_in_yaml(yaml_data_cache):
    missing = []
    for module, key in _get_prompt_calls():
        data = yaml_data_cache.get(module)
        if data is None:
            missing.append(f"{module}.yaml 文件不存在 (需要 {key})")
        elif key not in data:
            missing.append(f"{module}.{key}")
        elif not isinstance(data[key], str) or not data[key].strip():
            missing.append(f"{module}.{key} 不是非空字符串")
    assert not missing, "以下 prompt key 无法从 YAML 解析:\n" + "\n".join(missing)


def test_import_time_resolution(yaml_data_cache):
    """导入期解析等价校验：所有常量都能通过 loader 拿到非空字符串。"""
    from prompts.loader import get_prompt

    for module, key in _get_prompt_calls():
        value = get_prompt(module, key)
        assert isinstance(value, str) and value.strip(), f"{module}.{key} 解析为空"


def test_prompts_package_imports():
    """整包导入成功即证明全部常量在当前 YAML 下可解析。"""
    import prompts

    for name in prompts.__all__:
        assert hasattr(prompts, name), f"prompts.__all__ 中的 {name} 缺失"
