import httpx
from pathlib import Path

async def upload_image_with_quality(
    image_path: str,
    quality: int = 60,
    token: str = None,
    referer: str = None
):
    """
    使用 httpx 异步上传图片
    :param image_path: 图片文件路径
    :param quality: 图片质量 (默认60)
    :param token: PHPSESSID (必填)
    :param referer: 可选的 Referer
    :return: httpx.Response
    """

    url = "https://dev.ruom.top/api.php"

    # Cookies
    cookies = {
        "upload_count": '{"date":"2025-08-26","count":1}',   # 可根据实际情况改
        "PHPSESSID": token if token else "",                  # 必须带上
    }

    # Headers
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "origin": "https://dev.ruom.top",
        "referer": referer or "https://dev.ruom.top/",
        "sec-ch-ua": '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
    }

    # 文件 & 表单
    files = {
        "image": (Path(image_path).name, open(image_path, "rb"), "image/jpeg"),
    }
    data = {
        "quality": str(quality),
    }

    async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=60) as client:
        response = await client.post(url, data=data, files=files)
        print(response.json())
        return response.json()["data"]["url"]


# 用法示例
# import asyncio
# resp = asyncio.run(upload_image_with_quality("test.jpg", 60, token="3tfpmd0v6hc1lgp1cj8s35mkcb"))
# print(resp.status_code, resp.text)
