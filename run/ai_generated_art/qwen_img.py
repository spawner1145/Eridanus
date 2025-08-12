from developTools.event.events import GroupMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager        
import asyncio
from developTools.message.message_components import File, Image, Video, Node, Text
from framework_common.utils.utils import delay_recall  # 撤回提示防刷屏
import httpx
from pathlib import Path

censor_words = ["屏蔽词测试"]

async def generate_and_save_image(prompt: str, cookie: str) -> str:
    save_dir = Path("data/pictures/cache")
    save_dir.mkdir(parents=True, exist_ok=True)

    submit_url = "https://www.modelscope.cn/api/v1/muse/predict/task/submit"
    base_headers = {
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": "-nsRQ13dP_5NMpGEaLxNlKCWqwc=",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Origin": "https://www.modelscope.cn",
        "Referer": "https://www.modelscope.cn/studios/qwen/Qwen-VL-Chat/summary"
    }
    
    submit_data = {
        "modelArgs": {
            "checkpointModelVersionId": 275167,
            "loraArgs": [],
            "checkpointShowInfo": "Qwen Image_v1.safetensors"
        },
        "promptArgs": {
            "prompt": prompt,
            "negativePrompt": "lowres,(bad),text,error,fewer,extra,missing,worst quality,jpeg artifacts,low quality,watermark,unfinished,displeasing,oldest,early,chromatic aberration,signature,extra digits,artistic error,username,scan,[abstract],"
        },
        "basicDiffusionArgs": {
            "sampler": "Euler",
            "guidanceScale": 4,
            "seed": -1,
            "numInferenceSteps": 30,
            "numImagesPerPrompt": 1,
            "width": 2048,
            "height": 2048,
            "advanced": False
        },
        "hiresFixFrontArgs": None,
        "addWaterMark": False,
        "advanced": False,
        "predictType": "TXT_2_IMG",
        "controlNetFullArgs": []
    }

    print("使用指定的Cookie尝试连接")
    headers = base_headers.copy()
    headers["Cookie"] = cookie
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # 提交任务
            submit_response = await client.post(
                submit_url,
                headers=headers,
                json=submit_data,
                follow_redirects=True
            )
            submit_response.raise_for_status()
            submit_result = submit_response.json()
            
            if not (submit_result.get("Code") == 200 and submit_result.get("Success")):
                error_msg = submit_result.get("Message", "未知错误")
                print(f"Cookie提交失败: {error_msg}")
                return f"提交失败: {error_msg}"
                
            task_id = submit_result["Data"]["data"]["taskId"]
            print(f"任务提交成功，taskId: {task_id}")

        except httpx.RequestError as e:
            print(f"提交请求失败: {str(e)}")
            return f"请求失败: {str(e)}"
        except (KeyError, ValueError) as e:
            print(f"解析提交结果失败: {str(e)}")
            return f"解析结果失败: {str(e)}"

        # 轮询任务状态
        status_url = "https://www.modelscope.cn/api/v1/muse/predict/task/status"
        max_retries = 30  # 最大轮询次数
        retry_interval = 5  # 轮询间隔(秒)
        
        for attempt in range(max_retries):
            try:
                status_response = await client.get(
                    status_url,
                    headers=headers,
                    params={"taskId": task_id}
                )
                status_response.raise_for_status()
                status_result = status_response.json()
                
                if not (status_result.get("Code") == 200 and status_result.get("Success")):
                    raise Exception(f"查询状态失败: {status_result.get('Message')}")
                    
                task_data = status_result["Data"]["data"]
                task_status = task_data["status"]

                if task_status == "SUCCEED":
                    image_url = task_data["predictResult"]["images"][0]["imageUrl"]
                    
                    try:
                        filename = f"{task_id}.png"
                        save_path = save_dir / filename
                        save_path_str = save_path.as_posix()
                        
                        # 下载图片
                        image_response = await client.get(image_url)
                        image_response.raise_for_status()
                        
                        # 保存图片
                        with open(save_path, "wb") as f:
                            f.write(image_response.content)
                            
                        print(f"图片已保存至: {save_path_str}")
                        return save_path_str
                        
                    except httpx.RequestError as e:
                        return f"下载图片失败: {str(e)}"
                    except IOError as e:
                        return f"保存图片失败: {str(e)}"
                        
                elif task_status == "PROCESSING" or task_status == "PENDING":
                    progress = task_data.get("progress", {}).get("detail", "处理中")
                    print(f"第{attempt+1}次轮询: {progress}")
                    await asyncio.sleep(retry_interval)
                    
                else:
                    error_msg = task_data.get("errorMsg", "未知错误")
                    print(f"任务失败({task_status}): {error_msg}")
                    return f"任务失败: {error_msg}"

            except httpx.RequestError as e:
                print(f"轮询请求失败: {str(e)}，{retry_interval}秒后重试...")
                await asyncio.sleep(retry_interval)
            except (KeyError, ValueError) as e:
                print(f"解析状态结果失败: {str(e)}")
                return f"解析状态失败: {str(e)}"

        print("轮询超时")
        return "轮询超时，未能获取结果"

async def call_qwen_img(bot, event, config, prompt):
    for word in censor_words:
        if word in prompt:
            await bot.send(event, Text("下头"), True)
            return
    # 在https://www.modelscope.cn/aigc/imageGeneration?tab=advanced&versionId=275167&modelType=Checkpoint&sdVersion=QWEN_IMAGE_20_B&modelUrl=modelscope%3A%2F%2FMusePublic%2FQwen-image%3Frevision%3Dv1
    # 这里跑一次图f12自己拿cookie
    cookie = config.ai_generated_art.config['ai绘画']['qwen_image_cookie']  # 这里填入你的cookie字符串
    if not cookie:
        msg = await bot.send(event, "请先去modelscope获取cookie", True)
        await delay_recall(bot, msg, 10)
        return
    msg = await bot.send(event, f"已发送qwen img请求...")
    await delay_recall(bot, msg, 10)
    
    results = await generate_and_save_image(prompt=prompt, cookie=cookie)
    if results.endswith(".png"):
        await bot.send(event, [Text("qwen image:"), Image(file=results)], True)
    else:
        await bot.send(event, Text(results))
    
def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if event.pure_text.startswith("#qwen "):
            await call_qwen_img(bot, event, config, event.pure_text.replace("#qwen ", ""))
