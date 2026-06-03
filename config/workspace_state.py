import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .constants import WORKSPACE_STATE_FILE


class WorkspaceStateError(Exception):
    pass


class WorkspaceStateManager:
    def __init__(self, state_file: Path = None):
        self.state_file = state_file or WORKSPACE_STATE_FILE
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            raise WorkspaceStateError(f"无法创建应用数据目录: {e}")

    def _atomic_write(self, data: Dict[str, Any]) -> bool:
        try:
            temp_dir = self.state_file.parent
            fd, temp_path = tempfile.mkstemp(dir=temp_dir, suffix=".tmp")

            try:
                os.close(fd)
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                fsync_fd = os.open(temp_path, os.O_RDONLY)
                try:
                    os.fsync(fsync_fd)
                finally:
                    os.close(fsync_fd)

                if self.state_file.exists():
                    old_path = self.state_file.with_suffix(".json.bak")
                    if old_path.exists():
                        old_path.unlink()
                    shutil.copy2(self.state_file, old_path)

                shutil.move(temp_path, self.state_file)

                return True
            finally:
                if Path(temp_path).exists():
                    try:
                        Path(temp_path).unlink()
                    except Exception as e:
                        print(f"清理临时文件失败: {e}")
        except PermissionError:
            raise WorkspaceStateError("保存工作区状态失败：没有写入权限")
        except OSError as e:
            raise WorkspaceStateError(f"保存工作区状态失败：{e}")

    def save_workspace(self, workspace_path: str, additional_data: Dict[str, Any] = None) -> Tuple[bool, str]:
        if not workspace_path:
            return False, "工作区路径为空"

        workspace = Path(workspace_path)
        if not workspace.exists():
            return False, f"工作区路径不存在: {workspace_path}"

        data = {
            "workspace_path": str(workspace),
            "last_opened_at": self._get_timestamp(),
            "version": "1.0.0"
        }

        if additional_data:
            data.update(additional_data)

        try:
            success = self._atomic_write(data)
            if success:
                return True, f"工作区已保存: {workspace_path}"
            return False, "保存工作区失败"
        except WorkspaceStateError as e:
            return False, str(e)

    def load_workspace(self) -> Tuple[Optional[str], Dict[str, Any]]:
        if not self.state_file.exists():
            return None, {}

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            workspace_path = data.get("workspace_path")
            if workspace_path:
                workspace = Path(workspace_path)
                if not workspace.exists():
                    return None, data

            return workspace_path, data
        except json.JSONDecodeError:
            return self._try_restore_from_backup()
        except (PermissionError, OSError) as e:
            print(f"加载工作区状态时出错: {e}")
            return self._try_restore_from_backup()

    def _try_restore_from_backup(self) -> Tuple[Optional[str], Dict[str, Any]]:
        backup_file = self.state_file.with_suffix(".json.bak")
        if not backup_file.exists():
            return None, {}

        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            workspace_path = data.get("workspace_path")
            if workspace_path:
                workspace = Path(workspace_path)
                if not workspace.exists():
                    return None, data

            print("已从备份文件恢复工作区状态")
            return workspace_path, data
        except Exception:
            return None, {}

    def clear_workspace_state(self) -> Tuple[bool, str]:
        try:
            if self.state_file.exists():
                old_path = self.state_file.with_suffix(".json.bak")
                if old_path.exists():
                    old_path.unlink()
                shutil.copy2(self.state_file, old_path)
                self.state_file.unlink()
            return True, "工作区状态已清除"
        except Exception as e:
            return False, f"清除工作区状态失败: {e}"

    def get_workspace_info(self) -> Dict[str, Any]:
        info = {
            "is_saved": False,
            "saved_path": None,
            "workspace_path": None,
            "is_valid": False,
            "workspace_name": None,
            "last_opened_at": None,
            "state_file": str(self.state_file),
            "state_file_exists": self.state_file.exists()
        }

        if not self.state_file.exists():
            return info

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = self._try_read_backup()

        saved_path = data.get("workspace_path")

        if saved_path:
            info["is_saved"] = True
            info["saved_path"] = saved_path
            info["last_opened_at"] = data.get("last_opened_at")

            workspace = Path(saved_path)
            if workspace.exists():
                info["is_valid"] = True
                info["workspace_path"] = saved_path
                info["workspace_name"] = workspace.name
            else:
                info["is_valid"] = False
                info["workspace_path"] = None
                info["workspace_name"] = None

        return info

    def _try_read_backup(self) -> Dict[str, Any]:
        backup_file = self.state_file.with_suffix(".json.bak")
        if not backup_file.exists():
            return {}

        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()


workspace_manager = WorkspaceStateManager()