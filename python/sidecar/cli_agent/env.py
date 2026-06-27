"""CLI agent 环境工具：登录 shell env、PATH 合并、API key 查找。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from config import config
from utils.logger import logger


# 登录 shell 环境缓存：GUI 启动时 PATH 不完整，通过登录 shell 获取用户真实环境
_login_shell_env: dict[str, str] | None = None
_login_shell_env_fetched = False


def get_login_shell() -> str:
    """返回用户默认 shell，回退到 macOS 常见的 zsh/bash。"""
    shell = os.environ.get("SHELL", "").strip()
    if shell and Path(shell).exists():
        return shell
    for fallback in ("/bin/zsh", "/bin/bash"):
        if Path(fallback).exists():
            return fallback
    return "/bin/sh"


def get_login_shell_env() -> dict[str, str]:
    """从登录 shell 获取用户环境变量（PATH、NVM、API key 等）。

    Tauri 侧载的 Python 子进程通常继承不到用户 shell 的完整环境，
    参考 cli-agents crate 的做法，通过登录 shell 读取 env。
    """
    global _login_shell_env, _login_shell_env_fetched
    if _login_shell_env_fetched:
        return _login_shell_env or {}

    _login_shell_env_fetched = True
    shell = get_login_shell()
    try:
        proc = subprocess.run(
            [shell, "-l", "-c", "env"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(f"登录 shell env 获取失败: {proc.stderr.strip()}")
            return {}

        env: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            # 跳过 shell 内部变量，只保留有意义的导出变量
            if key and not key.startswith("_"):
                env[key] = value
        _login_shell_env = env
        logger.info("已从登录 shell 获取用户环境变量")
        return env
    except Exception as e:
        logger.warning(f"登录 shell env 获取异常: {e}")
        return {}


def which_via_login_shell(cmd: str) -> str | None:
    """通过登录 shell 的 which 查找命令绝对路径。

    比 shutil.which 更可靠，能继承 shell rc 文件里的 PATH、nvm、fnm 等配置。
    """
    shell = get_login_shell()
    try:
        proc = subprocess.run(
            [shell, "-l", "-c", f"command -v {cmd} || which {cmd}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        path = proc.stdout.strip().splitlines()[0].strip()
        if path and Path(path).exists() and os.access(path, os.X_OK):
            return path
    except Exception as e:
        logger.debug(f"login shell which {cmd} 异常: {e}")
    return None


def common_bin_dirs() -> list[Path]:
    """返回常见 CLI 安装目录。

    Tauri 侧载的 Python 子进程通常继承不到用户 shell 的完整 PATH，
    因此手动补充 Homebrew、npm 全局、bun、claude 本地安装等常见路径。
    """
    dirs: list[Path] = []
    home = Path.home()

    candidates = [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
        "/opt/homebrew/opt/node/bin",
        "/usr/local/opt/node/bin",
        home / ".local" / "bin",
        home / ".kimi-code" / "bin",
        home / ".npm-global" / "bin",
        home / ".bun" / "bin",
        home / ".claude" / "local",
        home / ".nvm" / "versions" / "node",
    ]

    for c in candidates:
        if isinstance(c, str):
            p = Path(c)
        else:
            p = c
        if p.exists() and p.is_dir():
            # nvm 路径下面还有版本子目录
            if "nvm" in str(p) and (p / "..").name == "node":
                for sub in sorted(p.iterdir(), reverse=True):
                    if sub.is_dir():
                        bin_dir = sub / "bin"
                        if bin_dir.exists():
                            dirs.append(bin_dir)
            else:
                dirs.append(p)

    return dirs


def resolve_command(cmd: str, aliases: list[str] | None = None) -> str | None:
    """在 PATH 与常见目录中解析命令，返回绝对路径或命令名。

    优先通过登录 shell 查找，继承用户 shell 的完整 PATH（nvm、homebrew 等）。
    """
    names = [cmd]
    if aliases:
        names.extend(aliases)

    # 1. 通过登录 shell 查找（最可靠，继承 .zshrc/.bashrc 的 PATH）
    for name in names:
        found = which_via_login_shell(name)
        if found:
            return found

    # 2. 使用登录 shell 的 PATH 进行 shutil.which
    login_env = get_login_shell_env()
    login_path = login_env.get("PATH", "")
    for name in names:
        found = shutil.which(name, path=login_path) if login_path else shutil.which(name)
        if found:
            return found

    # 3. 扫描常见安装目录
    for directory in common_bin_dirs():
        for name in names:
            candidate = directory / name
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)

    return None


def merge_path(current: str, login: str) -> str:
    """合并 PATH：保留登录 shell 中的条目优先，再追加当前进程独有的条目。

    Tauri 启动的 Python 子进程通常只拿到最小 PATH（/usr/bin:/bin），
    而 agent 及其子进程需要完整的用户 PATH，因此让登录 shell PATH 优先。
    """
    current_parts = [p for p in current.split(":") if p]
    login_parts = [p for p in login.split(":") if p]
    seen = set()
    merged: list[str] = []
    for p in login_parts + current_parts:
        if p not in seen:
            seen.add(p)
            merged.append(p)
    return ":".join(merged)


def lookup_api_key(key: str, login_env: dict[str, str] | None = None) -> str | None:
    """查找单个 API key：环境变量 > 登录 shell > config 精确字段 > config.api_key 兜底。"""
    if login_env is None:
        login_env = get_login_shell_env()
    val = os.environ.get(key) or login_env.get(key)
    if val:
        return val
    if hasattr(config, key.lower()):
        return getattr(config, key.lower())
    # Codex 等 OpenAI 工具可直接复用 NoteAI 设置里的主 API key
    if key == "OPENAI_API_KEY" and getattr(config, "api_key", None):
        return config.api_key
    return None


def build_agent_env(required_keys: list[str]) -> dict[str, str]:
    """合并当前环境变量、登录 shell 环境与 agent 所需的 API key。

    优先从 os.environ / config 读取，确保 GUI 启动时也能拿到 key。
    登录 shell 环境可补充 PATH、NVM、fnm 等配置；PATH 会智能合并而非被覆盖。
    """
    login_env = get_login_shell_env()
    # 以当前进程环境为基准，缺失项从登录 shell 补充；PATH 做合并而非简单覆盖
    env = dict(os.environ)
    for key, value in login_env.items():
        if key == "PATH":
            env["PATH"] = merge_path(env.get("PATH", ""), value)
        elif key not in env:
            env[key] = value

    # 禁用颜色，保证流式输出是纯文本
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"

    for key in required_keys:
        val = lookup_api_key(key, login_env)
        if val:
            env[key] = val
    return env


def validate_prompt(prompt: str, max_length: int = 10000) -> tuple[bool, str]:
    """校验用户 prompt，避免被外部 CLI 参数解析器误解释。"""
    if not prompt or not prompt.strip():
        return False, "prompt 不能为空"
    if len(prompt) > max_length:
        return False, f"prompt 超过最大长度 {max_length}"
    if "\x00" in prompt:
        return False, "prompt 包含非法空字符"
    # 控制字符仅允许常见空白，避免终端控制序列
    if any(ch != "\n" and ch != "\r" and ch != "\t" and ord(ch) < 32 for ch in prompt):
        return False, "prompt 包含非法控制字符"
    # 防止被解析为 CLI 选项（如 opencode run -foo）
    stripped = prompt.lstrip()
    if stripped.startswith("-"):
        return False, "prompt 不能以 '-' 开头"
    if stripped.startswith("-- "):
        return False, "prompt 不能以 '-- ' 开头"
    return True, ""


def resolve_workspace(ws: str | None) -> tuple[Path | None, str]:
    """解析并校验工作区路径，返回 (path, error_message)。"""
    if not ws:
        return None, "未设置工作区"
    candidate = Path(ws).expanduser().resolve()
    if not candidate.exists():
        return None, f"工作区路径不存在: {ws}"
    if not candidate.is_dir():
        return None, f"工作区路径不是目录: {ws}"
    return candidate, ""
