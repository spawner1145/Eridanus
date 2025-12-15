from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from developTools.message.message_components import Text, Image, At
from framework_common.utils.install_and_import import install_and_import
from io import BytesIO
import shlex
import json
import asyncio
from pathlib import Path
import base64
import uuid

# --- 使用 install_and_import 导入必要的库 ---
emoji = install_and_import("emoji", "emoji")

# 修复 pilmoji 需要的 get_emoji_unicode_dict 函数缺失问题
emoji.unicode_codes.get_emoji_unicode_dict = lambda lang: {
    data[lang]: emj
    for emj, data in emoji.EMOJI_DATA.items()
    if lang in data and data['status'] <= emoji.STATUS['fully_qualified']
}
# 修复结束

requests = install_and_import("requests", "requests")
Pillow_module = install_and_import("Pillow", "PIL")
pilmoji_module = install_and_import("pilmoji", "pilmoji")

Image_PIL = Pillow_module.Image
ImageDraw_PIL = Pillow_module.ImageDraw
ImageFont_PIL = Pillow_module.ImageFont
Pilmoji = pilmoji_module.Pilmoji

# 加载配置
try:
    yaml_manager = YAMLManager(Path(__file__).parent / "config.yaml")
    config = yaml_manager.load()
except Exception:
    config = {}

def auto_newline(emoji: Pilmoji, xy: tuple[int, int], text: str, font: ImageFont_PIL.FreeTypeFont, init_fontsize: int, max_width: int) -> str:
    width, _ = emoji.getsize(text, font.font_variant(size=init_fontsize))
    # print(width/max_width)
    div = int((width/max_width)**(0.5+5/len(text)))
    # div = 2
    if div==0:
        emoji.text((xy[0]+(max_width-width)//2, xy[1]), text, 'black', font.font_variant(size=init_fontsize), align='center', emoji_position_offset=(0, round(30/145*init_fontsize)))
        return
    ffont = font.font_variant(size=init_fontsize//int(div))
    step = len(text) // div + 1
    lines = [text[i:i+step] for i in range(0, len(text), step)]
    final = '\n'.join(lines)
    final_size = emoji.getsize(final, ffont)
    img_text = Image_PIL.new("RGB", (int(final_size[0]), int(final_size[1]+30)), (255, 255, 255))
    with Pilmoji(img_text) as text_emoji:
        y = 0
        for line in lines:
            dx, dy = text_emoji.getsize(line, ffont)
            text_emoji.text(((img_text.size[0]-dx)//2, y), line, 'black', ffont, align='center', emoji_position_offset=(0, round(30/145*(init_fontsize//int(div)))))
            y += dy
    rate = min(max_width/img_text.size[0], init_fontsize/img_text.size[1])
    new_size = tuple(map(lambda x: x*rate, img_text.size))
    emoji.image.paste(img_text.resize(map(int, new_size)), (int(xy[0]+(max_width-new_size[0])//2), int(xy[1]+(init_fontsize-new_size[1])//2)))

def clean_cache(cache_dir: Path, max_age_seconds: int = 3600):
    """清理指定目录下超过 max_age_seconds 的文件"""
    try:
        if not cache_dir.exists():
            return
        
        import time
        current_time = time.time()
        
        for file_path in cache_dir.iterdir():
            if file_path.is_file():
                try:
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        # print(f"[god_meme_generator] Cleaned cache file: {file_path}")
                except Exception as e:
                    print(f"[god_meme_generator] Error deleting cache file {file_path}: {e}")
    except Exception as e:
        print(f"[god_meme_generator] Error cleaning cache: {e}")

async def get_user_nickname(bot: ExtendBot, user_id: str, group_id: int = None) -> str:
    """获取用户昵称，优先获取群名片"""
    try:
        if group_id:
            try:
                info_wrapper = await bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id))
                # 处理包装字典 {'data': {...}}
                if info_wrapper and isinstance(info_wrapper, dict) and 'data' in info_wrapper:
                    info = info_wrapper['data']
                    return info.get('card') or info.get('nickname') or str(user_id)
            except Exception:
                # 如果获取群成员信息失败（可能不在群里），尝试获取陌生人信息
                pass
        
        info_wrapper = await bot.get_stranger_info(user_id=int(user_id))
        if info_wrapper and isinstance(info_wrapper, dict) and 'data' in info_wrapper:
             info = info_wrapper['data']
             return info.get('nickname') or str(user_id)
        elif isinstance(info_wrapper, dict):
             return info_wrapper.get('nickname') or str(user_id)
             
        return str(user_id)
    except Exception as e:
        print(f"Error fetching nickname for {user_id}: {e}")
        return str(user_id)

def generate_meme_image(qqId, name, comment, call, appel):
    try:
        resp = requests.get(f'http://q.qlogo.cn/headimg_dl?dst_uin={qqId}&spec=640&img_type=jpg')
        resp.raise_for_status()
        io = BytesIO(resp.content)
        img = Image_PIL.open(io)
    except Exception as e:
        print(f"Error downloading avatar: {e}")
        return None
    
    meme = Image_PIL.new("RGB", (1024, 1024), (255, 255, 255))
    
    #使用漫朔的字体
    default_font_bd = Path("framework_common/manshuo_draw/data/fort/LXGWWenKai-Bold.ttf")
    default_font = Path("framework_common/manshuo_draw/data/fort/LXGWWenKai-Regular.ttf")
    
    font_path_bd = config.get('font_msyhbd_path', str(default_font_bd))
    font_path = config.get('font_msyh_path', str(default_font))
    
    def get_valid_font_path(path_str):
        # 1. 检查绝对路径或相对于当前工作目录的路径是否存在
        p = Path(path_str)
        if p.exists(): return str(p)
        
        # 2. 检查相对于插件目录的路径
        plugin_dir = Path(__file__).parent
        p_local = plugin_dir / path_str
        if p_local.exists(): return str(p_local)
        
        # 3. 如果配置的字体失败，回退到系统字体
        if "msyh" in path_str.lower():
             return r'C:\Windows\Fonts\MSYH.TTC'
             
        return path_str

    try:
        # 获取实际存在的字体路径
        real_font_bd = get_valid_font_path(font_path_bd)
        real_font = get_valid_font_path(font_path)
        
        # 尝试加载，指定 index=0 以防万一
        # 注意：在 Linux 上，PIL 可能需要绝对路径
        fontDB = ImageFont_PIL.truetype(str(Path(real_font_bd).resolve()), size=10, index=0)
        font = ImageFont_PIL.truetype(str(Path(real_font).resolve()), size=10, index=0)
    except Exception as e:
        import os
        plugin_dir = Path(__file__).parent
        files = os.listdir(plugin_dir)
        error_msg = f"字体加载失败: {str(e)}\n尝试路径: {real_font_bd}, {real_font}\n目录文件: {files}"
        print(error_msg)
        raise Exception(error_msg)

    with Pilmoji(meme) as emoji:
        auto_newline(emoji, (10, 10), f'请问你见到 {name} 了吗', fontDB, 145, 1004)
        meme.paste(img.resize((690, 690)), (167, 160))
        auto_newline(emoji, (10, 854), f'非常{comment}！简直就是{call}!', fontDB, 110, 1004)
        auto_newline(emoji, (0, 964), f'{appel}也没失踪也没怎么样，我只是觉得你们都该看一下', font, 60, 1024)
    
    io = BytesIO()
    meme.save(io, 'jpeg')
    io.seek(0)
    return io

async def message_handler(bot: ExtendBot, event: GroupMessageEvent | PrivateMessageEvent):
    # 手动从消息链构建文本，因为 pure_text 可能为空或不可靠
    full_text = ""
    try:
        msg_chain = getattr(event, 'message_chain', getattr(event, 'message', []))
        for seg in msg_chain:
            if isinstance(seg, Text):
                full_text += seg.text
            elif isinstance(seg, dict) and seg.get('type') == 'text':
                full_text += seg.get('data', {}).get('text', '')
            elif hasattr(seg, 'text') and seg.text: # 鸭子类型
                full_text += str(seg.text)
    except Exception:
        pass
    
    full_text = full_text.strip()
    # 如果构建失败，回退到 pure_text
    if not full_text:
         full_text = getattr(event, 'pure_text', '').strip()

    # 检查前缀
    if not full_text.startswith("神"):
        return

    # 移除 "神"
    content = full_text[1:].strip()
    
    qqId = None
    name = None
    
    # 尝试从 message_chain 或 message 获取消息段
    segments = getattr(event, 'message_chain', getattr(event, 'message', []))
    
    # 1. 检查组件中的 At
    for seg in segments:
        # 检查是否为 At 对象
        if isinstance(seg, At):
            qqId = str(seg.qq)
            break
        # 检查是否为表示 At 的字典（回退）
        elif isinstance(seg, dict) and seg.get('type') == 'at':
            qqId = str(seg.get('data', {}).get('qq', ''))
            break
        # 检查是否为具有 'qq' 属性的对象（鸭子类型）
        elif hasattr(seg, 'qq'):
             qqId = str(seg.qq)
             break
        # 检查 target 属性（旧样式）
        elif hasattr(seg, 'target'):
             qqId = str(seg.target)
             break

    # 2. 如果没有找到 At，检查内容是否为数字或为空（自己）

    # 2. 如果没有找到 At，检查内容是否为数字或为空（自己）
    if not qqId:
        # 移除文本中潜在的 @ 前缀（处理 "神 @123456" 文本情况）
        clean_content = content.replace('@', '').strip()
        parts = clean_content.split()
        
        if parts and parts[0].isdigit():
            qqId = parts[0]
        # elif not clean_content:
        #     # 情况： "神"（无参数） -> 自己
        #     qqId = str(event.sender.id)
        #     # 对于自己，尝试直接使用发送者信息
        #     if hasattr(event.sender, 'card') and event.sender.card:
        #         name = event.sender.card
        #     elif hasattr(event.sender, 'nickname') and event.sender.nickname:
        #         name = event.sender.nickname
        
        # 回退：如果错过了 At 段，尝试从原始消息中提取 QQ
        # 某些实现可能会将 At 信息放在 raw_message 或类似位置
        if not qqId:
            import re
            # 查找 [CQ:at,qq=123456] 模式
            cq_at = re.search(r'\[CQ:at,qq=(\d+)\]', event.pure_text) # pure_text 可能包含 CQ 码？
            if cq_at:
                qqId = cq_at.group(1)
            
            # 或者在原始文本中查找简单的 @123456 模式
            at_pattern = re.search(r'@(\d+)', text)
            if at_pattern:
                qqId = at_pattern.group(1)

    if not qqId:
        return

    # 如果未设置或只有 ID，则获取昵称
    if not name:
        group_id = getattr(event, 'group_id', None)
        name = await get_user_nickname(bot, qqId, group_id)

    # 其他参数的默认值
    comment = '牛逼'
    call = '神'
    appel = '他'

    try:
        loop = asyncio.get_running_loop()
        img_io = await loop.run_in_executor(None, generate_meme_image, qqId, name, comment, call, appel)
        if img_io:
            # 保存到文件，因为 Image 组件需要 'file' 字段
            save_dir = Path("data/pictures/god_meme_generator")
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存新文件前清理缓存（保留文件 1 小时）
            clean_cache(save_dir, max_age_seconds=3600)
            
            file_path = save_dir / f"{uuid.uuid4()}.jpg"
            with open(file_path, "wb") as f:
                f.write(img_io.getvalue())
            
            await bot.send(event, [Image(file=str(file_path))])
        else:
            await bot.send(event, [Text("生成失败，无法获取头像。")])
    except Exception as e:
        await bot.send(event, [Text(f"生成出错: {str(e)}")])

def register_handlers(bot: ExtendBot, conf: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        await message_handler(bot, event)

    @bot.on(PrivateMessageEvent)
    async def handle_private_message(event: PrivateMessageEvent):
        await message_handler(bot, event)
