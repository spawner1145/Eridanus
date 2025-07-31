from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Text
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from run.ai_code_generator.service.AiPluginGenerator import code_generate


def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        if event.pure_text.startswith(config.ai_code_generator.ai_coder["prefix"]):
            if event.sender.user_id>config.ai_code_generator.ai_coder["code_generation_permission_need"]:
                prompt=event.pure_text.replace(config.ai_code_generator.ai_coder["prefix"],"").strip()
                bot.logger.info(f"AI插件生成器收到需求:{prompt}")
                r=await code_generate(config,prompt,event.user_id)
                await bot.send(event, "请查看控制台输出以验证")
            else:
                await bot.send(event, "你没有权限生成插件")