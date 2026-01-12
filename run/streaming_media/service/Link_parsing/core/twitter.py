import httpx
import re
import copy
import asyncio
from .login_core import ini_login_Link_Prising
from .common import json_init,filepath_init,COMMON_HEADER,GLOBAL_NICKNAME,GENERAL_REQ_LINK
from urllib.parse import urlparse
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from developTools.utils.logger import get_logger
logger=get_logger()
import json
from framework_common.manshuo_draw.manshuo_draw import manshuo_draw
from httpx import AsyncClient
import pprint
from framework_common.utils.utils import download_img
from framework_common.utils.random_str import random_str
from playwright.async_api import async_playwright
from run.resource_collector.service.engine_search import html_read

async def twitter(url,filepath=None,proxy=None):
    """
        X解析
    :param bot:
    :param event:
    :return:
    """
    msg=url
    contents=[]
    json_check = copy.deepcopy(json_init)
    json_check['soft_type'] = 'x'
    json_check['status'] = True
    json_check['video_url'] = False
    if filepath is None: filepath = filepath_init
    x_url = re.search(r"https?:\/\/x.com\/[0-9-a-zA-Z_]{1,20}\/status\/([0-9]*)", msg)[0]

    #x_url = GENERAL_REQ_LINK.replace("{}", x_url)







    # 内联一个请求
    async def x_req(x_url):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://xdown.app",
            "Referer": "https://xdown.app/",
        }
        data = {"q": x_url, "lang": "zh-cn"}
        async with AsyncClient(headers=headers) as client:
            url = "https://xdown.app/api/ajaxSearch"
            response = await client.post(url, data=data)

            return response.json()

    rsq_data = (await x_req(x_url))
    #pprint.pprint(rsq_data)
    match = re.search(r'src="([^"]+)"', rsq_data['data'])
    if match:
        img_url = match.group(1)
        json_check['pic_url_list'] = [img_url]
    else:
        return json_check
    #print(img_url)

    match = re.search(r'href="([^"]+)"', rsq_data['data'])
    if match:
        video_url = match.group(1)
        match = re.search(r'data-audioUrl="([^"]+)"', rsq_data['data'])
        if match:
            audio_url = match.group(1)
            json_check['audio_url'] = audio_url
            json_check['video_url'] = video_url



    logger.info(img_url)
    img_path = "data/pictures/cache/" + random_str() + ".png"
    await download_img(img_url, img_path, proxy="http://127.0.0.1:7890" )

    #使用浏览器获取文本
    title = ''
    match = re.search(r'<h3>(.*?)</h3>', rsq_data['data'])
    if match:
        title = f'[title]{match.group(1)}[/title]'
    else:
        try:
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(headless=True, proxy={"server":"http://127.0.0.1:7890"})
                page = await browser.new_page()
                await page.route("**/*", lambda route, request: asyncio.create_task(
                    route.abort() if request.resource_type in ["image", "stylesheet", "font"] else route.continue_()
                ))
                # 访问网页
                await page.goto(x_url)

                # 获取网页body中的纯文本内容
                body_handle = await page.query_selector("body")
                text_content = await body_handle.inner_text()
                #print(text_content)
                await browser.close()
                text_content = text_content.split("\n")
                #print(text_content)
                num,X_id,X_name,X_content = 0,None,None,None
                for item in text_content:
                    if item.startswith('@'):
                        X_id = text_content[num]
                        X_name = text_content[num - 1]
                        break
                    num += 1
                if X_id is not None:
                    content_num = 0
                    for item in text_content:
                        if item.strip() == '·' or item.strip() == 'Views':
                            break
                        content_num += 1
                    X_content = "\n".join(text_content[num+1:content_num])
                #print(X_id,X_name,X_content)
                if X_id is not None:
                    title = f'[title]{X_name} [/title]{X_id}\n{X_content}'
        except:pass
    if title:
        contents = [title,img_path]
    else:
        contents = [img_path]
    json_check['pic_path'] = await manshuo_draw(contents)
    return json_check