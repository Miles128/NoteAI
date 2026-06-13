import os
from datetime import datetime

import requests

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class AliyunProvider(CloudProvider):
    PROVIDER_NAME = "aliyun"
    DISPLAY_NAME = "阿里云盘"
    AUTH_TYPE = "access_token"
    AUTH_FIELDS = [
        {"key": "access_token", "label": "Access Token", "type": "text", "placeholder": "阿里云盘 Access Token"},
    ]

    API_BASE = "https://openapi.alipan.com"
    REMOTE_ROOT = "NoteAI"

    def __init__(self, config: dict):
        super().__init__(config)
        self._access_token = config.get("access_token", "")
        self._root_id = config.get("root_id", "")

    def _headers(self):
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    def _parse_mtime(self, mtime_str: str) -> float:
        if not mtime_str:
            return 0.0
        try:
            dt = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0

    def authenticate(self, credentials: dict) -> dict:
        token = credentials.get("access_token", self._access_token)
        if not token:
            return {"success": False, "message": "请提供 Access Token"}
        self._access_token = token
        try:
            resp = requests.post(
                f"{self.API_BASE}/adrive/v1.0/openFile/list",
                headers=self._headers(),
                json={"drive_id": "", "parent_file_id": "root", "limit": 1},
                timeout=10,
            )
            if resp.status_code == 401:
                return {"success": False, "message": "Access Token 无效或已过期"}
            self._ensure_root()
            return {"success": True, "message": "认证成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _ensure_root(self):
        if self._root_id:
            return
        resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/list",
            headers=self._headers(),
            json={"parent_file_id": "root", "limit": 100},
            timeout=30,
        )
        if resp.status_code != 200:
            return
        for item in resp.json().get("items", []):
            if item.get("name") == self.REMOTE_ROOT and item.get("type") == "folder":
                self._root_id = item["file_id"]
                return
        create_resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/create",
            headers=self._headers(),
            json={"parent_file_id": "root", "name": self.REMOTE_ROOT, "type": "folder", "check_name_mode": "refuse"},
            timeout=30,
        )
        if create_resp.status_code in (200, 201):
            self._root_id = create_resp.json().get("file_id", "")

    def _get_parent_id(self, remote_path: str) -> str:
        if not remote_path:
            return self._root_id
        parts = remote_path.strip("/").split("/")
        parent_id = self._root_id
        for part in parts:
            resp = requests.post(
                f"{self.API_BASE}/adrive/v1.0/openFile/list",
                headers=self._headers(),
                json={"parent_file_id": parent_id, "limit": 200},
                timeout=30,
            )
            if resp.status_code != 200:
                return parent_id
            found = False
            for item in resp.json().get("items", []):
                if item.get("name") == part and item.get("type") == "folder":
                    parent_id = item["file_id"]
                    found = True
                    break
            if not found:
                create_resp = requests.post(
                    f"{self.API_BASE}/adrive/v1.0/openFile/create",
                    headers=self._headers(),
                    json={"parent_file_id": parent_id, "name": part, "type": "folder", "check_name_mode": "refuse"},
                    timeout=30,
                )
                if create_resp.status_code in (200, 201):
                    parent_id = create_resp.json().get("file_id", parent_id)
        return parent_id

    def is_authenticated(self) -> bool:
        if not self._access_token:
            return False
        try:
            resp = requests.post(
                f"{self.API_BASE}/adrive/v1.0/openFile/list",
                headers=self._headers(),
                json={"parent_file_id": "root", "limit": 1},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def list_files(self, remote_path: str = "") -> list:
        self._ensure_root()
        parent_id = self._root_id
        if remote_path:
            parent_id = self._get_parent_id(remote_path)
        if not parent_id:
            return []
        resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/list",
            headers=self._headers(),
            json={"parent_file_id": parent_id, "limit": 200},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        items = []
        for item in resp.json().get("items", []):
            ts = self._parse_mtime(item.get("updated_at", ""))
            name = item.get("name", "")
            items.append(
                CloudFileInfo(
                    path=f"{remote_path}/{name}" if remote_path else name,
                    name=name,
                    size=item.get("size", 0),
                    modified_time=ts,
                    is_dir=item.get("type") == "folder",
                    cloud_id=item.get("file_id", ""),
                )
            )
        return items

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        self._ensure_root()
        parent_dir = os.path.dirname(remote_path)
        filename = os.path.basename(remote_path)
        parent_id = self._get_parent_id(parent_dir) if parent_dir else self._root_id
        if not parent_id:
            return False
        file_size = os.path.getsize(local_path)
        create_resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/create",
            headers=self._headers(),
            json={
                "parent_file_id": parent_id,
                "name": filename,
                "type": "file",
                "size": file_size,
                "check_name_mode": "refuse",
                "content_hash_name": "none",
                "proof_version": "v1",
            },
            timeout=30,
        )
        if create_resp.status_code not in (200, 201):
            return False
        upload_info = create_resp.json()
        upload_url = upload_info.get("upload_url", "")
        if not upload_url:
            return False
        with open(local_path, "rb") as f:
            put_resp = requests.put(upload_url, data=f, timeout=120)
        return put_resp.status_code == 200

    def _find_file_id(self, parent_id: str, filename: str) -> str:
        list_resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/list",
            headers=self._headers(),
            json={"parent_file_id": parent_id, "limit": 200},
            timeout=30,
        )
        if list_resp.status_code != 200:
            return ""
        for item in list_resp.json().get("items", []):
            if item.get("name") == filename:
                return item.get("file_id", "")
        return ""

    def download_file(self, remote_path: str, local_path: str) -> bool:
        self._ensure_root()
        parent_dir = "/".join(remote_path.strip("/").split("/")[:-1])
        filename = remote_path.strip("/").split("/")[-1]
        parent_id = self._get_parent_id(parent_dir) if parent_dir else self._root_id
        if not parent_id:
            return False
        file_id = self._find_file_id(parent_id, filename)
        if not file_id:
            return False
        dl_resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/getDownloadUrl",
            headers=self._headers(),
            json={"file_id": file_id},
            timeout=30,
        )
        if dl_resp.status_code != 200:
            return False
        download_url = dl_resp.json().get("url", "")
        if not download_url:
            return False
        resp = requests.get(download_url, timeout=120, stream=True)
        if resp.status_code != 200:
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True

    def create_folder(self, remote_path: str) -> bool:
        self._ensure_root()
        parts = remote_path.strip("/").split("/")
        parent_dir = "/".join(parts[:-1])
        folder_name = parts[-1]
        parent_id = self._get_parent_id(parent_dir) if parent_dir else self._root_id
        if not parent_id:
            return False
        resp = requests.post(
            f"{self.API_BASE}/adrive/v1.0/openFile/create",
            headers=self._headers(),
            json={"parent_file_id": parent_id, "name": folder_name, "type": "folder", "check_name_mode": "refuse"},
            timeout=30,
        )
        return resp.status_code in (200, 201)
