import os
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class JianguoyunProvider(CloudProvider):
    PROVIDER_NAME = "jianguoyun"
    DISPLAY_NAME = "坚果云"
    AUTH_TYPE = "credentials"
    AUTH_FIELDS = [
        {"key": "username", "label": "用户名", "type": "text", "placeholder": "坚果云账号"},
        {"key": "app_password", "label": "应用密码", "type": "password", "placeholder": "坚果云第三方应用密码"},
    ]

    DAV_BASE = "https://dav.jianguoyun.com/dav/"
    REMOTE_ROOT = "NoteAI"

    def __init__(self, config: dict):
        super().__init__(config)
        self._username = config.get("username", "")
        self._app_password = config.get("app_password", "")

    def _auth(self):
        return (self._username, self._app_password)

    def _url(self, remote_path: str = "") -> str:
        if remote_path:
            return f"{self.DAV_BASE}{self.REMOTE_ROOT}/{remote_path}"
        return f"{self.DAV_BASE}{self.REMOTE_ROOT}/"

    def authenticate(self, credentials: dict) -> dict:
        username = credentials.get("username", self._username)
        app_password = credentials.get("app_password", self._app_password)
        if not username or not app_password:
            return {"success": False, "message": "请提供用户名和应用密码"}
        self._username = username
        self._app_password = app_password
        try:
            resp = requests.request(
                "PROPFIND",
                self.DAV_BASE,
                auth=self._auth(),
                headers={"Depth": "0"},
                timeout=10,
            )
            if resp.status_code in (200, 207):
                return {"success": True, "message": "认证成功"}
            return {"success": False, "message": "认证失败，请检查用户名和应用密码"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def is_authenticated(self) -> bool:
        if not self._username or not self._app_password:
            return False
        try:
            resp = requests.request(
                "PROPFIND",
                self.DAV_BASE,
                auth=self._auth(),
                headers={"Depth": "0"},
                timeout=10,
            )
            return resp.status_code in (200, 207)
        except Exception:
            return False

    def _parse_propstat(self, propstat, ns: dict) -> tuple:
        is_dir = False
        size = 0
        mtime = 0.0
        if propstat is None:
            return is_dir, size, mtime
        res_type = propstat.find("d:resourcetype", ns)
        if res_type is not None and res_type.find("d:collection", ns) is not None:
            is_dir = True
        size_elem = propstat.find("d:getcontentlength", ns)
        if size_elem is not None and size_elem.text:
            size = int(size_elem.text)
        mtime_elem = propstat.find("d:getlastmodified", ns)
        if mtime_elem is not None and mtime_elem.text:
            try:
                dt = parsedate_to_datetime(mtime_elem.text)
                mtime = dt.timestamp()
            except Exception:
                mtime = 0.0
        return is_dir, size, mtime

    def list_files(self, remote_path: str = "") -> list:
        url = self._url(remote_path)
        resp = requests.request(
            "PROPFIND",
            url,
            auth=self._auth(),
            headers={"Depth": "1"},
            timeout=30,
        )
        if resp.status_code not in (200, 207):
            return []
        items = []
        try:
            root = ET.fromstring(resp.content)
            ns = {"d": "DAV:"}
            for resp_elem in root.findall("d:response", ns):
                href_elem = resp_elem.find("d:href", ns)
                if href_elem is None:
                    continue
                href = href_elem.text or ""
                name = href.rstrip("/").split("/")[-1]
                if not name:
                    continue
                propstat = resp_elem.find("d:propstat/d:prop", ns)
                is_dir, size, mtime = self._parse_propstat(propstat, ns)
                items.append(
                    CloudFileInfo(
                        path=f"{remote_path}/{name}" if remote_path else name,
                        name=name,
                        size=size,
                        modified_time=mtime,
                        is_dir=is_dir,
                        cloud_id=href,
                    )
                )
        except ET.ParseError:
            pass
        return items[1:] if items else items

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        url = self._url(remote_path)
        parent = "/".join(remote_path.split("/")[:-1])
        if parent:
            self.create_folder(parent)
        with open(local_path, "rb") as f:
            resp = requests.put(url, auth=self._auth(), data=f, timeout=120)
        return resp.status_code in (200, 201, 204)

    def download_file(self, remote_path: str, local_path: str) -> bool:
        url = self._url(remote_path)
        resp = requests.get(url, auth=self._auth(), timeout=120, stream=True)
        if resp.status_code != 200:
            return False
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True

    def create_folder(self, remote_path: str) -> bool:
        parts = remote_path.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            url = self._url(current)
            resp = requests.request("MKCOL", url, auth=self._auth(), timeout=10)
            if resp.status_code not in (200, 201, 405):
                return False
        return True
