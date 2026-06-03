from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CloudFileInfo:
    path: str
    name: str
    size: int
    modified_time: float
    is_dir: bool = False
    cloud_id: str = ""


class CloudProvider(ABC):
    PROVIDER_NAME: str = ""
    DISPLAY_NAME: str = ""
    AUTH_TYPE: str = ""
    AUTH_FIELDS: list = field(default_factory=list)

    def __init__(self, config: dict):
        self._config = config or {}

    @abstractmethod
    def authenticate(self, credentials: dict) -> dict:
        ...

    @abstractmethod
    def list_files(self, remote_path: str = "") -> list:
        ...

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        ...

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> bool:
        ...

    @abstractmethod
    def create_folder(self, remote_path: str) -> bool:
        ...

    @abstractmethod
    def is_authenticated(self) -> bool:
        ...
