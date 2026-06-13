import os

import requests

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class Pan123Provider(CloudProvider):
    PROVIDER_NAME = "pan123"
    DISPLAY_NAME = "123云盘"
    AUTH_TYPE = "credentials"
    AUTH_FIELDS = [
        {"key": "client_id", "label": "Client ID", "type": "text", "placeholder": "123云盘开放平台 Client ID"},
        {
            "key": "client_secret",
            "label": "Client Secret",
            "type": "password",
            "placeholder": "123云盘开放平台 Client Secret",
        },
    ]

    API_BASE = "https://open.123pan.com"
    REMOTE_ROOT_NAME = "NoteAI"

    def __init__(self, config: dict):
        super().__init__(config)
        self._client_id = config.get("client_id", "")
        self._client_secret = config.get("client_secret", "")
        self._access_token = config.get("access_token", "")
        self._root_id = config.get("root_id", 0)

    def _headers(self):
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    def authenticate(self, credentials: dict) -> dict:
        client_id = credentials.get("client_id", self._client_id)
        client_secret = credentials.get("client_secret", self._client_secret)
        if not client_id or not client_secret:
            return {"success": False, "message": "请提供 Client ID 和 Client Secret"}
        self._client_id = client_id
        self._client_secret = client_secret
        try:
            resp = requests.post(
                f"{self.API_BASE}/api/v1/access_token",
                json={"client_id": client_id, "client_secret": client_secret},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                return {"success": False, "message": data.get("message", "认证失败")}
            self._access_token = data["data"]["access_token"]
            self._ensure_root()
            return {"success": True, "message": "认证成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _ensure_root(self):
        if self._root_id:
            return
        resp = requests.get(
            f"{self.API_BASE}/api/file/list",
            headers=self._headers(),
            params={"parentFileId": 0, "limit": 200},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            return
        for item in data.get("data", {}).get("InfoList", []):
            if item.get("FileName") == self.REMOTE_ROOT_NAME and item.get("IsDirectory"):
                self._root_id = item.get("FileId", 0)
                return
        create_resp = requests.post(
            f"{self.API_BASE}/api/file/create",
            headers=self._headers(),
            json={"driveId": 0, "etag": "", "fileName": self.REMOTE_ROOT_NAME, "parentFileId": 0, "size": 0, "type": 1},
            timeout=30,
        )
        cdata = create_resp.json()
        if cdata.get("code") == 0:
            self._root_id = cdata.get("data", {}).get("Info", {}).get("FileId", 0)

    def is_authenticated(self) -> bool:
        if not self._access_token:
            return False
        try:
            resp = requests.get(
                f"{self.API_BASE}/api/user/info",
                headers=self._headers(),
                timeout=10,
            )
            return resp.json().get("code") == 0
        except Exception:
            return False

    def list_files(self, remote_path: str = "") -> list:
        self._ensure_root()
        parent_id = self._root_id
        if remote_path:
            parent_id = self._resolve_path(remote_path)
        if not parent_id:
            return []
        resp = requests.get(
            f"{self.API_BASE}/api/file/list",
            headers=self._headers(),
            params={"parentFileId": parent_id, "limit": 200},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            return []
        items = []
        for item in data.get("data", {}).get("InfoList", []):
            mtime = item.get("UpdateAt", "") or item.get("CreateAt", "")
            ts = 0.0
            if mtime:
                try:
                    ts = float(mtime)
                except (ValueError, TypeError):
                    ts = 0.0
            name = item.get("FileName", "")
            items.append(
                CloudFileInfo(
                    path=f"{remote_path}/{name}" if remote_path else name,
                    name=name,
                    size=item.get("Size", 0),
                    modified_time=ts,
                    is_dir=item.get("IsDirectory", False),
                    cloud_id=str(item.get("FileId", "")),
                )
            )
        return items

    def _resolve_path(self, remote_path: str) -> int:
        parts = remote_path.strip("/").split("/")
        current_id = self._root_id
        for part in parts:
            resp = requests.get(
                f"{self.API_BASE}/api/file/list",
                headers=self._headers(),
                params={"parentFileId": current_id, "limit": 200},
                timeout=30,
            )
            data = resp.json()
            if data.get("code") != 0:
                return current_id
            found = False
            for item in data.get("data", {}).get("InfoList", []):
                if item.get("FileName") == part and item.get("IsDirectory"):
                    current_id = item.get("FileId", 0)
                    found = True
                    break
            if not found:
                create_resp = requests.post(
                    f"{self.API_BASE}/api/file/create",
                    headers=self._headers(),
                    json={"driveId": 0, "etag": "", "fileName": part, "parentFileId": current_id, "size": 0, "type": 1},
                    timeout=30,
                )
                cdata = create_resp.json()
                if cdata.get("code") == 0:
                    current_id = cdata.get("data", {}).get("Info", {}).get("FileId", current_id)
        return current_id

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        self._ensure_root()
        parent_dir = os.path.dirname(remote_path)
        filename = os.path.basename(remote_path)
        parent_id = self._resolve_path(parent_dir) if parent_dir else self._root_id
        if not parent_id:
            return False
        file_size = os.path.getsize(local_path)
        upload_resp = requests.post(
            f"{self.API_BASE}/api/file/upload",
            headers=self._headers(),
            json={
                "driveId": 0,
                "duplicate": 2,
                "etag": "",
                "fileName": filename,
                "parentFileId": parent_id,
                "size": file_size,
                "type": 0,
            },
            timeout=30,
        )
        data = upload_resp.json()
        if data.get("code") != 0:
            return False
        upload_url = data.get("data", {}).get("UploadURL", "")
        if not upload_url:
            return False
        with open(local_path, "rb") as f:
            put_resp = requests.put(upload_url, data=f, timeout=120)
        return put_resp.status_code == 200

    def _find_file_id(self, parent_id: int, filename: str) -> int:
        list_resp = requests.get(
            f"{self.API_BASE}/api/file/list",
            headers=self._headers(),
            params={"parentFileId": parent_id, "limit": 200},
            timeout=30,
        )
        ldata = list_resp.json()
        if ldata.get("code") != 0:
            return 0
        for item in ldata.get("data", {}).get("InfoList", []):
            if item.get("FileName") == filename:
                return item.get("FileId", 0)
        return 0

    def download_file(self, remote_path: str, local_path: str) -> bool:
        self._ensure_root()
        parent_dir = "/".join(remote_path.strip("/").split("/")[:-1])
        filename = remote_path.strip("/").split("/")[-1]
        parent_id = self._resolve_path(parent_dir) if parent_dir else self._root_id
        if not parent_id:
            return False
        file_id = self._find_file_id(parent_id, filename)
        if not file_id:
            return False
        dl_resp = requests.get(
            f"{self.API_BASE}/api/file/download/info",
            headers=self._headers(),
            params={"FileId": file_id},
            timeout=30,
        )
        ddata = dl_resp.json()
        if ddata.get("code") != 0:
            return False
        download_url = ddata.get("data", {}).get("DownloadURL", "")
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
        parent_id = self._resolve_path(parent_dir) if parent_dir else self._root_id
        if not parent_id:
            return False
        resp = requests.post(
            f"{self.API_BASE}/api/file/create",
            headers=self._headers(),
            json={"driveId": 0, "etag": "", "fileName": folder_name, "parentFileId": parent_id, "size": 0, "type": 1},
            timeout=30,
        )
        return resp.json().get("code") == 0
