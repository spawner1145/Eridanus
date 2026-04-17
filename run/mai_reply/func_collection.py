"""
func_collection.py
函数调用集合 —— 供 Eridanus ai_llm 插件的函数调用体系使用

当前提供：
  - clear_chat_history: 清除当前用户的对话历史
  - get_mood: 查看 bot 当前情绪
"""

from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager

from run.mai_reply.service.context_manager import ContextManager
from run.mai_reply.service.emotion_system import EmotionSystem


async def clear_chat_history(bot: ExtendBot, event, config: YAMLManager):
    """清除当前用户在本会话的 MaiReply 对话历史"""
    ctx = ContextManager(config)
    group_id = getattr(event, "group_id", None)
    ctx.clear_session(group_id, event.user_id)
    await bot.send(event, "好的，对话记录已清除～")


async def get_current_mood(bot: ExtendBot, event, config: YAMLManager):
    """查看 MaiReply bot 当前的情绪状态"""
    emotion = EmotionSystem(config)
    mood = emotion.get_mood()
    score = emotion.get_score()
    direction = "↑" if score > 10 else ("↓" if score < -10 else "→")
    await bot.send(event, f"现在的状态：{mood}（情绪值 {score:+d} {direction}）")
