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

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager

from run.mai_reply.service.trigger import TriggerChecker
from run.mai_reply.service.reply_engine import ReplyEngine


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
        if trigger._has_at(event,bot.id):   #艾特无论如何要回复
            should_reply=True
            if event.message_chain.has(Text):
                clean_text = event.message_chain.get(Text)[0].text
            else:
                clean_text = "(艾特了你)"
        elif prefix_check(text,config.mai_reply.config["trigger"]["prefix"]):
            should_reply=True
            clean_text = text
        else:
            if not config.mai_reply.config["trigger_llm"]["enable"]:
                return
            if config.mai_reply.config["trigger_llm"]["whitelist_enabled"]:
                if not event.group_id in config.mai_reply.config["trigger_llm"]["whitelist"]:
                    #bot.logger.info(f"[MaiReply] 群 {event.group_id} 不在触发白名单中，跳过")
                    return
            should_reply, clean_text = await trigger.check(
                event=event,
                bot_self_id=bot.id,
                bot_name=config.common_config.basic_config["bot"],
                pure_text=text,
            )
        #print(should_reply, clean_text)
        #print(event.message_chain)
        #print(clean_text)

        bot.logger.info(f"[MaiReply] trigger={should_reply} self_id={bot.id} text={clean_text}")
        if not should_reply:
            # 即使不回复，也把消息存入群旁观窗口（感知群聊气氛）
            if text.strip():
                try:
                    user_name = str(event.user_id)
                    engine.context.push_group_window(event.group_id, user_name, clean_text)
                except Exception:
                    pass
            return

        # 更新 focus
        #trigger.set_focus(event.user_id, event.group_id)

        # 异步处理（不阻塞事件循环）
        asyncio.create_task(engine.handle(bot, event, clean_text))

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

        asyncio.create_task(engine.handle(bot, event, text))

    def prefix_check(message: str, prefix: list):
        for p in prefix:
            if message.startswith(p) and p != "":
                bot.logger.info(f"[MaiReply] 消息以触发前缀 {p} 开头，强制触发")
                return True
        return False