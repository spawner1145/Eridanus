import base64
import json
from typing import Optional, Dict, Any

from qzone_api import QzoneApi

from run.qq_zone.service.QzoneResponseParser import QzoneResponseParser

from loguru import logger
class QzoneApiFixed(QzoneApi):

    async def _send_zone_with_pic(self,target_qq: int,pic_path: str,content: str, cookies: dict, g_tk: int) -> Optional[Dict[str, Any]]:
        '''
        上传图片
        :param pic_path: 图片路径
        :param cookies: cookies
        :param g_tk: g_tk
        :return: 图片上传结果
        '''
        with open(pic_path, 'rb') as f:
            image_data = f.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
        skey = cookies.get('skey', '')
        p_skey =cookies.get('p_skey', '')

        upload_url = f"https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image?g_tk={g_tk}&&g_tk={g_tk}"

        form_data = {
            'filename': 'filename',
            'uin': target_qq,
            'skey': skey,
            'zzpaneluin': target_qq,
            'zzpanelkey': '',
            'p_uin': target_qq,
            'p_skey': p_skey,
            'qzonetoken': '',  # 可能需要从页面获取
            'uploadtype': '1',
            'albumtype': '7',
            'exttype': '0',
            'refer': 'shuoshuo',
            'output_type': 'jsonhtml',
            'charset': 'utf-8',
            'output_charset': 'utf-8',
            'upload_hd': '1',
            'hd_width': '2048',
            'hd_height': '10000',
            'hd_quality': '96',
            'backUrls': 'http://upbak.photo.qzone.qq.com/cgi-bin/upload/cgi_upload_image,http://119.147.64.75/cgi-bin/upload/cgi_upload_image',
            'url': f'https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image?g_tk={g_tk}',
            'base64': '1',
            'jsonhtml_callback': 'callback',
            'picfile': base64_image  # Base64 编码的图片数据
        }
        cookies_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        response=await self._make_post_request(url=upload_url, data=form_data, cookies=cookies_str)
        richval = QzoneResponseParser.extract_richval(response)
        pic_bo = QzoneResponseParser.extract_pic_bo(response)

        logger.info(f"上传图片成功: {response}")
        """发送说说参数解析"""
        params = {
        "syn_tweet_verson": 1,
        "paramstr": 1,
        "pic_template": "",
        "richtype": 1,
        "richval": richval,
        "special_url": "",
        "subrichtype": 1,
        "pic_bo": pic_bo,
        "who": 1,
        "con": content,
        "feedversion": 1,
        "ver": 1,
        "ugc_right": 1,
        "to_sign": 0,
        "hostuin": target_qq,
        "code_version": 1,
        "format": "fs",
        "qzreferrer": f"https://user.qzone.qq.com/{target_qq}"
        }
        try:
            return await self._make_post_request(url=f"{self.send_url}?&g_tk={g_tk}", data=params, cookies=cookies_str)
        except Exception as e:
            logger.error(f"发送说说失败: {e}")
            return None
