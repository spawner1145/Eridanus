import asyncio
import json
import os

import yaml
import httpx

_here = os.path.dirname(__file__)
_cfg_path = os.path.abspath(os.path.join(_here, "../config.yaml"))
with open(_cfg_path, "r", encoding="utf-8") as _f:
    _cfg = yaml.safe_load(_f)

PIC_PATH = _cfg.get("pic_path", "./data/pictures/cache/")
MEME_HOST = _cfg.get("meme_generate", {}).get("host", "http://127.0.0.1:2233/memes/")

result_dir = os.path.join(PIC_PATH, "result/")

async def get_more_img_func(func_name: str, img_paths: list, result_id: int,result_type: str,options: str = "",details: str = "")-> str:
    """生成仅需一或多张图片的表情包，返回结果路径"""
    files = []
    for img_path in img_paths:
        files.append(("images", open(img_path, "rb"))) 
    texts = []
    if options == "":
        args = {"circle": True}
    else:
        args = {"circle": True,f"{options}":f"{details}"}
    data = {"texts": texts, "args": json.dumps(args)}
    #print(data)

    url = f"{MEME_HOST.rstrip('/')}/{func_name}/"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, files=files, data=data)
    
    if os.path.exists(result_dir) is False:
        os.makedirs(result_dir)
    result_path = f"{result_dir}{func_name}_{result_id}.{result_type}"
    with open(result_path, "wb") as f:
        f.write(resp.content)
    return result_path

async def get_func(func_name: str, img_paths: list, strings: list, result_id: int,result_type: str)-> str:
    """生成表情包，返回结果路径"""
    files = []
    for img_path in img_paths:
        files.append(("images", open(img_path, "rb"))) 
    texts = []
    for str in strings:
        texts.append(str)
    args = {"circle": True}
    data = {"texts": texts, "args": json.dumps(args)}

    url = f"{MEME_HOST.rstrip('/')}/{func_name}/"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, files=files, data=data)
    
    if os.path.exists(result_dir) is False:
        os.makedirs(result_dir)
    result_path = f"{result_dir}{func_name}_{result_id}.{result_type}"
    with open(result_path, "wb") as f:
        f.write(resp.content)
    return result_path

# 测试调用
if __name__ == "__main__":
    print(MEME_HOST)
    # loop = asyncio.new_event_loop()
    # loop.run_until_complete(get_func("test", [], ["Hello, World!"], 1, "jpg"))