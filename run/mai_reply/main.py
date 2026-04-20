"""
mai_reply/main.py
MaiReply 插件主入口

设计理念源自 MaiBot：
  "最像，而不是最好"
  不追求完美，追求真实。
  bot不是工具，她只是在这里，和大家一起聊天。

功能：
  - 高拟人化 AI 群聊/私聊回复
  - 情绪系统（随时间自然波动）
  - 多会话上下文记忆（Redis 存储）
  - 群聊旁观上下文感知
  - 跨会话用户印象记忆
  - 消息分割+打字延迟模拟
  - 错字生成
  - 概率触发 + focus持续对话
  - 高并发安全（信号量 + 会话锁 + 消息合并）
  - /clear 清除对话历史
  - 函数调用（兼容 Eridanus func_calling 体系）
"""

import asyncio
import base64
import uuid

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text, Image, Mface
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import download_img, get_img
from run.mai_reply.service.gei_img_description import _resolve_images

from run.mai_reply.service.trigger import TriggerChecker
from run.mai_reply.service.reply_engine import ReplyEngine


async def extract_message_content(event, bot) -> tuple:
    """
    从消息链中提取文本和图片，构建 OpenAI 多模态 content 列表。
    返回 (pure_text: str, content: str | list)
    - 若无图片，content 为纯字符串（与原逻辑兼容）
    - 若含图片，content 为 list[dict]，符合 OpenAI vision 格式
    """
    text_parts = []
    image_items = []  # {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}

    for msg in event.message_chain:
        if isinstance(msg, Text):
            text_parts.append(msg.text)
        elif isinstance(msg, (Image, Mface)):
            try:
                url = await get_img(event, bot)
                path = f"data/pictures/cache/{uuid.uuid4()}.png"
                await download_img(url, path)
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                image_items.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}
                })
            except Exception as e:
                # 图片获取失败时降级为文本说明
                text_parts.append("[图片获取失败]")

    pure_text = "".join(text_parts).strip()

    if not image_items:
        return pure_text, pure_text

    # 构建多模态 content list
    content = []
    if pure_text:
        content.append({"type": "text", "text": pure_text})
    else:
        content.append({"type": "text", "text": "(发送了图片)"})
    content.extend(image_items)

    return pure_text, content


def main(bot: ExtendBot, config: YAMLManager):
    if not config.mai_reply.config["enable"]:
        bot.logger.warning("[MaiReply] 功能未开启。使用旧版ai对话组件")
        bot.logger.warning("[MaiReply] 如要启用新版ai对话请在配置文件中将 mai_reply.enable 设置为 true 随后重启bot")
        return
    engine = ReplyEngine(config)

    trigger = TriggerChecker(config, engine.context, engine.emotion)


    bot.logger.info("[MaiReply] 高拟人化AI回复插件已加载")

    @bot.on(GroupMessageEvent)
    async def handle_group(event: GroupMessageEvent):
        """
        开始构式一样的权限判断
        """

        text = event.pure_text or ""

        # 清理指令
        if text.strip() in ("/clear", "清除对话", "清理对话"):
            engine.context.clear_session(event.group_id, event.user_id)
            await bot.send(event, "好的，对话记录已清除～")
            return
        async def add_to_context():
            if event.message_chain.has(Image) or event.message_chain.has(Mface):
                if config.mai_reply.config["context"]["img_context"] and event.group_id in config.mai_reply.config["context"]["vision_enable_group"]:
                    bot.logger.info(f"[MaiReply] 消息包含图片，且已开启图片上下文，将存入旁观窗口")
                    async def img_add_to_window():
                        img_url = await get_img(event, bot)
                        path = f"data/pictures/cache/{uuid.uuid4()}.png"
                        await download_img(img_url, path)
                        window_text = await _resolve_images(path,event.message_id)
                        #print(window_text)
                        engine.context.push_group_window(event.group_id, event.sender.nickname, window_text+f"url：{img_url}")
                        r=engine.context._load_group_window(event.group_id)  # 刷新窗口内容到内存
                        #print(r)
                    asyncio.create_task(img_add_to_window())
            if text.strip():
                try:
                    user_name = event.sender.nickname
                    #print(clean_text)
                    engine.context.push_group_window(event.group_id, user_name, clean_text)
                except Exception:
                    pass
        if trigger._has_at(event, bot.id):   # 艾特无论如何要回复
            should_reply = True
            pure_text, content = await extract_message_content(event, bot)
            clean_text = pure_text or "(艾特了你)"
        elif prefix_check(text, config.mai_reply.config["trigger"]["prefix"]):
            should_reply = True
            pure_text, content = await extract_message_content(event, bot)
            clean_text = pure_text
        else:
            if not config.mai_reply.config["trigger_llm"]["enable"]:
                await add_to_context()  # 即使不触发，也把消息存入群旁观窗口（感知群聊气氛）
                return
            if config.mai_reply.config["trigger_llm"]["whitelist_enabled"]:
                if event.group_id not in config.mai_reply.config["trigger_llm"]["whitelist"]:
                    await add_to_context()
                    return
            should_reply, clean_text = await trigger.check(
                event=event,
                bot_self_id=bot.id,
                bot_name=config.common_config.basic_config["bot"],
                pure_text=text,
            )
            pure_text, content = await extract_message_content(event, bot)

        bot.logger.info(f"[MaiReply] trigger={should_reply} self_id={bot.id} text={clean_text}")
        if not should_reply:
            #print("触发")
            # 即使不回复，也把消息存入群旁观窗口（感知群聊气氛）
            await add_to_context()
            return

        # 异步处理（不阻塞事件循环），传入多模态 content
        asyncio.create_task(engine.handle(bot, event, clean_text, multimodal_content=content))

    # ------------------------------------------------------------------ 私聊消息处理
    @bot.on(PrivateMessageEvent)
    async def handle_private(event: PrivateMessageEvent):
        text = event.pure_text or ""

        # 清理指令
        if text.strip() in ("/clear", "清除对话", "清理对话"):
            engine.context.clear_session(None, event.user_id)
            await bot.send(event, "好，忘掉了～")
            return

        # 私聊配置了不触发则跳过
        if not config.mai_reply.config.get("trigger", {}).get("private_trigger", True):
            return

        pure_text, content = await extract_message_content(event, bot)
        asyncio.create_task(engine.handle(bot, event, pure_text or text, multimodal_content=content))

    def prefix_check(message: str, prefix: list):
        for p in prefix:
            if message.startswith(p) and p != "":
                bot.logger.info(f"[MaiReply] 消息以触发前缀 {p} 开头，强制触发")
                return True
        return False