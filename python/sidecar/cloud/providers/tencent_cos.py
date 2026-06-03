import os
from datetime import datetime

from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider


class TencentCOSProvider(CloudProvider):
    PROVIDER_NAME = "tencent_cos"
    DISPLAY_NAME = "腾讯云COS"
    AUTH_TYPE = "credentials"
    AUTH_FIELDS = [
        {"key": "secret_id", "label": "Secret ID", "type": "text", "placeholder": "腾讯云 SecretId"},
        {"key": "secret_key", "label": "Secret Key", "type": "password", "placeholder": "腾讯云 SecretKey"},
        {"key": "bucket", "label": "Bucket", "type": "text", "placeholder": "存储桶名称，如 noteai-1250000000"},
        {"key": "region", "label": "Region", "type": "text", "placeholder": "地域，如 ap-guangzhou"},
    ]

    REMOTE_PREFIX = "NoteAI"

    def __init__(self, config: dict):
        super().__init__(config)
        self._secret_id = config.get("secret_id", "")
        self._secret_key = config.get("secret_key", "")
        self._bucket = config.get("bucket", "")
        self._region = config.get("region", "")
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client
        try:
            from qcloud_cos import CosConfig, CosS3Client  # noqa: PLC0415
            conf = CosConfig(Region=self._region, SecretId=self._secret_id, SecretKey=self._secret_key)
            self._client = CosS3Client(conf)
            return self._client
        except ImportError:
            return None

    def _parse_mtime(self, mtime_str: str) -> float:
        if not mtime_str:
            return 0.0
        try:
            dt = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0

    def authenticate(self, credentials: dict) -> dict:
        self._secret_id = credentials.get("secret_id", self._secret_id)
        self._secret_key = credentials.get("secret_key", self._secret_key)
        self._bucket = credentials.get("bucket", self._bucket)
        self._region = credentials.get("region", self._region)
        if not all([self._secret_id, self._secret_key, self._bucket, self._region]):
            return {"success": False, "message": "请提供完整的 SecretId、SecretKey、Bucket 和 Region"}
        self._client = None
        client = self._get_client()
        if client is None:
            return {"success": False, "message": "请安装 cos-python-sdk-v5: uv pip install cos-python-sdk-v5"}
        try:
            client.head_bucket(Bucket=self._bucket)
            return {"success": True, "message": "认证成功"}
        except Exception as e:
            self._client = None
            return {"success": False, "message": f"认证失败: {e}"}

    def is_authenticated(self) -> bool:
        if not all([self._secret_id, self._secret_key, self._bucket, self._region]):
            return False
        client = self._get_client()
        if client is None:
            return False
        try:
            client.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False

    def list_files(self, remote_path: str = "") -> list:
        client = self._get_client()
        if client is None:
            return []
        prefix = f"{self.REMOTE_PREFIX}/{remote_path}/" if remote_path else f"{self.REMOTE_PREFIX}/"
        try:
            resp = client.list_objects(Bucket=self._bucket, Prefix=prefix, Delimiter="/")
        except Exception:
            return []
        items = []
        for prefix_obj in resp.get("CommonPrefixes", []):
            p = prefix_obj.get("Prefix", "")
            name = p.rstrip("/").split("/")[-1]
            rel = p[len(self.REMOTE_PREFIX) + 1:].rstrip("/")
            items.append(CloudFileInfo(
                path=rel,
                name=name,
                size=0,
                modified_time=0.0,
                is_dir=True,
                cloud_id=p,
            ))
        for obj in resp.get("Contents", []):
            key = obj.get("Key", "")
            name = key.split("/")[-1]
            if not name:
                continue
            rel = key[len(self.REMOTE_PREFIX) + 1:]
            ts = self._parse_mtime(obj.get("LastModified", ""))
            items.append(CloudFileInfo(
                path=rel,
                name=name,
                size=obj.get("Size", 0),
                modified_time=ts,
                is_dir=False,
                cloud_id=key,
            ))
        return items

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        key = f"{self.REMOTE_PREFIX}/{remote_path}"
        try:
            client.upload_file(Bucket=self._bucket, Key=key, LocalFilePath=local_path)
            return True
        except Exception:
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        key = f"{self.REMOTE_PREFIX}/{remote_path}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        try:
            client.download_file(Bucket=self._bucket, Key=key, DestFilePath=local_path)
            return True
        except Exception:
            return False

    def create_folder(self, remote_path: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        key = f"{self.REMOTE_PREFIX}/{remote_path}/"
        try:
            client.put_object(Bucket=self._bucket, Key=key, Body=b"")
            return True
        except Exception:
            return False
