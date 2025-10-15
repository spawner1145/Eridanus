from .service.aoyi import generate_animation
from framework_common.utils.utils import download_img, url_to_base64, get_img, delay_recall
from framework_common.utils.random_str import random_str
from developTools.message.message_components import Image, Node, Text
from developTools.event.events import GroupMessageEvent
import os
from PIL import Image as PILImage
from io import BytesIO

def main(bot, config):
    CACHE_PATH = "data/pictures/cache/"
    os.makedirs(CACHE_PATH, exist_ok=True)
    
    @bot.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        if str(event.pure_text).startswith("/aoyi "):
            img_url = await get_img(event, bot)
            if not img_url:
                msg = await bot.send(event, "用法: /aoyi 文本, 记得引用图片")
                await delay_recall(bot, msg)
                return
            
            text = str(event.pure_text).replace("/aoyi ", "")
            if not text:
                msg = await bot.send(event, "用法: /aoyi 文本, 记得引用图片")
                await delay_recall(bot, msg)
                return
            
            try:
                # 下载原始图片
                temp_path = os.path.join(CACHE_PATH, f"{random_str()}.tmp")
                temp_path = await download_img(img_url, temp_path)
                
                # 检查是否为GIF并处理
                img_path = os.path.join(CACHE_PATH, f"{random_str()}.png")
                with PILImage.open(temp_path) as img:
                    # 如果是GIF，取第一帧
                    if img.format == "GIF":
                        img.seek(0)  # 确保在第一帧
                        # 转换为RGBA以支持透明通道
                        if img.mode in ('RGBA', 'LA'):
                            background = PILImage.new(img.mode[:-1], img.size, (255, 255, 255))
                            background.paste(img, img.split()[-1])
                            img = background
                        img.save(img_path, "PNG")
                    else:
                        # 非GIF直接转换为PNG
                        img.save(img_path, "PNG")
                
                # 清理临时文件
                os.remove(temp_path)
                
                # 生成动画
                gif_path = os.path.join(CACHE_PATH, f"{random_str()}.gif")
                msg = await bot.send(event, "正在生成奥义图", True)
                await delay_recall(bot, msg)
                gif_path = await generate_animation(img_path, gif_path, text)
                await bot.send(event, [Image(file=gif_path)], True)
                
            except Exception as e:
                error_msg = await bot.send(event, f"处理失败: {str(e)}")
                await delay_recall(bot, error_msg)
