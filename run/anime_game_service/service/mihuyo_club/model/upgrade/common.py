from typing import Union, Optional, Dict, TYPE_CHECKING
from developTools.utils.logger import get_logger
logger=get_logger()
from pydantic_settings import BaseSettings

from ..._version import __version__
from ...model.common import data_path
from ...model.upgrade.configV2 import Preference, SaltConfig, DeviceConfig, GoodListImageConfig
from ...model.upgrade.dataV2 import UserData, UserAccount, PluginData, plugin_data_path

if TYPE_CHECKING:
    IntStr = Union[int, str]

__all__ = ["plugin_data_path_v1", "PluginDataV1"]
plugin_data_path_v1 = data_path / "plugin_data.json"


class PluginDataV1(BaseSettings):
    version: str = __version__
    """创建插件数据文件时的版本号"""
    preference: Preference = Preference()
    """偏好设置"""
    salt_config: SaltConfig = SaltConfig()
    """生成Headers - DS所用salt值"""
    device_config: DeviceConfig = DeviceConfig()
    """设备信息"""
    good_list_image_config: GoodListImageConfig = GoodListImageConfig()
    """商品列表输出图片设置"""
    user_bind: Optional[Dict[str, str]] = {}
    '''不同NoneBot适配器平台的用户数据绑定关系（如QQ聊天和QQ频道）(空用户数据:被绑定用户数据)'''
    users: Dict[str, UserData] = {}
    '''所有用户数据'''




