from pathlib import Path

import pytest
from sidecar.cloud.sync_engine import CONFIG_FILE, SyncEngine


class DummyProvider:
    PROVIDER_NAME = "dummy"

    def download_file(self, _remote_path: str, local_path: str) -> bool:
        Path(local_path).write_text("downloaded", encoding="utf-8")
        return True


def test_download_rejects_remote_path_traversal(tmp_path: Path) -> None:
    engine = SyncEngine(str(tmp_path), DummyProvider())

    with pytest.raises(ValueError, match="非法"):
        engine._download_single(
            {"relative_path": "Notes/../../outside.md", "mtime": 1},
            {},
        )

    assert not (tmp_path.parent / "outside.md").exists()


def test_provider_config_uses_runtime_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sidecar.cloud.sync_engine.store_credential", lambda *_args: True)
    monkeypatch.setattr("sidecar.cloud.sync_engine.load_credential", lambda *_args: "secret")

    SyncEngine.save_provider_config(str(tmp_path), "dummy", {"token": "secret", "root": "notes"})

    assert (tmp_path / ".noteai" / CONFIG_FILE).is_file()
    assert not (tmp_path / "NoteAI" / CONFIG_FILE).exists()
    assert SyncEngine.load_provider_config(str(tmp_path), "dummy") == {
        "token": "secret",
        "root": "notes",
    }


def test_provider_config_migrates_legacy_file(tmp_path: Path) -> None:
    legacy = tmp_path / "NoteAI" / CONFIG_FILE
    legacy.parent.mkdir()
    legacy.write_text('{"dummy": {"root": "legacy"}}', encoding="utf-8")

    assert SyncEngine.load_provider_config(str(tmp_path), "dummy") == {"root": "legacy"}
    assert (tmp_path / ".noteai" / CONFIG_FILE).is_file()
    assert not legacy.exists()
