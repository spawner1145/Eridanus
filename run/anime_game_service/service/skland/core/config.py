import random
from pathlib import Path
from typing import Any, Literal

from developTools.utils.logger import get_logger
logger=get_logger()
from pydantic import Field
from pydantic import BaseModel
from pydantic import AnyUrl as Url
#from nonebot.compat import PYDANTIC_V2
#import nonebot_plugin_localstore as store
#from nonebot.plugin import get_plugin_config

RES_DIR: Path = Path(__file__).parent / "resources"
TEMPLATES_DIR: Path = RES_DIR / "templates"
Building_Dir=RES_DIR / 'images' / 'ark_card' / "building"
career_dir=RES_DIR / 'images' / 'ark_card' / "career"
card_img_dir=RES_DIR / 'images' / 'ark_card' / "card_img"
CACHE_DIR = RES_DIR / "cache"
RESOURCE_ROUTES = ["portrait", "skill", "avatar"]







#config = get_plugin_config(Config).skland
