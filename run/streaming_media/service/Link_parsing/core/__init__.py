# __init__.py
from .xhs import xiaohongshu
from .tiktok import dy
from .weibo import wb
from .twitter import twitter
from .gal import Galgame_manshuo,youxi_pil_new_text,gal_PILimg
from .bangumi_core import bangumi_PILimg
from .majsoul import majsoul_PILimg
from .bilibili import bilibili,download_video_link_prising,download_img


# 定义 __all__ 列表，明确导出的内容
__all__ = ['xiaohongshu', 'dy', 'wb','twitter','youxi_pil_new_text','Galgame_manshuo','bangumi_PILimg','gal_PILimg',
           'majsoul_PILimg','bilibili','download_video_link_prising','download_img']
