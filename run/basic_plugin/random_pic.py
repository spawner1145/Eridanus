import os
import re
import random
import httpx
from httpx._urlparse import urlparse

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.random_str import random_str


def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def today_husband(event: GroupMessageEvent):
        text = str(event.pure_text)
        if not text.startswith("今") or not any(keyword in text for keyword in ["今日", "今天"]):
            return

        url_map = {
            "腿": [
                "https://api.dwo.cc/api/meizi",
            ],
            "黑丝": [
                "https://api.dwo.cc/api/hs_img",
                "https://img.sorahub.site/?tag=black%20pantyhose",
                "https://v2.api-m.com/api/heisi?return=302",
                ""
            ],
            "白丝": [
                "https://api.dwo.cc/api/bs_img",
                "https://img.sorahub.site/?tag=white%20socks",
                "https://v2.api-m.com/api/baisi?return=302",
            ],
            "头像": [
                "https://api.dwo.cc/api/dmtou",
            ],
            "cos": [
                "https://img.sorahub.site",
            ],
        }

        matched_key = next((k for k in url_map if k in text), None)
        url = None
        if matched_key:
            url_list = url_map[matched_key]
            url = random.choice(url_list)
            bot.logger.info(f"今日 {matched_key} API 选择：{url}")

        if not url:
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                content_type = response.headers.get('Content-Type', '')

                if 'image' in content_type:
                    ext = get_image_extension(content_type)
                    img_path = f'data/pictures/cache/{random_str()}{ext}'
                    with open(img_path, 'wb') as f:
                        f.write(response.content)
                    await bot.send(event, [Image(file=img_path)])
                    return

                if 'json' in content_type or response.text.strip().startswith('{'):
                    try:
                        data = response.json()
                    except Exception:
                        await bot.send(event, 'API 返回的 JSON 无法解析喵~')
                        return

                    img_urls = extract_all_urls_from_json(data)
                    if not img_urls:
                        await bot.send(event, 'API 返回了 JSON 但没找到图片 URL 喵~')
                        return

                    img_url = random.choice(img_urls)
                    bot.logger.info(f"发现图片 URL：{img_url}")

                    ext = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                    img_path = f'data/pictures/cache/{random_str()}{ext}'
                    img_response = await client.get(img_url)
                    with open(img_path, 'wb') as f:
                        f.write(img_response.content)

                    await bot.send(event, [Image(file=img_path)])
                    return

                # 其他格式
                await bot.send(event, 'API 返回了未知格式数据喵~')

        except Exception as e:
            bot.logger.error(f'API 请求失败: {e}')
            await bot.send(event, 'api失效了喵，请过一段时间再试试吧')

    def get_image_extension(content_type: str) -> str:
        if 'png' in content_type:
            return '.png'
        elif 'webp' in content_type:
            return '.webp'
        return '.jpg'

    def extract_all_urls_from_json(data):
        urls = []
        img_pattern = re.compile(
            r'https?://[^\s\'"]+\.(?:jpg|jpeg|png|webp|gif|bmp|tiff|svg)(?:\?[^\s\'"]*)?',
            re.IGNORECASE
        )

        def _scan(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    _scan(v)
            elif isinstance(obj, list):
                for v in obj:
                    _scan(v)
            elif isinstance(obj, str):
                matches = img_pattern.findall(obj)
                urls.extend(matches)

        _scan(data)
        return urls
