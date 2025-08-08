from developTools.event.events import GroupMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager        
import asyncio
import random
import os
from developTools.message.message_components import File, Image, Video, Node, Text
from framework_common.utils.utils import delay_recall # 撤回提示防刷屏

from .comfy_api.client import ComfyUIClient
from .comfy_api.workflow import ComfyWorkflow

"""
使用这个流前在c站搜素neta lumina，并根据文档提示下载节点和huggingface的模型
"""

# Part 1: 服务器配置
COMFYUI_URLS = ["http://127.0.0.1:8188"]

# 使用asyncio.Queue来实现更健壮的轮询
url_queue = asyncio.Queue()
for url in COMFYUI_URLS:
    url_queue.put_nowait(url)

url_queue = asyncio.Queue()
for url in COMFYUI_URLS:
    url_queue.put_nowait(url)

# Part 2: 核心工作流函数
async def run_workflow(prompt, input_image_path, config, output_dir = "outputs"):
    current_server_url = await url_queue.get()
    print(f"\n本次执行使用服务器: {current_server_url}")
    # 将URL放回队列以便下次使用
    await url_queue.put(current_server_url)

    # 请确保这些ID与你的工作流JSON文件匹配，其实这个不搞也可以，只是为了方便下面表示
    NODE_MAPPING = {
        "LOAD_IMAGE": '33', "POSITIVE_PROMPT": '6', "NEGATIVE_PROMPT": '7',
        "KSAMPLER": '3', "SAVE_IMAGE": '9', "TEXT_OUTPUT": "69"
    }
    WORKFLOW_JSON_PATH = "run/comfyui_api/example_src/neta_lumina_i2i.json"

    if not all(os.path.exists(p) for p in [input_image_path, WORKFLOW_JSON_PATH]):
        print(f"错误: 确保文件存在: {input_image_path}, {WORKFLOW_JSON_PATH}"); return

    async with ComfyUIClient(current_server_url, proxy=config.common_config.basic_config["proxy"]["http_proxy"] if config.common_config.basic_config["proxy"].get("http_proxy") else None) as client:
        # 上传输入图片
        upload_info = await client.upload_file(input_image_path)
        server_filename = upload_info['name']

        workflow = ComfyWorkflow(WORKFLOW_JSON_PATH)
        workflow.add_replacement(NODE_MAPPING["LOAD_IMAGE"], "image", server_filename)
        workflow.add_replacement(NODE_MAPPING["POSITIVE_PROMPT"], "text", prompt)
        workflow.add_replacement(NODE_MAPPING["KSAMPLER"], "seed", random.randint(0, 9999999999))

        # 定义所有你想要的输出
        # 默认下载，最终的输出将会是DEFAULT_DOWNLOAD键内
        workflow.add_output_node(NODE_MAPPING["SAVE_IMAGE"])

        print("\n开始执行工作流，完成后将一次性返回所有结果...")
        all_results = await client.execute_workflow(workflow, output_dir)
        return all_results


# Part 3: 主函数入口
def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if event.pure_text.startswith("neta "):
            msg = await bot.send(event, "已发送生成图片请求...")
            await delay_recall(bot, msg, 10)
            prompt = event.pure_text.replace("neta ","").strip()
            # 这边你可以改成自己通过机器人输入图片，具体看run/ai_generated_art/aiDraw.py这个文件，懒得示例了
            INPUT_IMAGE = "run/comfyui_api/example_src/upload_img.png"
            results = await run_workflow(prompt=prompt, input_image_path=INPUT_IMAGE, config=config)
            path = results.get("9", {}).get("DEFAULT_DOWNLOAD", "")
            await bot.send(event, Image(file=path))

if __name__ == "__main__":
    asyncio.run(main())