import json

import asyncio
import random

import httpx
import requests


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
async def free_deepseek(prompt,proxies=None,model_name="deepseek-r1"):
    url="https://api.milorapart.top/apis/deepseek"
    data = {"messages": prompt}
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(url=url, json=data)
        #print(r.json())
        return r.json()["choices"][0]["message"]
async def free_kimi(prompt,proxies=None,model_name="kimi"):
    url='https://api.milorapart.top/apis/kimichat'
    data={"messages": prompt}
    async with httpx.AsyncClient(proxies=proxies, timeout=200) as client:
        r = await client.post(url, json=data)
        return {'role': 'assistant', 'content': r.json()["reply"]}
async def free_deepseek2(prompt,proxies=None,model_name="deepseek-r1"):
    url='https://api.pearktrue.cn/api/aichat'
    data={"messages": prompt,"model": model_name}
    async with httpx.AsyncClient(proxies=proxies, timeout=200) as client:
        r = await client.post(url, json=data)
        return r.json()["choices"][0]["message"]
async def free_model_result(prompt, proxies=None,model_name="gpt-4o-mini"):
    model_names=["glm-4.7","glm-4-flash-250414","spark-lite","minimax-m2.1","mimo-v2-flash","deepseek-v3.2","deepseek-r1","kimi-k2-thinking","gpt-5.2","gemini-3-pro-preview","gemini-3-flash-preview","claude-sonnet-4-5-20250929","Step-3.5-Flash"]

    functions = [
        free_models(prompt, proxies,model_name),
        free_deepseek(prompt,proxies,model_name),
        free_kimi(prompt, proxies, model_name),
        free_deepseek2(prompt, proxies, random.choices(model_names))
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
                    print(result)
                    return result
        except Exception as e:
            print(f"Task failed: {e}")
prompt=[{"role": "user", "content": "你好，你是谁a"}, {"role": "assistant",
                                                                       "content": "您好！我是由中国的深度求索（DeepSeek）公司开发的智能助手DeepSeek-R1。如您有任何任何问题，我会尽我所能为您提供帮助。\n\n\n您好！我是由中国的深度求索（DeepSeek）公司开发的智能助手DeepSeek-R1。如您有任何任何问题，我会尽我所能为您提供帮助。"},
                         {"role": "user", "content": "你刚说啥?"}]
#r=asyncio.run(free_model_result(prompt=prompt))
#print(r)