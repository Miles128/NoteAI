from sidecar.cloud.providers.aliyun import AliyunProvider
from sidecar.cloud.providers.baidu import BaiduProvider
from sidecar.cloud.providers.base import CloudFileInfo, CloudProvider
from sidecar.cloud.providers.icloud import ICloudProvider
from sidecar.cloud.providers.jianguoyun import JianguoyunProvider
from sidecar.cloud.providers.onedrive import OneDriveProvider
from sidecar.cloud.providers.pan123 import Pan123Provider
from sidecar.cloud.providers.tencent_cos import TencentCOSProvider

ALL_PROVIDERS = [
    OneDriveProvider,
    BaiduProvider,
    AliyunProvider,
    Pan123Provider,
    JianguoyunProvider,
    TencentCOSProvider,
    ICloudProvider,
]

PROVIDER_MAP = {p.PROVIDER_NAME: p for p in ALL_PROVIDERS}

__all__ = [
    "CloudProvider",
    "CloudFileInfo",
    "OneDriveProvider",
    "BaiduProvider",
    "AliyunProvider",
    "Pan123Provider",
    "JianguoyunProvider",
    "TencentCOSProvider",
    "ICloudProvider",
    "ALL_PROVIDERS",
    "PROVIDER_MAP",
]
