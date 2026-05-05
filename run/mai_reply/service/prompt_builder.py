"""
prompt_builder.py
Prompt 构建器 —— 组装系统提示词和用户消息
核心理念：使用自然语言风格构建 Prompt，让回复贴近人类习惯
"""

import os
import json
import time
from datetime import datetime
from typing import Optional


# 角色卡解析支持 txt / json / SillyTavern PNG 卡（仅读取文本元数据）
def _load_chara_file(chara_file: str) -> Optional[str]:
    """
    从 data/system/chara/ 目录加载角色卡
    支持 .txt / .json
    """
    if not chara_file:
        return None
    base_dir = os.path.join("data", "system", "chara")
    path = os.path.join(base_dir, chara_file)
    if not os.path.exists(path):
        return None
    ext = os.path.splitext(chara_file)[1].lower()
    try:
        if ext == ".txt":
            with open(path, "r", encoding="utf-8") as f:
                print(f"加载到角色{chara_file}")
                return f.read().strip()
        elif ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # SillyTavern JSON 格式
            if isinstance(data, dict):
                desc = data.get("description") or data.get("personality") or data.get("system_prompt", "")
                scenario = data.get("scenario", "")
                return f"{desc}\n{scenario}".strip()
            print(f"加载到角色{chara_file}")
            return str(data)
    except Exception:
        return None
    return None


class PromptBuilder:

    def __init__(self, config, emotion_system):
        self.cfg = config
        self.emotion = emotion_system
        pcfg = config.mai_reply.config.get("persona", {})
        self._name_override: str = pcfg.get("name", "").strip()
        self._system_template: str = pcfg.get("system_prompt", "")
        self._chara_file: str = pcfg.get("chara_file", "").strip()
        # 角色卡内容缓存（启动时加载一次）
        self._chara_content: Optional[str] = _load_chara_file(self._chara_file)

    def get_bot_name(self, bot_name_from_config: str) -> str:
        return self._name_override or bot_name_from_config

    def build_system_prompt(
        self,
        bot_name: str,
        user_name: str,
        group_name: str = "私聊",
        group_context_snippet: str = "",
        user_impression: str = "",
    ) -> str:
        """
        构建完整 system prompt
        """
        # 优先使用角色卡内容，角色卡内容作为人设基础，其余追加
        if self._chara_content:
            base = self._chara_content
        else:
            base = self._system_template

        # 时间
        now = datetime.now()
        time_str = now.strftime("%Y年%m月%d日 %H:%M")
        # 星期
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        time_str += f" {weekdays[now.weekday()]}"

        # 情绪
        mood = self.emotion.get_mood()
        #print(bot_name,user_name)
        # 变量替换
        prompt = base.replace("{","{{").replace("}","}}").format(
            bot_name=bot_name,
            用户=user_name,
            time=time_str,
            mood=mood,
            group_name=group_name,
        )

        if group_context_snippet:
            prompt += f"\n\n{group_context_snippet}"

        # 追加用户印象记忆（强化态度区分指令）
        if user_impression:
            prompt += f"\n\n【你对 {user_name} 的主观印象与态度】\n{user_impression}\n（重要：请务必根据以上印象，动态调整你此刻对TA的说话语气！如果印象好就亲昵，如果印象差就冷淡甚至回怼！）"
        else:
            prompt += f"\n\n【你对 {user_name} 的主观印象与态度】\n你们还不算太熟，按你正常的心情回应即可。"

        # 追加拟人化输出规则
        prompt += _HUMANLIKE_RULES
        prompt=prompt.replace("{bot_name}", bot_name).replace("{用户}", user_name)
        #print(prompt)
        return prompt.strip()


# 拟人化输出规则，始终追加
# 拟人化输出规则，始终追加
_HUMANLIKE_RULES = """

【你的说话方式（核心规则）】
- 说话要随意自然，像真实的人在聊天，绝对不要写长篇大论
- 真人聊天时喜欢把一句话拆成几条短消息连发！如果你想分段连发，请务必使用 `||` 符号分隔每条消息！
  举个例子：
  干什么||？||你就知道你的机器人我不想理你（推开）
- 不要用 markdown（没有加粗、没有#标题、没有列表）
- 句末尽量不加句号，标点随意点，多用空格、逗号或省略号
- 不要每句话都回应对方，有时候只说自己想说的就行
- 回复总长度一般不超过80字，最多拆成2-4条连发
- 不要重复之前说过的内容"""
