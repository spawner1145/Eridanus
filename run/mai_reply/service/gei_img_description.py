import asyncio
import base64

import httpx

from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.system_logger import get_logger

_VISION_SYSTEM = (
    "你是一个图片内容提取器。"
    "输出规则：只输出图片内容的客观描述，不加任何开场白、总结语或元评论。"
    "用中文直接陈述事实，不要说图片显示 或 我看到 等。"
    "对截图/界面：逐字转录所有可见文字。"
    "对图表/表格：复现数据值。"
    "对手写内容：原样转录，不确定处标注[?]。"
    "如果认识图中的角色，请说明它是谁。"
)

_VISION_USER_PROMPT = (
    "请逐项列出这张图片中的所有内容：布局、物体、文字、颜色、空间关系、"
    "人物特征、图表数据、代码、品牌标志等所有细节。直接开始描述，不要有任何前言。"
)
config=YAMLManager.get_instance()
logger=get_logger(__name__)
VISION_API_BASE = config.mai_reply.config["context"]["vision_base_url"]
VISION_API_KEY = config.mai_reply.config["context"]["vision_api_key"]
VISION_MODEL = config.mai_reply.config["context"]["vision_model"]


def encode_image(image_path):
    """将本地图片读取并编码为 Base64 字符串"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
async def _resolve_images(img_path: str,msg_id) -> str:
    """
    遍历 messages，将含有 image_url block 的多模态消息转换为纯文本消息。
    每张图片并发调用 _describe_image，描述结果以标签形式注入文本。
    """
    base64_image = encode_image(img_path)

    # 构造 Base64 的 Data URI
    # 注意：如果你的图片是 png，请将 image/jpeg 改为 image/png
    image_data_uri = f"data:image/jpeg;base64,{base64_image}"

    # 如果你想测试网络图片直传，可以直接把 image_data_uri 换成下面的 URL：
    # image_data_uri = "https://www.w3.org/Icons/w3c_home.png"

    # 2. 构造符合 OpenAI 标准的 Payload
    payload = {
        "model": VISION_MODEL,  # 根据你的 arting_client.py，这个模型支持识图
        "messages": [
            {
                "role": "system",
                "content": _VISION_SYSTEM,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_uri
                        }
                    }
                ]
            }
        ],
        "stream": False  # 为了测试方便，这里先用非流式。你可以改为 True 测试流式输出
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VISION_API_KEY}"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{VISION_API_BASE}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        desc = data["choices"][0]["message"]["content"]

        logger.info("vision | image described, len=%d", len(desc))

        final_des=f"\n\n[⚙️系统内部指令：用户在此处上传了一张图片{msg_id}。以下是你自身视觉感知模块提取到的画面数据。]\n[⚠️强制要求：在回复时，你必须表现出是你**亲眼看到**了这张图片。**绝对禁止**说出“根据您提供的图片描述”、“从文字描述来看”等破坏沉浸感的话语，请直接以看图者的口吻对画面进行分析！]\n<vision_data_picture{msg_id}>\n{desc}\n</vision_data_picture{msg_id}>"

        return final_des