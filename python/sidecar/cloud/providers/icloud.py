import os
import shutil

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class ICloudProvider(CloudProvider):
    PROVIDER_NAME = "icloud"
    DISPLAY_NAME = "iCloud"
    AUTH_TYPE = "path"
    AUTH_FIELDS = [
        {
            "key": "folder_path",
            "label": "iCloud 文件夹路径",
            "type": "text",
            "placeholder": "如 ~/Library/Mobile Documents/com~apple~CloudDocs/NoteAI/",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self._folder_path = os.path.expanduser(config.get("folder_path", ""))

    def authenticate(self, credentials: dict) -> dict:
        folder = os.path.expanduser(credentials.get("folder_path", self._folder_path))
        if not folder:
            return {"success": False, "message": "请提供 iCloud 文件夹路径"}
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                return {"success": False, "message": f"无法创建目录: {e}"}
        self._folder_path = folder
        return {"success": True, "message": "路径已验证"}

    def is_authenticated(self) -> bool:
        return bool(self._folder_path) and os.path.isdir(self._folder_path)

    def list_files(self, remote_path: str = "") -> list:
        target = os.path.join(self._folder_path, remote_path) if remote_path else self._folder_path
        if not os.path.isdir(target):
            return []
        items = []
        for entry in os.scandir(target):
            stat = entry.stat()
            rel = os.path.join(remote_path, entry.name) if remote_path else entry.name
            items.append(
                CloudFileInfo(
                    path=rel,
                    name=entry.name,
                    size=stat.st_size,
                    modified_time=stat.st_mtime,
                    is_dir=entry.is_dir(follow_symlinks=False),
                    cloud_id=os.path.join(target, entry.name),
                )
            )
        return items

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        dst = os.path.join(self._folder_path, remote_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(local_path, dst)
            return True
        except Exception:
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        src = os.path.join(self._folder_path, remote_path)
        if not os.path.isfile(src):
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        try:
            shutil.copy2(src, local_path)
            return True
        except Exception:
            return False

    def create_folder(self, remote_path: str) -> bool:
        path = os.path.join(self._folder_path, remote_path)
        try:
            os.makedirs(path, exist_ok=True)
            return True
        except Exception:
            return False
