import ast
import asyncio
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List

from framework_common.utils.system_logger import get_logger

logger = get_logger("ai_AIPluginGenerator")


class AIPluginGenerator:
    def __init__(self, base_path: str = "run"):
        """AI 插件 / tool 代码生成器。base_path 为插件生成目录（run）。"""
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.sdk_guide = self._build_sdk_guide()

    # ------------------------------------------------------------------ #
    # SDK 指南（发给模型的“知识”）——覆盖 事件插件 与 function-calling tool 两类产物
    # ------------------------------------------------------------------ #
    def _build_sdk_guide(self) -> str:
        return r'''
# Eridanus 插件 / Tool 开发 SDK 指南

Eridanus 有两类可生成产物：
- **事件插件（plugin）**：注册 `@bot.on(事件)` 处理器，响应群/私聊消息、通知等（如 “收到 ping 回复 pong”）。
- **函数调用工具（tool）**：给 AI 对话插件 mai_reply 使用的能力。AI 判断需要时自动调用；调用结果回给模型。
两者可共存（both）。

## 目录结构
```
run/<plugin_name>/
├─ __init__.py          # 必需。plugin_description；若含 tool，还要 dynamic_imports + function_declarations
├─ main.py              # 事件插件入口（tool-only 可不生成，main_code 置空）
├─ func_collection.py   # tool 实现（仅 tool/both 时生成，tool_code 置空则不生成）
└─ config.yaml          # 可选。需要配置项时生成
```
插件目录名用小写下划线命名（如 weather_query）。

## __init__.py
- 纯插件：
```python
plugin_description = "天气查询：发送 天气 城市 返回该城市天气"
```
- 含 tool：额外声明 dynamic_imports（模块路径 → 函数名列表）与 function_declarations（发给大模型的函数签名）：
```python
plugin_description = "素数工具：判断整数是否为素数"

dynamic_imports = {
    "run.prime_tool.func_collection": ["is_prime"],
}

function_declarations = [
    {
        "name": "is_prime",
        "description": "判断一个整数是否为素数。当用户询问某数是否为质数/素数时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "要判断的整数"}
            },
            "required": ["n"],
        },
    },
]
```
注意：dynamic_imports 的 key 必须是 `run.<plugin_name>.func_collection` 这种真实可导入的模块路径；
value 里的函数名必须与 func_collection.py 中的函数名、以及 function_declarations 里的 name 完全一致。

## main.py（事件插件入口）
入口固定为 `def main(bot, config):`，在其中用装饰器注册处理器。**处理函数必须是 async**。
```python
from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text, Image, At
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager


def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        if event.pure_text == "ping":
            await bot.send(event, "pong")

    @bot.on(PrivateMessageEvent)
    async def _(event: PrivateMessageEvent):
        pass
```

## func_collection.py（tool 实现）
每个 tool 是一个 **async 函数**，签名固定按需声明 `bot`、`event`、`config`，其余参数与 function_declarations
的 parameters 对应。框架按“形参名”注入：若形参里有 `bot`/`event`/`config` 就会被自动传入，其余来自模型。
函数可以直接用 `await bot.send(event, ...)` 发消息；**返回值（字符串/可 JSON 化对象）会作为工具结果回传给模型**，
所以建议 return 一段简短结果文本，便于模型继续对话。
```python
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager


async def is_prime(n: int, bot: ExtendBot = None, event=None, config: YAMLManager = None):
    """判断 n 是否为素数。"""
    n = int(n)
    if n < 2:
        return f"{n} 不是素数"
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return f"{n} 不是素数（可被 {i} 整除）"
    return f"{n} 是素数"
```
tool 无需在 main.py 注册，也无需重启：生成后框架会自动重扫并注册，随后可在 WebUI「功能管理」里开关。

## 事件对象常用属性
- event.pure_text: 纯文本内容
- event.user_id: 发送者 QQ
- event.group_id: 群号（群消息）
- event.message_id: 消息 id
- event.sender: 发送者信息

## Bot 常用方法（均为 async）
- await bot.send(event, 消息)                      # 消息可为字符串，或消息组件列表
- await bot.send_group_message(group_id, 消息)
- await bot.send_friend_message(user_id, 消息)
- await bot.recall(message_id)                     # 撤回
- await bot.mute(group_id, user_id, duration)      # 禁言（秒）
- await bot.send_group_sign(group_id)              # 群签到

## 消息组件
```python
from developTools.message.message_components import Text, Image, At, Record, File, Reply, Node, Music, Video, Face
Text("文本")
Image(file="http:// 或 file:// 或 base64:// 或本地路径")   # 只需传 file
At(qq=123456)
Record(file="音频url/路径")     # 语音
File(file="文件路径", name="名称")
Reply(id=message_id)            # 引用回复
Music(type="163", id=歌曲id)    # 音乐卡片
# 发送示例：
await bot.send(event, [Text("看图："), Image(file=url)])
await bot.send(event, "纯文本也行")
```

## 读取配置（config.yaml）
配置按“插件目录名 + 文件名(去 .yaml)”访问：`config.<plugin_name>.<yaml文件名>[key]`。
config.yaml 的文件名是 config，所以：
```python
api_key = config.weather_query.config["api_key"]
```

## 使用第三方库（自动安装并导入）
```python
from framework_common.utils.install_and_import import install_and_import
httpx = install_and_import("httpx")          # pip 名与 import 名相同
bs4 = install_and_import("beautifulsoup4", "bs4")   # 不同则给出 import 名
```

## 硬性要求
1. 代码必须完整可运行，禁止省略号/伪代码。
2. 所有事件处理函数与 tool 函数都必须是 async。
3. 目录名、dynamic_imports 的函数名、function_declarations 的 name、func_collection.py 的函数名，四者必须一致。
4. 用户要求“重新生成/修改”时，plugin_name 必须与上次一致。
5. 用到非标准库时，必须用 install_and_import。
6. tool-only 时 main_code 置空字符串；纯事件插件时 tool_code 置空字符串、__init__ 不写 dynamic_imports/function_declarations。
'''

    # ------------------------------------------------------------------ #
    # Schema / Prompt
    # ------------------------------------------------------------------ #
    def _get_plugin_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["plugin", "tool", "both"],
                    "description": "产物类型：plugin=事件插件；tool=AI 函数调用工具；both=两者都要。",
                },
                "plugin_name": {
                    "type": "string",
                    "description": "插件目录名（小写下划线，如 prime_tool）。",
                },
                "plugin_description": {
                    "type": "string",
                    "description": "插件功能描述，简洁清晰。",
                },
                "init_code": {
                    "type": "string",
                    "description": "__init__.py 完整代码。必含 plugin_description；含 tool 时还要 dynamic_imports 与 function_declarations。",
                },
                "main_code": {
                    "type": "string",
                    "description": "main.py 完整代码（含 def main(bot, config) 与事件处理器）。kind=tool 时置为空字符串。",
                },
                "tool_code": {
                    "type": "string",
                    "description": "func_collection.py 完整代码（被 dynamic_imports 引用的 async tool 函数）。kind=plugin 时置为空字符串。",
                },
                "config": {
                    "type": "string",
                    "description": "config.yaml 示例内容（YAML）。不需要配置则返回空字符串。",
                },
                "usage_instructions": {
                    "type": "string",
                    "description": "使用说明（触发方式 / 配置 / 示例）。",
                },
            },
            "required": [
                "kind", "plugin_name", "plugin_description",
                "init_code", "main_code", "tool_code", "config", "usage_instructions",
            ],
        }

    def _build_ai_prompt(self, requirement: str, plugin_name: str = None) -> str:
        name_instruction = f"插件名称必须是: {plugin_name}" if plugin_name else "请为插件起一个合适的小写下划线名称"
        return f"""你是资深的 Eridanus 机器人插件工程师。请严格依据下面的 SDK 指南完成开发需求。

{self.sdk_guide}

## 开发需求
{requirement}

## 输出要求
{name_instruction}
判断该需求更适合做“事件插件(plugin)”、“AI 函数调用工具(tool)”还是“both”，并在 kind 字段说明。
- 若是给 AI 对话使用的能力（查询/计算/检索等，由 AI 需要时调用），应生成 tool（func_collection.py + __init__ 的 dynamic_imports/function_declarations）。
- 若是响应具体聊天指令/事件，应生成事件插件（main.py）。
严格按 schema 返回 JSON，字段：kind, plugin_name, plugin_description, init_code, main_code, tool_code, config, usage_instructions。
未使用的代码字段（如 tool-only 的 main_code）返回空字符串。所有代码必须完整、可直接运行。
"""

    # ------------------------------------------------------------------ #
    # 生成 / 写盘 / 校验
    # ------------------------------------------------------------------ #
    async def generate_plugin(self, ai_response: Dict[str, Any], plugin_name: str = None) -> Dict[str, Any]:
        if ai_response is None:
            return {"success": False, "error": "AI 返回结果为空", "plugin_name": plugin_name or "unknown"}
        if not isinstance(ai_response, dict):
            return {"success": False, "error": f"AI 返回格式错误，期望 dict，实际 {type(ai_response)}",
                    "plugin_name": plugin_name or "unknown", "raw_response": str(ai_response)}

        required = ["plugin_name", "plugin_description", "init_code"]
        missing = [f for f in required if not str(ai_response.get(f, "")).strip()]
        if missing:
            return {"success": False, "error": f"AI 返回缺少必需字段: {', '.join(missing)}",
                    "plugin_name": plugin_name or ai_response.get("plugin_name", "unknown"),
                    "raw_response": ai_response}

        if plugin_name:
            ai_response["plugin_name"] = plugin_name

        try:
            plugin_path = self._create_plugin_files(ai_response)
        except Exception as e:
            return {"success": False, "error": f"写入插件文件出错: {e}",
                    "plugin_name": ai_response.get("plugin_name", "unknown"), "raw_response": ai_response}

        result = dict(ai_response)
        result["success"] = True
        result["plugin_path"] = str(plugin_path)
        # 是否含 tool：tool_code 非空，或 __init__ 里声明了 function_declarations
        result["has_tool"] = bool(str(ai_response.get("tool_code", "")).strip()) \
            or ("function_declarations" in str(ai_response.get("init_code", "")))
        return result

    def _create_plugin_files(self, parsed: Dict[str, Any]) -> Path:
        plugin_name = parsed["plugin_name"]
        plugin_dir = self.base_path / plugin_name

        if plugin_dir.exists():
            logger.warning(f"插件目录 {plugin_dir} 已存在，将覆盖")
            import gc, time
            gc.collect()
            time.sleep(0.1)
            try:
                shutil.rmtree(plugin_dir)
            except PermissionError as e:
                logger.error(f"删除目录失败: {e}")
                backup = self.base_path / f"{plugin_name}_old_{int(time.time())}"
                plugin_dir.rename(backup)
                logger.info(f"已重命名旧目录为: {backup}")

        plugin_dir.mkdir(exist_ok=True)

        # __init__.py（必需）
        (plugin_dir / "__init__.py").write_text(parsed["init_code"], encoding="utf-8")

        # main.py（事件插件，可空）
        main_code = str(parsed.get("main_code", "")).strip()
        if main_code:
            (plugin_dir / "main.py").write_text(parsed["main_code"], encoding="utf-8")

        # func_collection.py（tool，可空）
        tool_code = str(parsed.get("tool_code", "")).strip()
        if tool_code:
            (plugin_dir / "func_collection.py").write_text(parsed["tool_code"], encoding="utf-8")

        # config.yaml（可选）
        config_example = str(parsed.get("config", "")).strip()
        if config_example and config_example not in ("{}", "{ }"):
            (plugin_dir / "config.yaml").write_text(parsed["config"], encoding="utf-8")

        return plugin_dir

    def syntax_check(self, plugin_path) -> List[str]:
        """ast.parse 校验目录下所有 .py，返回错误列表（空=通过）。"""
        errors = []
        for pyfile in Path(plugin_path).glob("*.py"):
            try:
                ast.parse(pyfile.read_text(encoding="utf-8"))
            except SyntaxError as e:
                errors.append(f"{pyfile.name}:{e.lineno}: {e.msg}")
            except Exception as e:
                errors.append(f"{pyfile.name}: {e}")
        return errors

    async def activate(self, bot, plugin_name: str, has_tool: bool) -> Dict[str, Any]:
        """激活生成的插件：加载事件处理器；若含 tool 则重扫 func_map 并刷新 mai_reply。"""
        info = {"loaded": False, "tool_registered": False}
        try:
            if bot is not None and hasattr(bot, "load_plugin"):
                info["loaded"] = bool(await bot.load_plugin(plugin_name))
        except Exception as e:
            info["load_error"] = str(e)
            logger.warning(f"[ai_code_generator] load_plugin({plugin_name}) 失败: {e}")

        if has_tool:
            try:
                from framework_common.framework_util.func_map_loader import rescan
                rescan()
                from run.mai_reply.service.reply_engine import refresh_tools
                info["tool_count"] = refresh_tools()
                info["tool_registered"] = True
            except Exception as e:
                info["tool_error"] = str(e)
                logger.warning(f"[ai_code_generator] tool 注册失败: {e}")
        return info

    def list_generated_plugins(self) -> List[str]:
        plugins = []
        if self.base_path.exists():
            for item in self.base_path.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    plugins.append(item.name)
        return plugins


# ---------------------------------------------------------------------- #
# 供 code_generator.py 调用的入口
# ---------------------------------------------------------------------- #
async def code_generate(bot, config, prompt, user_id):
    """生成插件/tool：调用专用端点 → 写盘 → 语法校验 → 激活（含 tool 动态注册）。"""
    generator = AIPluginGenerator()
    ai_prompt = generator._build_ai_prompt(requirement=prompt)

    from run.ai_code_generator.service.llm_backend import generate_structured
    ai_response = await generate_structured(config, generator._get_plugin_schema(), ai_prompt, user_id=user_id)

    result = await generator.generate_plugin(ai_response)
    if not result.get("success"):
        logger.error(f"❌ 插件生成失败: {result.get('error')}")
        return result

    result["syntax_errors"] = generator.syntax_check(result["plugin_path"])
    result["activation"] = await generator.activate(bot, result["plugin_name"], result.get("has_tool", False))

    logger.info(f"✅ 插件生成: {result['plugin_name']} ({result.get('kind')}), "
                f"syntax_errors={result['syntax_errors']}, activation={result['activation']}")
    return result


if __name__ == "__main__":
    asyncio.run(code_generate(None, None, "生成一个 tool：判断整数是否为素数", 1000))
