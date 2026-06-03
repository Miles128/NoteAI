import os

import requests

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class BaiduProvider(CloudProvider):
    PROVIDER_NAME = "baidu"
    DISPLAY_NAME = "百度网盘"
    AUTH_TYPE = "access_token"
    AUTH_FIELDS = [
        {"key": "access_token", "label": "Access Token", "type": "text", "placeholder": "百度网盘 Access Token"},
    ]

    API_BASE = "https://pan.baidu.com/rest/2.0/xpan"
    PCS_BASE = "https://d.pcs.baidu.com/rest/2.0/pcs"
    REMOTE_ROOT = "/apps/NoteAI"

    def __init__(self, config: dict):
        super().__init__(config)
        self._access_token = config.get("access_token", "")

    def authenticate(self, credentials: dict) -> dict:
        token = credentials.get("access_token", self._access_token)
        if not token:
            return {"success": False, "message": "请提供 Access Token"}
        self._access_token = token
        try:
            resp = requests.get(
                f"{self.API_BASE}/nas",
                params={"method": "uinfo", "access_token": token},
                timeout=10,
            )
            if resp.status_code == 200 and "baidu_name" in resp.json():
                return {"success": True, "message": "认证成功"}
            return {"success": False, "message": "Access Token 无效"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def is_authenticated(self) -> bool:
        if not self._access_token:
            return False
        try:
            resp = requests.get(
                f"{self.API_BASE}/nas",
                params={"method": "uinfo", "access_token": self._access_token},
                timeout=10,
            )
            return resp.status_code == 200 and "baidu_name" in resp.json()
        except Exception:
            return False

    def list_files(self, remote_path: str = "") -> list:
        path = f"{self.REMOTE_ROOT}/{remote_path}" if remote_path else self.REMOTE_ROOT
        resp = requests.get(
            f"{self.API_BASE}/file",
            params={"method": "list", "access_token": self._access_token, "dir": path},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = []
        for item in data.get("list", []):
            is_dir = item.get("isdir", 0) == 1
            mtime = item.get("server_mtime", 0)
            items.append(CloudFileInfo(
                path=f"{remote_path}/{item['server_filename']}" if remote_path else item["server_filename"],
                name=item["server_filename"],
                size=item.get("size", 0),
                modified_time=float(mtime) if mtime else 0.0,
                is_dir=is_dir,
                cloud_id=str(item.get("fs_id", "")),
            ))
        return items

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        path = f"{self.REMOTE_ROOT}/{remote_path}"
        with open(local_path, "rb") as f:
            resp = requests.post(
                f"{self.PCS_BASE}/file",
                params={"method": "upload", "access_token": self._access_token, "path": path},
                files={"file": f},
                timeout=120,
            )
        return resp.status_code == 200

    def download_file(self, remote_path: str, local_path: str) -> bool:
        path = f"{self.REMOTE_ROOT}/{remote_path}"
        resp = requests.get(
            f"{self.PCS_BASE}/file",
            params={"method": "download", "access_token": self._access_token, "path": path},
            timeout=120,
            stream=True,
        )
        if resp.status_code != 200:
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True

    def create_folder(self, remote_path: str) -> bool:
        path = f"{self.REMOTE_ROOT}/{remote_path}"
        resp = requests.post(
            f"{self.API_BASE}/file",
            params={"method": "create", "access_token": self._access_token, "path": path},
            timeout=30,
        )
        return resp.status_code == 200
