import os
import random
import re
import json
import asyncio
from typing import Dict, Any, List, Union
from pathlib import Path


class AIPluginGenerator:
    def __init__(self, ai_reply_core_func, base_path: str = "run"):
        """
        AI插件代码生成器

        Args:
            ai_reply_core_func: 你定义的aiReplyCore异步函数
            base_path: 插件生成的基础路径
        """
        self.ai_reply_core = ai_reply_core_func
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)

        # SDK使用指南模板
        self.sdk_guide = self._build_sdk_guide()

    def _build_sdk_guide(self) -> str:
        """构建SDK使用指南"""
        return """
# SDK使用指南

## 项目结构要求
插件必须按以下结构组织：
```
run/
├─plugin_name/
│ ├─plugin_name.py  # 主插件文件
│ ├─__init__.py     # 必须包含plugin_description和entrance_func
```

## __init__.py模板
```python
plugin_description = "具体插件名称和功能描述"

from framework_common.framework_util.main_func_detector import load_main_functions

# 各个入口文件
entrance_func = load_main_functions(__file__)
```

## 主插件文件模板
```python
from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager

def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        # 群消息处理逻辑
        if event.pure_text == "触发词":
            await bot.send(event, "回复内容")

    @bot.on(PrivateMessageEvent) 
    async def handle_private_message(event: PrivateMessageEvent):
        # 私聊消息处理逻辑
        pass
```

## 常用事件类型
class MessageEvent(BaseModel):
    事件基类

    post_type: Literal["message"]
    sub_type: str
    user_id: int
    message_type: str
    message_id: int
    message: List[Dict[str, Any]]  # Change the type hint here
    original_message: Optional[list] = None
    _raw_message: str
    font: int
    sender: Sender
    to_me: bool = False
    reply: Optional[Reply] = None

    processed_message: List[Dict[str, Union[str, Dict]]] = []

    message_chain: MessageChain=[]
    pure_text: str = ""

    model_config = ConfigDict(extra="allow",arbitrary_types_allowed=True)

- GroupMessageEvent: 群消息事件
- PrivateMessageEvent: 私聊消息事件

class GroupUploadNoticeEvent(NoticeEvent):
    群文件上传事件

    notice_type: Literal["group_upload"]
    user_id: int
    group_id: int
    file: File
群管理员变动

class GroupAdminNoticeEvent(NoticeEvent):
    群管理员变动

    notice_type: Literal["group_admin"]
    sub_type: str
    user_id: int
    group_id: int
群成员减少事件

class GroupDecreaseNoticeEvent(NoticeEvent):
    群成员减少事件

    notice_type: Literal["group_decrease"]
    sub_type: str
    user_id: int
    group_id: int
    operator_id: int
群成员增加事件

class GroupIncreaseNoticeEvent(NoticeEvent):
    群成员增加事件

    notice_type: Literal["group_increase"]
    sub_type: str
    user_id: int
    group_id: int
    operator_id: int
群禁言事件

class GroupBanNoticeEvent(NoticeEvent):
    群禁言事件

    notice_type: Literal["group_ban"]
    sub_type: str
    user_id: int
    group_id: int
    operator_id: int
    duration: int
好友添加事件

class FriendAddNoticeEvent(NoticeEvent):
    好友添加事件

    notice_type: Literal["friend_add"]
    user_id: int
群消息撤回事件

class GroupRecallNoticeEvent(NoticeEvent):
    群消息撤回事件

    notice_type: Literal["group_recall"]
    user_id: int
    group_id: int
    operator_id: int
    message_id: int
好友消息撤回事件

class FriendRecallNoticeEvent(NoticeEvent):
    好友消息撤回事件

    notice_type: Literal["friend_recall"]
    user_id: int
    message_id: int
戳一戳提醒事件

class PokeNotifyEvent(NotifyEvent):
    戳一戳提醒事件

    sub_type: Literal["poke"]
    target_id: int
    group_id: Optional[int] = None
    raw_info: list =None
群红包运气王提醒事件

class LuckyKingNotifyEvent(NotifyEvent):
    群红包运气王提醒事件

    sub_type: Literal["lucky_king"]
    target_id: int
资料卡被赞事件

class ProfileLikeEvent(NotifyEvent):
    sub_type: Literal["profile_like"]
    operator_id: int
    operator_nick: str
    times: int
群荣誉变更提醒事件

class HonorNotifyEvent(NotifyEvent):
    群荣誉变更提醒事件

    sub_type: Literal["honor"]
    honor_type: str
好友申请

class FriendRequestEvent(RequestEvent):
    加好友请求事件

    request_type: Literal["friend"]
    user_id: int
    flag: str
    comment: Optional[str] = None
加群请求/邀请事件

class GroupRequestEvent(RequestEvent):
    加群请求/邀请事件

    request_type: Literal["group"]
    sub_type: str
    group_id: int
    user_id: int
    flag: str
    comment: Optional[str] = None

__all__ = [
    "MessageEvent",
    "PrivateMessageEvent",
    "GroupMessageEvent",
    "NoticeEvent",
    "GroupUploadNoticeEvent",
    "GroupAdminNoticeEvent",
    "GroupDecreaseNoticeEvent",
    "GroupIncreaseNoticeEvent",
    "GroupBanNoticeEvent",
    "FriendAddNoticeEvent",
    "GroupRecallNoticeEvent",
    "FriendRecallNoticeEvent",
    "NotifyEvent",
    "PokeNotifyEvent",
    "ProfileLikeEvent",
    "LuckyKingNotifyEvent",
    "HonorNotifyEvent",
    "RequestEvent",
    "FriendRequestEvent",
    "GroupRequestEvent",
    "MetaEvent",
    "LifecycleMetaEvent",
    "HeartbeatMetaEvent",
    "startUpMetaEvent"
]

## 事件属性
- event.pure_text: 纯文本内容
- event.user_id: 发送者ID
- event.group_id: 群组ID（群消息）
- event.message_id: 消息ID
- event.sender: 发送者信息

## Bot常用方法
- await bot.send(event, message): 发送消息
- await bot.send_group_message(group_id, message): 发送群消息
- await bot.send_friend_message(user_id, message): 发送私聊消息
- await bot.recall(message_id): 撤回消息
- await bot.mute(group_id, user_id, duration): 禁言
- await bot.group_poke(group_id, user_id): 戳一戳
- await bot.set_qq_avatar(self,file: str): file: http://，base64://,file://均可
- await bot.set_group_add_request(self,flag: str,approve: bool,reason: str):
        "
        处理加群请求
        :param flag: 请求id
        :param approve:
        :param reason:
        :return:
        "
- await bot.set_group_card(self,group_id: int,user_id: int,card: str): 设置群名片
- await bot.set_group_special_title(self,group_id: int,user_id: int,special_title: str): 设置群头衔
- await bot.send_group_sign(self,group_id: int): 发送群签到
- await bot.send_group_notice(self,group_id: int,content: str,image: str): 发送群公告


## 消息组件
```python
from developTools.message.message_components import Text, Image, At, Reply,Card

# 文本消息
Text("文本内容")

# 图片消息  
Image(file="图片路径或Url")

# @某人
At(qq=user_id)

# 回复消息
Reply(id=message_id)

Card(audio="音频url", title="标题", image="封面")
#message_chain仅支持文本和图片同时存在，其他消息组件之间相互不兼容。
```

## 配置文件使用
```python
# 从config中读取配置
api_key = config.get("api_key", "default_value")
```

## 注意事项
1. 所有插件都必须有main函数作为入口点
2. 事件处理函数必须是异步函数
3. 插件名称应该具有描述性
4. 使用event.pure_text进行文本匹配
5. 发送消息时可以使用字符串或消息组件列表
"""

    async def generate_plugin(self, requirement: str, plugin_name: str = None) -> Dict[str, Any]:
        """
        根据需求生成插件代码

        Args:
            requirement: 插件需求描述
            plugin_name: 插件名称（如果不提供则由AI生成）

        Returns:
            包含生成结果的字典
        """
        # 构建AI提示词
        prompt = self._build_ai_prompt(requirement, plugin_name)

        try:
            # 调用AI生成代码
            ai_response = await self.ai_reply_core(prompt)

            # 检查AI返回是否为None
            if ai_response is None:
                return {
                    "success": False,
                    "error": "AI返回结果为空",
                    "plugin_name": plugin_name or "unknown"
                }

            # 解析AI返回结果
            parsed_result = self._parse_ai_response(ai_response)

            if parsed_result and parsed_result.get("success"):
                # 创建插件文件
                plugin_path = self._create_plugin_files(parsed_result)
                parsed_result["plugin_path"] = str(plugin_path)

            return parsed_result or {
                "success": False,
                "error": "解析AI返回结果失败",
                "plugin_name": plugin_name or "unknown"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"生成插件时出错: {str(e)}",
                "plugin_name": plugin_name or "unknown"
            }

    def _build_ai_prompt(self, requirement: str, plugin_name: str = None) -> str:
        """构建发送给AI的提示词"""
        name_instruction = f"插件名称必须是: {plugin_name}" if plugin_name else "请为插件起一个合适的名称"

        return f"""
你是一个专业的Python插件开发助手。请严格按照以下SDK指南开发一个QQ机器人插件。

{self.sdk_guide}

## 开发需求
{requirement}

## 开发要求
{name_instruction}

请严格按照以下格式返回结果：

```json
{{
    "plugin_name": "插件目录名称（使用下划线，如：weather_plugin）",
    "plugin_description": "插件功能描述",
    "main_code": "主插件文件的完整Python代码",
    "init_code": "__init__.py文件的完整代码",
    "config_example": "配置文件示例（如果需要）",
    "usage_instructions": "插件使用说明"
}}
```

注意：
1. 代码必须完整可用，不能有省略
2. 必须使用提供的SDK接口
3. 代码中不要包含```python标记
4. 插件名称使用下划线命名法
5. 确保所有import语句正确
"""

    def _parse_ai_response(self, ai_response: Union[str, Dict, None]) -> Dict[str, Any]:
        """解析AI返回的结果"""
        try:
            # 处理不同类型的AI返回结果
            if ai_response is None:
                return {
                    "success": False,
                    "error": "AI返回结果为空",
                    "raw_response": None
                }

            # 如果是字典类型（如Gemini API返回格式）
            if isinstance(ai_response, dict):
                # 尝试提取文本内容
                text_content = self._extract_text_from_dict(ai_response)
                if not text_content:
                    return {
                        "success": False,
                        "error": "无法从AI返回结果中提取文本内容",
                        "raw_response": str(ai_response)
                    }
                ai_response = text_content

            # 如果不是字符串，转换为字符串
            if not isinstance(ai_response, str):
                ai_response = str(ai_response)

            # 尝试提取JSON部分
            json_match = re.search(r'```json\s*(.*?)\s*```', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 如果没有找到代码块，尝试直接解析
                json_str = ai_response.strip()

            result = json.loads(json_str)

            # 验证必需字段
            required_fields = ["plugin_name", "plugin_description", "main_code", "init_code"]
            for field in required_fields:
                if field not in result:
                    return {
                        "success": False,
                        "error": f"AI返回结果缺少必需字段: {field}",
                        "raw_response": ai_response
                    }

            result["success"] = True
            return result

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"解析AI返回的JSON时出错: {str(e)}",
                "raw_response": ai_response
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"处理AI返回结果时出错: {str(e)}",
                "raw_response": str(ai_response) if ai_response else None
            }

    def _extract_text_from_dict(self, response_dict: Dict) -> str:
        """从复杂的字典结构中提取文本内容"""
        try:
            # 处理Gemini API格式
            if 'candidates' in response_dict:
                candidates = response_dict['candidates']
                if candidates and len(candidates) > 0:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [])
                    if parts and len(parts) > 0:
                        return parts[0].get('text', '')

            # 处理OpenAI API格式
            if 'choices' in response_dict:
                choices = response_dict['choices']
                if choices and len(choices) > 0:
                    message = choices[0].get('message', {})
                    return message.get('content', '')

            # 处理其他可能的格式
            if 'text' in response_dict:
                return response_dict['text']

            if 'content' in response_dict:
                return response_dict['content']

            return ''

        except Exception:
            return ''

    def _create_plugin_files(self, parsed_result: Dict[str, Any]) -> Path:
        """创建插件文件"""
        plugin_name = parsed_result["plugin_name"]
        plugin_dir = self.base_path / plugin_name

        # 创建插件目录
        plugin_dir.mkdir(exist_ok=True)

        # 创建主插件文件
        main_file = plugin_dir / f"{plugin_name}.py"
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(parsed_result["main_code"])

        # 创建__init__.py文件
        init_file = plugin_dir / "__init__.py"
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write(parsed_result["init_code"])

        # 如果有配置示例，创建配置文件
        if parsed_result.get("config_example"):
            config_file = plugin_dir / "config_example.yaml"
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write(parsed_result["config_example"])

        return plugin_dir

    async def generate_multiple_plugins(self, requirements: List[str]) -> List[Dict[str, Any]]:
        """批量生成多个插件"""
        results = []
        for i, requirement in enumerate(requirements):
            print(f"正在生成第 {i + 1}/{len(requirements)} 个插件...")
            result = await self.generate_plugin(requirement)
            results.append(result)

            # 避免请求过于频繁
            if i < len(requirements) - 1:
                await asyncio.sleep(1)

        return results

    def list_generated_plugins(self) -> List[str]:
        """列出已生成的插件"""
        plugins = []
        if self.base_path.exists():
            for item in self.base_path.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    plugins.append(item.name)
        return plugins

    def get_plugin_info(self, plugin_name: str) -> Dict[str, Any]:
        """获取插件信息"""
        plugin_dir = self.base_path / plugin_name
        if not plugin_dir.exists():
            return {"error": "插件不存在"}

        try:
            # 读取__init__.py获取描述
            init_file = plugin_dir / "__init__.py"
            if init_file.exists():
                with open(init_file, 'r', encoding='utf-8') as f:
                    init_content = f.read()

                # 提取插件描述
                desc_match = re.search(r'plugin_description\s*=\s*["\'](.+?)["\']', init_content)
                description = desc_match.group(1) if desc_match else "无描述"
            else:
                description = "无描述"

            # 检查主文件
            main_file = plugin_dir / f"{plugin_name}.py"
            has_main_file = main_file.exists()

            return {
                "name": plugin_name,
                "description": description,
                "has_main_file": has_main_file,
                "plugin_dir": str(plugin_dir)
            }

        except Exception as e:
            return {"error": f"读取插件信息时出错: {str(e)}"}


# 使用示例
async def code_generate(config,prompt):


    from run.ai_code_generator.service.AiChatbot import AiChatbot
    base_url = config.ai_llm.config["llm"]["gemini"]["base_url"],
    api_key=random.choice(config.ai_llm.config["llm"]["gemini"]["api_keys"]),
    model=config.ai_llm.config["llm"]["gemini"]["model"],
    proxy=config.common_config.basic_config["proxy"]["http_proxy"]
    AiChatbot = AiChatbot(base_url=base_url, api_key=api_key, model=model,proxy=proxy)

    generator = AIPluginGenerator(AiChatbot.get_response)

    # 生成插件
    result = await generator.generate_plugin(prompt)

    if result["success"]:
        print(f"插件生成成功: {result['plugin_name']}")
        print(f"插件路径: {result['plugin_path']}")
    else:
        print(f"生成失败: {result['error']}")

    # 列出所有插件
    plugins = generator.list_generated_plugins()
    print(f"已生成的插件: {plugins}")


if __name__ == "__main__":
    asyncio.run(code_generate())