
import asyncio


from framework_common.ToolKits import Util
from developTools.message.message_components import Reply, Mface
from developTools.message.message_components import Image as Bot_Image


util=Util.get_instance()
async def delay_recall(bot, msg, interval=20):
    """
    延迟撤回消息的非阻塞封装函数，撤回机器人自身消息可以先msg = await bot.send(event, 'xxx')然后调用await delay_recall(bot, msg, 20)这样来不阻塞的撤回，默认20秒后撤回
    
    参数:
        bot
        msg: 消息
        interval: 延迟时间（秒）
    """
    async def recall_task():
        await asyncio.sleep(interval)
        await bot.recall(msg['data']['message_id'])

    asyncio.create_task(recall_task())

async def get_img(event,bot):
    """
    获取消息中或者引用消息中的图片url，如果没有找到返回False
    """
    if event.message_chain.has(Reply):
            msg = await bot.get_msg(event.message_chain.get(Reply)[0].id)
            bot.logger.info(f"获取到的消息：{msg.message_chain}")
            if msg.message_chain.has(Bot_Image):
                return msg.message_chain.get(Bot_Image)[0].url or msg.message_chain.get(Bot_Image)[0].file
            elif msg.message_chain.has(Mface):
                return msg.message_chain.get(Mface)[0].url or msg.message_chain.get(Mface)[0].file
            else:
                return False
    elif event.message_chain.has(Bot_Image):
        return event.message_chain.get(Bot_Image)[0].url or event.message_chain.get(Bot_Image)[0].file
    elif event.message_chain.has(Mface):
        return event.message_chain.get(Mface)[0].url or event.message_chain.get(Mface)[0].file
    else:
        return False



def parse_arguments(arg_string, original_dict):
    args = arg_string.split()
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith('--') and len(arg) > 2:
            key = arg[2:]
            value_parts = []
            j = i + 1
            while j < len(args) and not args[j].startswith('--'):
                value_parts.append(args[j])
                j += 1
            if value_parts:
                value = ' '.join(value_parts)
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                original_dict[key] = value
                i = j - 1
            else:
                if key in original_dict:
                    del original_dict[key]
        i += 1
    return original_dict
def convert_list_to_type(input_list, target_type_str="int"):
    """
    将列表中的每个元素尝试转换为指定类型, 返回转换后的列表
    input_list: 原始列表，包含各种可转换的元素。
    target_type_str: 目标类型名称，例如 "int", "float", "str" 等。
    """
    type_mapping = {
        'int': int,
        'float': float,
        'str': str,
        'bool': bool,
        'complex': complex,
    }
    convert_func = type_mapping.get(target_type_str.lower())
    if not convert_func:
        raise ValueError(f"不支持的类型: {target_type_str}")
    converted_list = []
    error_occurred = False
    for index, item in enumerate(input_list):
        try:
            converted_item = convert_func(item)
            converted_list.append(converted_item)
        except (ValueError, TypeError):
            print(f"转换失败：元素 '{item}'（位置索引 {index}）无法转换为 {target_type_str}")
            error_occurred = True
    if error_occurred:
        return input_list
    else:
        return converted_list

#以下函数均建议直接使用Util类中的方法，这将更加简便，出于兼容性考虑，原函数暂时保留
async def url_to_base64(url):
    """图片2base64"""
    return await util.image.Image2Base64(url)
async def download_img(url, path=None, gray_layer=False, proxy=None, headers=None):
    """下载图片"""
    return await util.image.download_img(url, path, gray_layer, proxy, headers)
async def download_file(url,path,proxy=None):
    """下载文件"""
    return await util.file.download_file(url,path,proxy)
def get_headers():
    """随机headers"""
    return util.network.random_headers()

def merge_audio_files(audio_files: list, output_file: str) -> str:
    """
    合并音频文件列表并保存为一个文件，支持 MP3、FLAC、WAV 等格式。
    :param audio_files: 音频文件路径列表（支持 wav, mp3, flac 等格式）。
    :param output_file: 输出的合并音频文件路径。
    :return: 输出文件路径。
    """
    return util.file.merge_audio_files(audio_files, output_file)




