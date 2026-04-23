from developTools.event.events import GroupMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import get_img
from run.ai_generated_art.function_collection import gptimage2_text2img, image_edit


def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if event.pure_text.startswith("/gi2"):
            prompt = event.pure_text[len("/gi2"):].strip()

            await gptimage2_text2img(bot,event,config,prompt)
        elif event.pure_text.startswith("/图像编辑 "):
            prompt = event.pure_text[len("/图像编辑 "):].strip()
            image_url=await get_img(event,bot)
            if not image_url:
                await bot.send(event,"消息中必须包含图片")
                return
            await image_edit(bot,event,config,prompt,image_url)
