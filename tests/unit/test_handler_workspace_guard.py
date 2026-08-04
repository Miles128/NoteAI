"""_require_workspace 统一守卫的最小回归测试。

覆盖正常解析、无 workspace、自定义 message、extra 字段注入四个分支。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sidecar.handlers.base import NO_WORKSPACE_MESSAGE, BaseHandler


def _make_handler(workspace_path):
    server = SimpleNamespace(_ctx=SimpleNamespace(config=SimpleNamespace(workspace_path=workspace_path)))
    return BaseHandler(server)


@pytest.fixture
def handler_with_workspace():
    return _make_handler("/tmp/example-workspace")


@pytest.fixture
def handler_without_workspace():
    return _make_handler(None)


def test_returns_workspace_when_set(handler_with_workspace):
    workspace, error = handler_with_workspace._require_workspace()
    assert workspace == "/tmp/example-workspace"
    assert error is None


def test_returns_error_dict_when_missing(handler_without_workspace):
    workspace, error = handler_without_workspace._require_workspace()
    assert workspace is None
    assert error == {"success": False, "message": NO_WORKSPACE_MESSAGE}


def test_empty_string_treated_as_missing():
    workspace, error = _make_handler("")._require_workspace()
    assert workspace is None
    assert error["success"] is False
    assert error["message"] == NO_WORKSPACE_MESSAGE


def test_custom_message(handler_without_workspace):
    _, error = handler_without_workspace._require_workspace(message="请先选择工作区")
    assert error["message"] == "请先选择工作区"


def test_extra_fields_merged(handler_without_workspace):
    _, error = handler_without_workspace._require_workspace(extra={"started": False})
    assert error == {"success": False, "message": NO_WORKSPACE_MESSAGE, "started": False}


def test_extra_ignored_when_workspace_set(handler_with_workspace):
    workspace, error = handler_with_workspace._require_workspace(extra={"started": False})
    assert workspace == "/tmp/example-workspace"
    assert error is None
