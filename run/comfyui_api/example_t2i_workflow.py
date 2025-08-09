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
最简单的文生图演示
"""

# Part 1: 服务器配置
COMFYUI_URLS = ["http://127.0.0.1:8188"]

# 使用asyncio.Queue来实现更健壮的轮询
url_queue = asyncio.Queue()
for url in COMFYUI_URLS:
    url_queue.put_nowait(url)

# Part 2: 核心工作流函数
async def run_workflow(prompt, config, output_dir: str = "data/pictures/cache"):
    """
    执行工作流并获取所有预定义的输出
    """
    current_server_url = await url_queue.get()
    print(f"\n本次执行使用服务器: {current_server_url}")
    # 将URL放回队列以便下次使用
    await url_queue.put(current_server_url)

    # 导出的api工作流JSON文件的路径
    WORKFLOW_JSON_PATH = "run/comfyui_api/example_src/simple_t2i.json"

    if not os.path.exists(WORKFLOW_JSON_PATH):
        print(f"错误: 找不到工作流文件: {WORKFLOW_JSON_PATH}"); return
    
    async with ComfyUIClient(current_server_url, proxy=config.common_config.basic_config["proxy"]["http_proxy"] if config.common_config.basic_config["proxy"].get("http_proxy") else None) as client:
        
        workflow = ComfyWorkflow(WORKFLOW_JSON_PATH)

        # 种子一定要和上一次执行不同，否则不会返回内容
        if prompt != "default":
            workflow.add_replacement("6", "text", prompt)
        workflow.add_replacement("3", "seed", random.randint(0, 9999999999))

        # 4. 从节点(SaveImage) 触发默认下载，最终的输出将会是DEFAULT_DOWNLOAD键内
        workflow.add_output_node("9")

        # 一次性执行并获取所有结果
        print("\n开始执行工作流，完成后将一次性返回所有结果...")
        all_results = await client.execute_workflow(workflow, output_dir)

        print("\n工作流全部输出结果")
        # 使用json.dumps美化输出，方便查看
        #print(json.dumps(all_results, indent=2, ensure_ascii=False))
        #print("输出完毕")
        return all_results
    
def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if event.pure_text.startswith("cui "):
            msg = await bot.send(event, "已发送生成图片请求...")
            await delay_recall(bot, msg, 10)
            prompt = event.pure_text.replace("cui ","").strip()
            results = await run_workflow(prompt=prompt, config=config)
            path = results.get("9", {}).get("DEFAULT_DOWNLOAD", "")
            await bot.send(event, Image(file=path))
