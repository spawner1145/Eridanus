import json

import asyncio
import httpx


async def free_models(prompt,proxies=None,model_name="gpt-4o-mini"):
    url="https://apiserver.alcex.cn/v1/chat/completions"
    data = {
        "model": model_name,
        "messages": prompt,
        "stream": False
    }
    async with httpx.AsyncClient(proxies=proxies, timeout=200) as client:
        r = await client.post(url, json=data)

        return r.json()["choices"][0]["message"]


async def free_model_result(prompt, proxies=None,model_name="gpt-4o-mini"):
    functions = [
        free_models(prompt, proxies,model_name),
        #free_phi_3_5(prompt, proxies),
        #free_gemini(prompt,proxies),
        #claude_free(prompt,proxies),
        #free_gpt4(prompt,proxies)
    ]

    for future in asyncio.as_completed(functions):
        try:
            result = await future
            if result:
                if result["content"]!= "" and result["content"]!= "You've reached your free usage limit today":
                    return result
        except Exception as e:
            print(f"Task failed: {e}")
