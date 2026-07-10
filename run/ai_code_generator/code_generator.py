from developTools.event.events import GroupMessageEvent
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from run.ai_code_generator.service.AiPluginGenerator import code_generate


def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        prefix = config.ai_code_generator.ai_coder["prefix"]
        if not event.pure_text.startswith(prefix):
            return

        user_info = await get_user(event.user_id)
        if user_info.permission <= config.ai_code_generator.ai_coder["code_generation_permission_need"]:
            await bot.send(event, "你没有权限生成插件")
            return

        prompt = event.pure_text.replace(prefix, "", 1).strip()
        if prompt == "":
            await bot.send(event, "请输入需求，例如：/写插件 生成一个 tool：判断整数是否为素数")
            return

        bot.logger.info(f"AI插件生成器收到需求:{prompt}")
        await bot.send(event, "正在生成，请稍候喵…")

        try:
            r = await code_generate(bot, config, prompt, event.user_id)
        except Exception as e:
            bot.logger.error(f"AI插件生成异常: {e}")
            await bot.send(event, f"生成失败：{e}")
            return

        if not r.get("success"):
            await bot.send(event, f"生成失败：{r.get('error', '未知错误')}")
            return

        await bot.send(event, _format_report(r))


def _format_report(r: dict) -> str:
    lines = [
        f"✅ 已生成：{r.get('plugin_name')}（{r.get('kind', 'plugin')}）",
        f"路径：{r.get('plugin_path')}",
        f"说明：{r.get('plugin_description', '')}",
    ]

    errors = r.get("syntax_errors") or []
    if errors:
        lines.append("⚠️ 语法检查发现问题（可能需要重新生成或手动修正）：")
        lines.extend(f"  - {e}" for e in errors)
    else:
        lines.append("语法检查：通过 ✅")

    act = r.get("activation") or {}
    if act.get("loaded"):
        lines.append("事件处理器：已加载 ✅")
    if r.get("has_tool"):
        if act.get("tool_registered"):
            lines.append(f"AI 工具：已动态注册 ✅（当前可用工具 {act.get('tool_count', '?')} 个）")
            lines.append("可在 WebUI「功能管理」里开关；下一条对话 mai_reply 即可调用。")
        else:
            lines.append(f"AI 工具：注册失败 ⚠️ {act.get('tool_error', '')}")
    if act.get("load_error"):
        lines.append(f"加载提示：{act.get('load_error')}")

    usage = r.get("usage_instructions")
    if usage:
        lines.append("—— 使用说明 ——")
        lines.append(str(usage))
    return "\n".join(lines)
