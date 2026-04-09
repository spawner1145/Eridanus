import os

from developTools.event.events import LifecycleMetaEvent, GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text, Image, Mface, At
from framework_common.ToolKits import Util
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import get_img, download_img, util
from run.meme_generate.service.arknights.main import composite_async

util=Util().get_instance()

def main(bot: ExtendBot,config: YAMLManager):
    temp_dict=[]
    @bot.on(GroupMessageEvent)
    async def group_message(event: GroupMessageEvent):
        #print(event.message_chain)
        #print(event.pure_text)
       # print("卫戍头像" in event.pure_text)
        if event.pure_text=="/卫戍头像":
            temp_dict.append(event.user_id)
            await bot.send(event,"请发送一张图片")
        elif event.message_chain.has(Text) and "卫戍头像" in event.message_chain.get(Text)[0].text and event.message_chain.has(At):
            bot.logger.info("正在制作卫戍头像")
            at_aim=event.message_chain.get(At)[0].qq
            avatar_url=f"https://q1.qlogo.cn/g?b=qq&nk={at_aim}&s=640"
            rel_img_path = f"data/pictures/cache/{event.user_id}.png"
            rel_out_path = f"data/pictures/cache/{event.user_id}_avatar.png"
            await download_img(avatar_url, rel_img_path)
            abs_img_path = os.path.abspath(rel_img_path)
            abs_out_path = os.path.abspath(rel_out_path)
            try:
                result_img = await composite_async(
                    user_photo_path=abs_img_path,
                    output_path=abs_out_path,
                    filter_strength=50,
                    show_badge=True,
                    zoom=1.0
                )
                await bot.send(event, Image(file=rel_out_path))
                # 合成成功后，接下来你就可以用 abs_out_path 发送图片了
                # await send_image(abs_out_path)

            except Exception as e:
                print(f"头像合成失败: {e}")
    @bot.on(GroupMessageEvent)
    async def group_message(event: GroupMessageEvent):
        if event.user_id in temp_dict and event.message_chain.has(Image):
            temp_dict.remove(event.user_id)
            img=await get_img(event,bot)
            rel_img_path = f"data/pictures/cache/{event.user_id}.png"
            rel_out_path = f"data/pictures/cache/{event.user_id}_avatar.png"
            await download_img(img, rel_img_path)

            abs_img_path = os.path.abspath(rel_img_path)
            abs_out_path = os.path.abspath(rel_out_path)
            try:
                result_img = await composite_async(
                    user_photo_path=abs_img_path,
                    output_path=abs_out_path,
                    filter_strength=50,
                    show_badge=True,
                    zoom=1.0
                )
                await bot.send(event,Image(file=rel_out_path))
                # 合成成功后，接下来你就可以用 abs_out_path 发送图片了
                # await send_image(abs_out_path)

            except Exception as e:
                print(f"头像合成失败: {e}")

