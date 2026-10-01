import asyncio
import logging
import os
from typing import Optional
from httpx import AsyncClient, Limits, Timeout

logger = logging.getLogger(__name__)

API_URL = "https://api.animetrace.com/v1/search"
MODEL_LIST_URL = "https://api.animetrace.com/v1/model/list"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Origin": "https://www.animetrace.com",
    "Referer": "https://www.animetrace.com/",
    "Accept": "application/json, text/plain, */*",
}


def _format_character_results(data_list: list) -> tuple[str, str]:
    if not data_list:
        return "", ""

    primary_lines = ["角色识别搜索结果："]
    detail_lines = []

    first_box = data_list[0]
    first_characters = first_box.get("character", [])
    if first_box.get("not_confident"):
        primary_lines.append("【提示：识别置信度较低，以下为推测候选】")

    for idx, item in enumerate(first_characters[:5], 1):
        work = item.get("work", "未知作品")
        char_name = item.get("character", "未知角色")
        primary_lines.append(f"{idx}. 《{work}》 - {char_name}")

    if len(data_list) > 1:
        detail_lines.append(f"共检测到 {len(data_list)} 个角色区域：")
        for b_idx, box in enumerate(data_list, 1):
            chars = box.get("character", [])
            nc = " (低置信度)" if box.get("not_confident") else ""
            top_char = f"《{chars[0].get('work', '未知')}》-{chars[0].get('character', '未知')}" if chars else "未匹配"
            detail_lines.append(f"区域 {b_idx}{nc}: {top_char}")
    elif len(first_characters) > 5:
        detail_lines.append("更多候选角色：")
        for idx, item in enumerate(first_characters[5:10], 6):
            work = item.get("work", "未知作品")
            char_name = item.get("character", "未知角色")
            detail_lines.append(f"{idx}. 《{work}》 - {char_name}")

    primary_str = "\n".join(primary_lines) + "\n" if len(primary_lines) > 1 else ""
    detail_str = "\n".join(detail_lines) + "\n" if detail_lines else ""
    return primary_str, detail_str


async def _execute_search_request(client: AsyncClient, form_data: dict, files: Optional[dict] = None) -> Optional[dict]:
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            if files:
                resp = await client.post(API_URL, headers=DEFAULT_HEADERS, data=form_data, files=files, timeout=30.0)
            else:
                resp = await client.post(API_URL, headers=DEFAULT_HEADERS, data=form_data, timeout=30.0)

            if resp.status_code == 429:
                if attempt < max_retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                logger.warning("AnimeTrace API 触发频率限制 (429)")
                return None

            resp_json = resp.json()
            if resp_json.get("code") == 17737:
                if attempt < max_retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                logger.warning(f"AnimeTrace 提示请求过频: {resp_json}")
                return None

            return resp_json
        except Exception as err:
            if attempt < max_retries:
                await asyncio.sleep(1.0)
                continue
            logger.error(f"AnimeTrace 请求异常: {err}")
            return None
    return None


async def anime_trace(image_source) -> list[str, str, bool]:
    """
    AnimeTrace 角色识别及 AI 作画检测接口。
    返回格式兼容原有规范: [主要识别结果文本, 详细/备选结果文本, 是否为AI创作(bool)]
    """
    base_data = {
        "is_multi": "1",
        "ai_detect": "1",
    }

    limits = Limits(max_keepalive_connections=5, max_connections=10)
    timeout = Timeout(30.0, connect=10.0)

    async with AsyncClient(trust_env=False, limits=limits, timeout=timeout) as client:
        image_bytes: Optional[bytes] = None
        filename = "image.jpg"

        if isinstance(image_source, str) and (image_source.startswith("http://") or image_source.startswith("https://")):
            try:
                dl_headers = {"User-Agent": DEFAULT_HEADERS["User-Agent"]}
                dl_resp = await client.get(image_source, headers=dl_headers, timeout=15.0)
                if dl_resp.status_code == 200 and dl_resp.content:
                    image_bytes = dl_resp.content
                    if "image/png" in dl_resp.headers.get("Content-Type", ""):
                        filename = "image.png"
                    elif "image/webp" in dl_resp.headers.get("Content-Type", ""):
                        filename = "image.webp"
            except Exception as dl_err:
                logger.warning(f"本地预下载图片失败，将直接尝试向 AnimeTrace 传递 url: {dl_err}")

            if image_bytes:
                files = {"file": (filename, image_bytes, "image/jpeg")}
                res_json = await _execute_search_request(client, base_data.copy(), files=files)
            else:
                data_with_url = base_data.copy()
                data_with_url["url"] = image_source
                res_json = await _execute_search_request(client, data_with_url)
        else:
            if not os.path.exists(image_source):
                logger.error(f"图片文件不存在: {image_source}")
                return ["", "", False]

            with open(image_source, "rb") as f:
                image_bytes = f.read()

            ext = os.path.splitext(image_source)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            files = {"file": (os.path.basename(image_source), image_bytes, mime)}
            res_json = await _execute_search_request(client, base_data.copy(), files=files)

        if not res_json:
            return ["", "", False]

        if res_json.get("code") != 0:
            msg = res_json.get("zh_message") or res_json.get("message") or "未知错误"
            logger.warning(f"AnimeTrace 接口返回错误: {res_json.get('code')} - {msg}")
            return [f"AnimeTrace 识别失败: {msg}", "", False]

        is_ai = bool(res_json.get("ai", False))
        data_list = res_json.get("data", [])
        if not data_list:
            return ["未能在图片中识别到已知动漫角色。", "", is_ai]

        primary_str, detail_str = _format_character_results(data_list)
        return [primary_str, detail_str, is_ai]


if __name__ == "__main__":
    test_img = "img.png"
    if os.path.exists(test_img):
        res = asyncio.run(anime_trace(test_img))
        print("识别结果：\n", res)
