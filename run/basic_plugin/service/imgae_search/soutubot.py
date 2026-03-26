# -*- coding: utf-8 -*-
import re
import time
import json
import base64
import requests
import asyncio

API_URL  = "https://soutubot.moe/api/search"
BASE_URL = "https://soutubot.moe"


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}

IMAGE_HEADERS = {
    **BROWSER_HEADERS,
    "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "sec-fetch-dest": "image",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "cross-site",
    "sec-fetch-storage-access": "active",
    "referer": BASE_URL + "/",
}


# 生成 x-api-key
def generate_api_key(session: requests.Session) -> str:
    """根据网站前端 JS 中的算法动态生成 x-api-key"""

    # 1. 访问主页获取全局变量 window.GLOBAL.m 的值
    resp = session.get(BASE_URL + "/", headers=BROWSER_HEADERS)
    resp.raise_for_status()

    # 匹配 <script> 标签中的 m 值，例如：window.GLOBAL={"m":123456789,...}
    match = re.search(r'["\']?m["\']?\s*:\s*(\d+(?:\.\d+)?)', resp.text)
    if not match:
        raise RuntimeError("未能在主页 HTML 中找到 window.GLOBAL.m 变量，页面可能已更新。")

    # 获取 m 值 (可能是整数或浮点数)
    global_m = float(match.group(1))

    # 2. 模拟 Math.pow(Z().unix(), 2) -> 当前时间戳(秒)的平方
    unix_timestamp = int(time.time())
    time_pow = unix_timestamp ** 2

    # 3. 模拟 Math.pow(window.navigator.userAgent.length, 2) -> UA 长度的平方
    ua_len_pow = len(USER_AGENT) ** 2

    # 4. 相加转字符串
    raw_num = time_pow + ua_len_pow + global_m
    # 保证和 JS 的 toString() 表现一致（去除 Python float 的 .0）
    raw_str = str(int(raw_num)) if raw_num.is_integer() else str(raw_num)

    # 5. 模拟 En.encode(e).split("").reverse().join("").replace(/=/g, "")
    # Base64编码
    b64_encoded = base64.b64encode(raw_str.encode('utf-8')).decode('utf-8')

    # 翻转并去等号
    api_key = b64_encoded[::-1].replace("=", "")

    print(f"[*] 动态计算生成 x-api-key: {api_key}")
    return api_key


#搜索
def _do_search(session: requests.Session, api_key: str,
               image_data: bytes, factor: float = 1.2) -> dict:
    """内部：把图片二进制发送给 API 并返回 JSON 结果。"""
    headers = {
        **BROWSER_HEADERS,
        "accept": "application/json, text/plain, */*",
        "x-api-key": api_key, # 使用刚刚动态生成的鉴权 Key
        "x-requested-with": "XMLHttpRequest",
        "sec-ch-ua": '"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "referer": BASE_URL + "/",
    }
    files = {"file": ("image.png", image_data, "image/png")}
    data  = {"factor": str(factor)}

    resp = session.post(API_URL, headers=headers, files=files, data=data)

    if resp.status_code == 401:
        print("[!] HTTP 401: x-api-key 可能计算错误或超时")

    resp.raise_for_status()
    return resp.json()

def search_by_image(image_path: str, factor: float = 1.2) -> dict:
    """以本地图片搜索。"""
    with open(image_path, "rb") as f:
        image_data = f.read()

    session = requests.Session()
    api_key = generate_api_key(session)
    return _do_search(session, api_key, image_data, factor)

def search_by_url(image_url: str, factor: float = 1.2) -> dict:
    """先下载远程图片，再搜索。"""
    session = requests.Session()

    print(f"[*] 下载图片: {image_url}")
    img_resp = session.get(image_url, headers=IMAGE_HEADERS)
    img_resp.raise_for_status()

    api_key = generate_api_key(session)
    return _do_search(session, api_key, img_resp.content, factor)


# 打印结果

def print_results(result: dict):
    print(json.dumps(result, ensure_ascii=False, indent=2))
    items = result.get("data",[])
    if items:
        print(f"\n[*] 共 {len(items)} 条结果:")
        for i, item in enumerate(items, 1):
            title = item.get("title") or item.get("name") or "无标题"
            sim   = item.get("similarity", "未知")

            # soutubot 通常会给出 pagePath 和 subjectPath，需要拼接主域名
            path = item.get("pagePath") or item.get("subjectPath") or ""
            source = item.get("source", "未知源")

            print(f"  {i}. [{source}] {title} (相似度: {sim}%)")
            if path:
                # 注：实际的 host 取决于来源（nhentai, ehentai等），简单起见这里仅打印 Path
                print(f"     路径: {path}")
    else:
        print("[-] 未找到相关结果。")

def search_img_by_path_or_url(target: str, factor: float = 1.2) -> dict:
    try:
        if target.startswith("http://") or target.startswith("https://"):
            print(f"[*] 远程图片搜索: {target}")
            result = search_by_url(target, factor)
        else:
            print(f"[*] 本地图片搜索: {target}")
            if target.startswith("file://"): target = target.replace("file://", "")
            result = search_by_image(target, factor)

        return result["data"]
    except Exception as e:
        print(f"[x] 搜索失败: {e}")
async def async_search_by_image(image_path: str, factor: float = 1.2) -> dict:
    """
    异步包装：本地图片搜索
    """
    result = await asyncio.to_thread(search_img_by_path_or_url, image_path, factor)
    return result
if __name__ == "__main__":
    # 测试时换成你本地实际存在的图片路径，或者网络 URL
    target = "data/pictures/img.png"
    factor = 1.2

    try:
        if target.startswith("http://") or target.startswith("https://"):
            print(f"[*] 远程图片搜索: {target}")
            result = search_by_url(target, factor)
        else:
            print(f"[*] 本地图片搜索: {target}")
            result = search_by_image(target, factor)
        print(type(result))
        print_results(result)

    except Exception as e:
        print(f"[x] 搜索失败: {e}")