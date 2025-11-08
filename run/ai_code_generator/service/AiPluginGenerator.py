import os
import random
import re
import json
import asyncio
import shutil
from typing import Dict, Any, List, Union
from pathlib import Path

from framework_common.utils.system_logger import get_logger
from run.ai_llm.service.schemaReplyCore import schemaReplyCore
logger = get_logger("ai_AIPluginGenerator")

class AIPluginGenerator:
    def __init__(self, base_path: str = "run"):
        """
        AI插件代码生成器

        Args:
            base_path: 插件生成的基础路径
        """

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
Image(file="图片路径或Url") #只需要传入file参数即可，其他参数无需传入

# @某人
At(qq=user_id)

# 回复消息
Reply(id=message_id)

Card(audio="音频url", title="标题", image="封面")
#message_chain仅支持文本和图片同时存在，其他消息组件之间相互不兼容。
```

## 配置文件使用
```
# 从config中读取配置
value = config.{module_name}{config_name}[key]
如插件名称为weather_plugin，配置文件名为config.yaml，假设此时配置文件内容为
api_key: your_api_key
则读取方式为：
api_key = config.weather_plugin.config[‘api_key’]


```
## 导入非python标准库
```python
from framework_common.utils.install_and_import import install_and_import
module = install_and_import(package_name, import_name) 
#然后进行进一步的导入
```

## 注意事项
1. 所有插件都必须有main函数作为入口点
2. 事件处理函数必须是异步函数
3. 插件名称应该具有描述性
4. 使用event.pure_text进行文本匹配
5. 发送消息时可以使用字符串或消息组件列表
"""

    async def generate_plugin(self, ai_response: Dict[str, Any], plugin_name: str = None) -> Dict[str, Any]:
        """
        根据需求生成插件代码

        Args:
            ai_response: AI返回的字典结果（已经是解析后的格式）
            plugin_name: 插件名称（如果不提供则使用AI返回的名称）

        Returns:
            包含生成结果的字典
        """
        try:
            # 检查AI返回是否有效
            if ai_response is None:
                return {
                    "success": False,
                    "error": "AI返回结果为空",
                    "plugin_name": plugin_name or "unknown"
                }

            # 验证AI返回的字典格式
            if not isinstance(ai_response, dict):
                return {
                    "success": False,
                    "error": f"AI返回结果格式错误，期望字典类型，实际为: {type(ai_response)}",
                    "plugin_name": plugin_name or "unknown",
                    "raw_response": str(ai_response)
                }

            # 验证必需字段
            required_fields = ["plugin_name", "plugin_description", "main_code", "init_code"]
            missing_fields = [field for field in required_fields if field not in ai_response]

            if missing_fields:
                return {
                    "success": False,
                    "error": f"AI返回结果缺少必需字段: {', '.join(missing_fields)}",
                    "plugin_name": plugin_name or ai_response.get("plugin_name", "unknown"),
                    "raw_response": ai_response
                }

            # 如果指定了插件名称，则覆盖AI返回的名称
            if plugin_name:
                ai_response["plugin_name"] = plugin_name

            # 创建插件文件
            plugin_path = self._create_plugin_files(ai_response)

            # 返回成功结果
            result = ai_response.copy()
            result["success"] = True
            result["plugin_path"] = str(plugin_path)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"生成插件时出错: {str(e)}",
                "plugin_name": plugin_name or ai_response.get("plugin_name", "unknown") if ai_response else "unknown",
                "raw_response": ai_response if ai_response else None
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

请严格按照Schema格式返回结果，包含以下字段：
- plugin_name: 插件目录名称（使用下划线，如：weather_plugin）
- plugin_description: 插件功能描述
- main_code: 主插件文件的完整Python代码
- init_code: __init__.py文件的完整代码
- config: 配置文件示例（如果需要，否则返回空JSON对象字符串）
- usage_instructions: 插件使用说明

注意：
1. 代码必须完整可用，不能有省略
2. 必须使用提供的SDK接口
3. 插件名称使用下划线命名法
4. 确保所有import语句正确
5. config.yaml如果不需要配置，请生成一个空的key value对
6. 当用户要求重新生成或修改时，新的插件名必须和先前生成的插件名保持一致
**7. 如果使用了非python标准库，必须使用如下方式导入。此方式可以自动安装并导入依赖包。
from framework_common.utils.install_and_import import install_and_import
module = install_and_import(package_name, import_name) 

"""

    def _create_plugin_files(self, parsed_result: Dict[str, Any]) -> Path:
        """创建插件文件"""
        plugin_name = parsed_result["plugin_name"]
        plugin_dir = self.base_path / plugin_name
        if plugin_dir.exists():
            logger.warning(f"插件目录 {plugin_dir} 已存在，将删除该目录及其内容")

            # 强制垃圾回收，释放可能的文件句柄
            import gc
            gc.collect()

            # 稍等一下让系统释放文件句柄
            import time
            time.sleep(0.1)

            try:
                shutil.rmtree(plugin_dir)
            except PermissionError as e:
                logger.error(f"删除目录失败: {e}")
                # 重命名作为备用方案
                backup_name = f"{plugin_name}_old_{int(time.time())}"
                backup_dir = self.base_path / backup_name
                plugin_dir.rename(backup_dir)
                logger.info(f"已重命名为: {backup_dir}")

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

        # 如果有配置示例且不是空的JSON对象，创建配置文件
        config_example = parsed_result.get("config", "")
        if config_example and config_example.strip() not in ["", "{}"]:
            config_file = plugin_dir / "config.yaml"
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write(config_example)

        return plugin_dir

    async def generate_multiple_plugins(self, requirements: List[str]) -> List[Dict[str, Any]]:
        """批量生成多个插件"""
        results = []
        for i, requirement in enumerate(requirements):
            print(f"正在生成第 {i + 1}/{len(requirements)} 个插件...")

            # 构建提示词
            prompt = self._build_ai_prompt(requirement)

            # 调用AI获取结果
            from framework_common.framework_util.yamlLoader import YAMLManager
            ai_response = await schemaReplyCore(
                config=YAMLManager("run"),
                schema=self._get_plugin_schema(),
                user_message=prompt,
                user_id=1000
            )

            # 生成插件
            result = await self.generate_plugin(ai_response)
            results.append(result)

            # 避免请求过于频繁
            if i < len(requirements) - 1:
                await asyncio.sleep(1)

        return results

    def _get_plugin_schema(self) -> Dict[str, Any]:
        """获取插件定义的Schema"""
        return {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "插件目录名称（使用下划线命名，如：weather_plugin）。"
                },
                "plugin_description": {
                    "type": "string",
                    "description": "插件功能描述，应清晰简洁。"
                },
                "main_code": {
                    "type": "string",
                    "description": "主插件文件（例如：main.py）的完整Python代码。代码应能实际工作，包含所有必要的导入和功能逻辑。"
                },
                "init_code": {
                    "type": "string",
                    "description": "__init__.py文件的完整Python代码，通常用于初始化包或导出模块。如果不需要，可以是空字符串。"
                },
                "config": {
                    "type": "string",
                    "description": "配置文件（例如：config.json）的示例内容，用于配置API密钥等敏感信息或可变参数。内容应是有效的JSON字符串。如果不需要配置，请返回空JSON对象 `{}` 的字符串表示。"
                },
                "usage_instructions": {
                    "type": "string",
                    "description": "插件的详细使用说明，包括安装步骤、配置方法和调用示例代码。内容应清晰易懂，可以直接用于指导用户。"
                }
            },
            "required": [
                "plugin_name",
                "plugin_description",
                "main_code",
                "init_code",
                "config",
                "usage_instructions"
            ]
        }

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
async def code_generate(config,prompt,user_id):
    """简化的代码生成函数"""
    generator = AIPluginGenerator()

    # 构建AI提示词
    ai_prompt = generator._build_ai_prompt(requirement=prompt)
    #print("发送给AI的提示词:")
    #print(ai_prompt)
    #print("-" * 50)

    # 调用schemaReplyCore获取AI响应
    from framework_common.framework_util.yamlLoader import YAMLManager
    ai_response = await schemaReplyCore(
        config=config,
        keep_history=True,
        schema=generator._get_plugin_schema(),
        user_message=ai_prompt,
        user_id=int(f"{user_id}1024"),
        model_set=config.ai_code_generator.ai_coder["使用模型"]
    )



    # 生成插件
    result = await generator.generate_plugin(ai_response)

    logger.info("插件生成结果:")
    if result["success"]:
        logger.info(f"✅ 插件生成成功!")
        logger.info(f"插件名称: {result['plugin_name']}")
        logger.info(f"插件描述: {result['plugin_description']}")
        logger.info(f"插件路径: {result['plugin_path']}")
        logger.info(f"使用说明: {result.get('usage_instructions', '无')}")
    else:
        logger.error(f"❌ 插件生成失败: {result['error']}")

    return result


if __name__ == "__main__":
    asyncio.run(code_generate("你好，请为我开发一个你好插件，当用户发送“你好”时，回复“你好，欢迎使用我的插件！"))