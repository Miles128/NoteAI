import os
import time
from datetime import datetime

import requests

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class OneDriveProvider(CloudProvider):
    PROVIDER_NAME = "onedrive"
    DISPLAY_NAME = "OneDrive"
    AUTH_TYPE = "oauth_device"
    AUTH_FIELDS = [
        {"key": "client_id", "label": "Client ID", "type": "text", "placeholder": "Azure 应用的 Client ID"},
    ]

    SCOPES = ["Files.ReadWrite.All"]
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    AUTHORITY = "https://login.microsoftonline.com/common"
    REMOTE_ROOT = "/NoteAI"

    def __init__(self, config: dict):
        super().__init__(config)
        self._access_token = config.get("access_token", "")
        self._client_id = config.get("client_id", "")
        self._token_expiry = config.get("token_expiry", 0)

    def _parse_mtime(self, mtime_str: str) -> float:
        if not mtime_str:
            return 0.0
        try:
            dt = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0

    def authenticate(self, credentials: dict) -> dict:
        try:
            import msal  # noqa: PLC0415
        except ImportError:
            return {"success": False, "message": "请安装 msal: uv pip install msal"}

        client_id = credentials.get("client_id", self._client_id)
        if not client_id:
            return {"success": False, "message": "请提供 Client ID"}

        app = msal.PublicClientApplication(client_id, authority=self.AUTHORITY)
        flow = app.initiate_device_flow(scopes=self.SCOPES)
        if "user_code" not in flow:
            return {"success": False, "message": "无法启动设备授权流程"}

        result = app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self._access_token = result["access_token"]
            self._client_id = client_id
            self._token_expiry = time.time() + result.get("expires_in", 3600)
            return {
                "success": True,
                "message": "认证成功",
                "user_code": flow.get("user_code", ""),
                "verification_uri": flow.get("verification_uri", ""),
            }
        return {"success": False, "message": result.get("error_description", "认证失败")}

    def _headers(self):
        return {"Authorization": f"Bearer {self._access_token}"}

    def is_authenticated(self) -> bool:
        if not self._access_token:
            return False
        if time.time() > self._token_expiry:
            return False
        try:
            resp = requests.get(f"{self.GRAPH_BASE}/me", headers=self._headers(), timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def list_files(self, remote_path: str = "") -> list:
        path = f"{self.REMOTE_ROOT}/{remote_path}" if remote_path else self.REMOTE_ROOT
        url = f"{self.GRAPH_BASE}/me/drive/root:{path}:/children"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code != 200:
            return []
        items = []
        for item in resp.json().get("value", []):
            ts = self._parse_mtime(item.get("lastModifiedDateTime", ""))
            items.append(
                CloudFileInfo(
                    path=f"{remote_path}/{item['name']}" if remote_path else item["name"],
                    name=item["name"],
                    size=item.get("size", 0),
                    modified_time=ts,
                    is_dir="folder" in item,
                    cloud_id=item.get("id", ""),
                )
            )
        return items

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        path = f"{self.REMOTE_ROOT}/{remote_path}"
        url = f"{self.GRAPH_BASE}/me/drive/root:{path}:/content"
        with open(local_path, "rb") as f:
            resp = requests.put(url, headers=self._headers(), data=f, timeout=120)
        return resp.status_code in (200, 201)

    def download_file(self, remote_path: str, local_path: str) -> bool:
        path = f"{self.REMOTE_ROOT}/{remote_path}"
        url = f"{self.GRAPH_BASE}/me/drive/root:{path}:/content"
        resp = requests.get(url, headers=self._headers(), timeout=120, stream=True)
        if resp.status_code != 200:
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True

    def create_folder(self, remote_path: str) -> bool:
        parts = remote_path.rstrip("/").split("/")
        parent = f"{self.REMOTE_ROOT}/{'/'.join(parts[:-1])}" if len(parts) > 1 else self.REMOTE_ROOT
        url = f"{self.GRAPH_BASE}/me/drive/root:{parent}:/children"
        body = {"name": parts[-1], "folder": {}}
        resp = requests.post(
            url, headers={**self._headers(), "Content-Type": "application/json"}, json=body, timeout=30
        )
        return resp.status_code in (200, 201)
