"""MCP 配置文件管理：生成 NoteAI vault MCP server 配置并注册到各 CLI agent。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from config import config
from utils.logger import logger

MCP_SERVER_NAME = "noteai-vault"

# CLI agent id → MCP 配置 target 名称
AGENT_MCP_TARGETS: dict[str, str] = {
    "claude": "claude",
    "opencode": "opencode",
    "codex": "codex",
    "gemini": "gemini",
    "kimi": "kimi",
}


def _mcp_server_script() -> Path:
    """返回 mcp-server/src/index.js 的绝对路径。"""
    return (Path(__file__).parent.parent.parent / "mcp-server" / "src" / "index.js").resolve()


def _user_home() -> Path:
    return Path.home()


def _config_paths() -> dict[str, Path]:
    """返回各 CLI agent 的 MCP 配置文件路径。"""
    home = _user_home()
    return {
        "claude": home / ".claude" / "mcp.json",
        "cursor": home / ".cursor" / "mcp.json",
        "opencode": home / ".config" / "opencode" / "opencode.json",
        "codex": home / ".codex" / "config.toml",
        "gemini": home / ".gemini" / "settings.json",
        "kimi": home / ".kimi-code" / "mcp.json",
    }


def _resolve_workspace_path(workspace_path: str | None = None) -> Path:
    ws = workspace_path or config.workspace_path
    if not ws:
        raise ValueError("未设置工作区路径")
    return Path(ws).expanduser().resolve()


def build_mcp_server_config(workspace_path: str | None = None) -> dict[str, Any]:
    """生成标准 mcpServers 条目（Claude / Cursor / Kimi / Gemini）。"""
    script = _mcp_server_script()
    if not script.exists():
        raise FileNotFoundError(f"MCP server 脚本不存在: {script}")
    ws_path = _resolve_workspace_path(workspace_path)
    return {
        "command": "node",
        "args": [str(script), "--workspace", str(ws_path)],
    }


def _build_opencode_mcp_entry(workspace_path: str | None = None) -> dict[str, Any]:
    """生成 OpenCode opencode.json 中的 mcp 条目。"""
    script = _mcp_server_script()
    if not script.exists():
        raise FileNotFoundError(f"MCP server 脚本不存在: {script}")
    ws_path = _resolve_workspace_path(workspace_path)
    return {
        "type": "local",
        "command": ["node", str(script), "--workspace", str(ws_path)],
        "enabled": True,
    }


def _toml_quote(value: str) -> str:
    return json.dumps(value)


def _build_codex_mcp_toml_block(workspace_path: str | None = None) -> str:
    """生成 Codex config.toml 的 [mcp_servers.noteai-vault] 块。"""
    script = _mcp_server_script()
    if not script.exists():
        raise FileNotFoundError(f"MCP server 脚本不存在: {script}")
    ws_path = str(_resolve_workspace_path(workspace_path))
    script_path = str(script)
    return (
        f"\n[mcp_servers.{MCP_SERVER_NAME}]\n"
        f"command = {_toml_quote('node')}\n"
        f"args = [{_toml_quote(script_path)}, "
        f"{_toml_quote('--workspace')}, {_toml_quote(ws_path)}]\n"
    )


_CODEX_SECTION_RE = re.compile(
    rf"\n?\[mcp_servers\.{re.escape(MCP_SERVER_NAME)}\][^\[]*",
    re.MULTILINE,
)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _register_mcp_servers_json(path: Path, server_config: dict[str, Any]) -> None:
    data = _read_json_object(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[MCP_SERVER_NAME] = server_config
    data["mcpServers"] = servers
    _write_json_object(path, data)


def _unregister_mcp_servers_json(path: Path) -> bool:
    if not path.exists():
        return False
    data = _read_json_object(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or MCP_SERVER_NAME not in servers:
        return False
    del servers[MCP_SERVER_NAME]
    data["mcpServers"] = servers
    _write_json_object(path, data)
    return True


def _is_registered_mcp_servers_json(path: Path) -> bool:
    data = _read_json_object(path)
    servers = data.get("mcpServers")
    return isinstance(servers, dict) and MCP_SERVER_NAME in servers


def _register_opencode(path: Path, workspace_path: str | None) -> None:
    data = _read_json_object(path)
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        mcp = {}
    mcp[MCP_SERVER_NAME] = _build_opencode_mcp_entry(workspace_path)
    data["mcp"] = mcp
    _write_json_object(path, data)


def _unregister_opencode(path: Path) -> bool:
    if not path.exists():
        return False
    data = _read_json_object(path)
    mcp = data.get("mcp")
    if not isinstance(mcp, dict) or MCP_SERVER_NAME not in mcp:
        return False
    del mcp[MCP_SERVER_NAME]
    data["mcp"] = mcp
    _write_json_object(path, data)
    return True


def _is_registered_opencode(path: Path) -> bool:
    data = _read_json_object(path)
    mcp = data.get("mcp")
    return isinstance(mcp, dict) and MCP_SERVER_NAME in mcp


def _register_codex(path: Path, workspace_path: str | None) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    cleaned = _CODEX_SECTION_RE.sub("", existing).rstrip()
    block = _build_codex_mcp_toml_block(workspace_path)
    content = f"{cleaned}{block}" if cleaned else block.lstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")


def _unregister_codex(path: Path) -> bool:
    if not path.exists():
        return False
    existing = path.read_text(encoding="utf-8")
    if not _CODEX_SECTION_RE.search(existing):
        return False
    cleaned = _CODEX_SECTION_RE.sub("", existing).rstrip()
    if cleaned:
        path.write_text(cleaned + "\n", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return True


def _is_registered_codex(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(re.search(rf"\[mcp_servers\.{re.escape(MCP_SERVER_NAME)}\]", path.read_text(encoding="utf-8")))


def _target_handlers() -> dict[str, dict[str, Callable[..., Any]]]:
    return {
        "claude": {
            "register": lambda path, ws: _register_mcp_servers_json(path, build_mcp_server_config(ws)),
            "unregister": _unregister_mcp_servers_json,
            "is_registered": _is_registered_mcp_servers_json,
        },
        "cursor": {
            "register": lambda path, ws: _register_mcp_servers_json(path, build_mcp_server_config(ws)),
            "unregister": _unregister_mcp_servers_json,
            "is_registered": _is_registered_mcp_servers_json,
        },
        "gemini": {
            "register": lambda path, ws: _register_mcp_servers_json(
                path,
                {**build_mcp_server_config(ws), "trust": True},
            ),
            "unregister": _unregister_mcp_servers_json,
            "is_registered": _is_registered_mcp_servers_json,
        },
        "kimi": {
            "register": lambda path, ws: _register_mcp_servers_json(path, build_mcp_server_config(ws)),
            "unregister": _unregister_mcp_servers_json,
            "is_registered": _is_registered_mcp_servers_json,
        },
        "opencode": {
            "register": _register_opencode,
            "unregister": _unregister_opencode,
            "is_registered": _is_registered_opencode,
        },
        "codex": {
            "register": _register_codex,
            "unregister": _unregister_codex,
            "is_registered": _is_registered_codex,
        },
    }


def register_mcp_server(
    targets: list[str] | None = None,
    workspace_path: str | None = None,
) -> dict[str, Any]:
    """将 NoteAI vault MCP server 注册到指定 CLI agent 配置文件。"""
    all_targets = _config_paths()
    handlers = _target_handlers()
    targets = targets or list(all_targets.keys())

    registered: list[str] = []
    errors: list[str] = []

    for name in targets:
        path = all_targets.get(name)
        handler = handlers.get(name)
        if path is None or handler is None:
            errors.append(f"未知 target: {name}")
            continue
        try:
            handler["register"](path, workspace_path)
            registered.append(name)
            logger.info(f"已注册 NoteAI MCP server 到 {path}")
        except Exception as e:
            errors.append(f"{name}: {e}")
            logger.warning(f"注册 MCP 配置到 {name} 失败: {e}")

    return {
        "success": not errors,
        "registered": registered,
        "errors": errors,
    }


def unregister_mcp_server(targets: list[str] | None = None) -> dict[str, Any]:
    """从各 CLI agent 配置中移除 NoteAI vault MCP server。"""
    all_targets = _config_paths()
    handlers = _target_handlers()
    targets = targets or list(all_targets.keys())

    removed: list[str] = []
    errors: list[str] = []

    for name in targets:
        path = all_targets.get(name)
        handler = handlers.get(name)
        if path is None or handler is None:
            errors.append(f"未知 target: {name}")
            continue
        try:
            if handler["unregister"](path):
                removed.append(name)
                logger.info(f"已从 {path} 移除 NoteAI MCP server")
        except Exception as e:
            errors.append(f"{name}: {e}")

    return {"success": not errors, "removed": removed, "errors": errors}


def get_mcp_status() -> dict[str, Any]:
    """返回各 CLI agent 的 MCP 注册状态。"""
    all_targets = _config_paths()
    handlers = _target_handlers()
    status: dict[str, Any] = {}
    for name, path in all_targets.items():
        handler = handlers.get(name)
        registered = False
        if handler is not None:
            try:
                registered = bool(handler["is_registered"](path))
            except Exception:
                pass
        status[name] = {"path": str(path), "registered": registered}
    return status


def get_mcp_config_path(target: str) -> Path | None:
    """返回指定 CLI 的 MCP 配置文件路径。"""
    return _config_paths().get(target)


def register_mcp_for_agent(
    agent_id: str,
    workspace_path: str | None = None,
) -> dict[str, Any]:
    """为单个 CLI agent 注册 MCP（按 agent_id 映射 target）。"""
    target = AGENT_MCP_TARGETS.get(agent_id)
    if target is None:
        return {"success": True, "registered": [], "errors": []}
    return register_mcp_server(targets=[target], workspace_path=workspace_path)
