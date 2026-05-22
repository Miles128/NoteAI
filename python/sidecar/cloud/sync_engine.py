import contextlib
import json
import os
import time

from sidecar.cloud.providers import PROVIDER_MAP, CloudProvider
from utils.logger import logger

SYNC_DIRS = ["Notes", "wiki"]
STATE_FILE = "cloud_sync_state.json"
CONFIG_FILE = "cloud_sync_config.json"


class SyncEngine:
    def __init__(self, workspace_path: str, provider: CloudProvider):
        self._workspace = workspace_path
        self._provider = provider
        self._noteai_dir = os.path.join(workspace_path, "NoteAI")
        self._state_path = os.path.join(self._noteai_dir, STATE_FILE)
        self._config_path = os.path.join(self._noteai_dir, CONFIG_FILE)

    def _ensure_noteai_dir(self):
        os.makedirs(self._noteai_dir, exist_ok=True)

    def _load_state(self) -> dict:
        if not os.path.isfile(self._state_path):
            return {}
        try:
            with open(self._state_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self, state: dict):
        self._ensure_noteai_dir()
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def scan_local_files(self) -> list:
        if not self._workspace or not os.path.isdir(self._workspace):
            return []
        files = []
        for sync_dir in SYNC_DIRS:
            dir_path = os.path.join(self._workspace, sync_dir)
            if not os.path.isdir(dir_path):
                continue
            for root, _dirs, filenames in os.walk(dir_path):
                for fname in filenames:
                    if fname.startswith("."):
                        continue
                    full = os.path.join(root, fname)
                    try:
                        stat = os.stat(full)
                        rel = os.path.relpath(full, self._workspace)
                        files.append({
                            "relative_path": rel,
                            "mtime": stat.st_mtime,
                            "size": stat.st_size,
                        })
                    except OSError:
                        continue
        return files

    def scan_remote_files(self) -> list:
        result = []
        self._scan_remote_recursive("", result)
        return result

    def _scan_remote_recursive(self, remote_path: str, result: list):
        try:
            items = self._provider.list_files(remote_path)
        except Exception as e:
            logger.warning(f"[cloud_sync] list_files failed for {remote_path}: {e}")
            return
        for item in items:
            if item.is_dir:
                self._scan_remote_recursive(item.path, result)
            else:
                result.append({
                    "relative_path": item.path,
                    "mtime": item.modified_time,
                    "size": item.size,
                })

    def _ensure_remote_dirs(self, relative_path: str):
        parts = relative_path.replace("\\", "/").split("/")
        for i in range(1, len(parts)):
            dir_path = "/".join(parts[:i])
            with contextlib.suppress(Exception):
                self._provider.create_folder(dir_path)

    def push(self, progress_callback=None) -> dict:
        local_files = self.scan_local_files()
        remote_files = self.scan_remote_files()
        remote_map = {f["relative_path"]: f for f in remote_files}

        to_upload = []
        for lf in local_files:
            rf = remote_map.get(lf["relative_path"])
            if rf is None or lf["mtime"] > rf["mtime"] + 1:
                to_upload.append(lf)

        if not to_upload:
            return {"success": True, "uploaded": 0, "skipped": len(local_files), "message": "没有需要上传的文件"}

        uploaded = 0
        failed = 0
        total = len(to_upload)
        for i, lf in enumerate(to_upload):
            local_full = os.path.join(self._workspace, lf["relative_path"])
            remote_path = lf["relative_path"].replace("\\", "/")
            try:
                self._ensure_remote_dirs(remote_path)
                ok = self._provider.upload_file(local_full, remote_path)
                if ok:
                    uploaded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"[cloud_sync] upload failed {remote_path}: {e}")
                failed += 1
            if progress_callback:
                progress_callback(i + 1, total, f"上传 {i + 1}/{total}")

        state = self._load_state()
        state["last_push"] = time.time()
        state["last_push_provider"] = self._provider.PROVIDER_NAME
        self._save_state(state)

        return {
            "success": True,
            "uploaded": uploaded,
            "failed": failed,
            "skipped": len(local_files) - uploaded - failed,
            "message": f"上传完成: {uploaded} 成功, {failed} 失败",
        }

    def _classify_remote_files(self, remote_files, local_map):
        to_download = []
        conflicts = []
        for rf in remote_files:
            rel = rf["relative_path"]
            if not any(rel.startswith(d + "/") or rel.startswith(d + "\\") for d in SYNC_DIRS):
                continue
            lf = local_map.get(rel)
            if lf is None:
                to_download.append(rf)
            elif rf["mtime"] > lf["mtime"] + 1:
                conflicts.append(rf)
        for cf in conflicts:
            to_download.append(cf)
        return to_download, conflicts

    def _download_single(self, rf, local_map):
        rel = rf["relative_path"]
        local_full = os.path.join(self._workspace, rel)
        remote_path = rel.replace("\\", "/")
        is_conflict = rel in local_map and rf["mtime"] > local_map[rel]["mtime"] + 1
        if is_conflict and os.path.isfile(local_full):
            stem, ext = os.path.splitext(local_full)
            cloud_version = f"{stem}_cloud_{int(time.time())}{ext}"
            try:
                self._provider.download_file(remote_path, cloud_version)
                return "conflict"
            except Exception:
                return "failed"
        os.makedirs(os.path.dirname(local_full), exist_ok=True)
        ok = self._provider.download_file(remote_path, local_full)
        return "downloaded" if ok else "failed"

    def pull(self, progress_callback=None) -> dict:
        remote_files = self.scan_remote_files()
        local_files = self.scan_local_files()
        local_map = {f["relative_path"]: f for f in local_files}

        to_download, _conflicts = self._classify_remote_files(remote_files, local_map)

        if not to_download:
            return {"success": True, "downloaded": 0, "conflicts": 0, "message": "没有需要下载的文件"}

        downloaded = 0
        conflict_resolved = 0
        failed = 0
        total = len(to_download)
        for i, rf in enumerate(to_download):
            try:
                result = self._download_single(rf, local_map)
                if result == "downloaded":
                    downloaded += 1
                elif result == "conflict":
                    conflict_resolved += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"[cloud_sync] download failed {rf['relative_path']}: {e}")
                failed += 1
            if progress_callback:
                progress_callback(i + 1, total, f"下载 {i + 1}/{total}")

        state = self._load_state()
        state["last_pull"] = time.time()
        state["last_pull_provider"] = self._provider.PROVIDER_NAME
        self._save_state(state)

        return {
            "success": True,
            "downloaded": downloaded,
            "conflicts": conflict_resolved,
            "failed": failed,
            "message": f"下载完成: {downloaded} 成功, {conflict_resolved} 冲突已保留, {failed} 失败",
        }

    def get_status(self) -> dict:
        state = self._load_state()
        local_files = self.scan_local_files()
        return {
            "provider": self._provider.PROVIDER_NAME,
            "authenticated": self._provider.is_authenticated(),
            "local_file_count": len(local_files),
            "last_push": state.get("last_push"),
            "last_pull": state.get("last_pull"),
            "last_push_provider": state.get("last_push_provider", ""),
            "last_pull_provider": state.get("last_pull_provider", ""),
        }

    @staticmethod
    def load_provider_config(workspace_path: str, provider_name: str) -> dict:
        config_path = os.path.join(workspace_path, "NoteAI", CONFIG_FILE)
        if not os.path.isfile(config_path):
            return {}
        try:
            with open(config_path, encoding="utf-8") as f:
                all_configs = json.load(f)
            return all_configs.get(provider_name, {})
        except Exception:
            return {}

    @staticmethod
    def save_provider_config(workspace_path: str, provider_name: str, config: dict):
        noteai_dir = os.path.join(workspace_path, "NoteAI")
        os.makedirs(noteai_dir, exist_ok=True)
        config_path = os.path.join(noteai_dir, CONFIG_FILE)
        all_configs = {}
        if os.path.isfile(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    all_configs = json.load(f)
            except Exception:
                all_configs = {}
        all_configs[provider_name] = config
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(all_configs, f, ensure_ascii=False, indent=2)

    @staticmethod
    def create_provider(provider_name: str, config: dict) -> CloudProvider:
        cls = PROVIDER_MAP.get(provider_name)
        if cls is None:
            raise ValueError(f"Unknown provider: {provider_name}")
        return cls(config)
