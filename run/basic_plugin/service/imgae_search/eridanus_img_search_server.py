import traceback

import httpx


async def search_(img:str):
    """
    Eridanus项目提供的搜图服务端，需要额外部署。
    """
    async with httpx.AsyncClient() as client:
        try:
            files = {
                "file": (img, open(img, "rb"), "image/jpeg")
            }

            headers = {
                "accept": "application/json"
            }
            response = await client.post("http://127.0.0.1:5008/search",headers=headers,files=files,timeout=None)
            #print(response.text)
        except Exception as e:
            traceback.print_exc()
            print(e)
        return response.json()["results"]