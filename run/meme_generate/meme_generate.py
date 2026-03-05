import requests
import os
import re
import json
import asyncio
import shutil
from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Reply,Video,Text,File,Node,At
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import delay_recall
from run.meme_generate.service.meme import get_more_img_func,get_func

mapping_path = "./run/meme_generate/config/mapping.json"
meme_list_path = "./run/meme_generate/config/meme_keys.jpg"

mapping = {}
keys = ()

result_dir = ""
target_dir = ""
has_inited = False


def main(bot: ExtendBot,config: YAMLManager):

    async def init():
        ''''插件初始化函数，负责加载配置和启动定时清理任务'''
        global has_inited,result_dir,target_dir,mapping,keys
        if has_inited:
           return
        has_inited = True
        result_dir = config.meme_generate.config["pic_path"] + "result/"
        target_dir = config.meme_generate.config["pic_path"] + "target/"
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        if not os.path.exists(mapping_path):
            import run.meme_generate.config.init_mapping as init_mapping
            init_mapping.write_default_mapping()
        mapping = read_json_mapping(mapping_path)
        keys = set(mapping.keys())
        # print(mapping)
        # print(keys)
        # Define cleanup task

        async def cleanup_task():
            '''定期清理result_dir和target_dir中的缓存文件'''
            while True:
                await asyncio.sleep(30 * 60)  # 30 minutes
                try:
                    if os.path.exists(result_dir):
                        shutil.rmtree(result_dir)
                        os.makedirs(result_dir)
                    if os.path.exists(target_dir):
                        shutil.rmtree(target_dir)
                        os.makedirs(target_dir)
                    bot.logger.info("[meme_generate] 定期清理缓存文件完成")
                except Exception as e:
                    bot.logger.error(f"[meme_generate] 清理缓存文件失败: {e}")
        asyncio.create_task(cleanup_task())

        bot.logger.info("[meme_generate] 插件初始化完成")
 
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        await init()

        if event.group_id == 450977050:
            return

        if event.pure_text == "meme列表":
            if not os.path.exists("./run/meme_generate/config/meme_keys.jpg"):
                import run.meme_generate.config.draw_pic as draw_pic
                draw_pic.generate_meme_key_image("./run/meme_generate/config/mapping.json")
            nums = keys.__len__()
            await bot.send(event, Text(f"表情包命令列表：共计{nums}个表情包命令喵~"))
            await bot.send(event, Image(file=meme_list_path))
            return

        if(event.message_chain.has(Text) and
            event.message_chain.get(Text)[0].text.strip() in keys):

            text = event.message_chain.get(Text)[0].text.strip()
            bot.logger.info(f"[meme_generate] 检测到{text}指令，开始处理")

            function = mapping[text]["function"]
            min_img_num = mapping[text]["min_img_num"]
            max_img_num = mapping[text]["max_img_num"]
            string_num = mapping[text]["string_num"]
            result_type = mapping[text]["type"]
            global options,details
            options = ""
            details = ""
            if "options" in mapping[text]:
                options = mapping[text]["options"]
                details = mapping[text]["details"]
            #print(function,min_img_num,max_img_num,string_num)

            if(min_img_num == 1 and max_img_num == 1 and string_num ==0):
                if(event.message_chain.has(Image)):
                    traget_img = event.message_chain.get(Image)[0].url

                elif(event.message_chain.has(Reply)):
                    reply_msg_id = event.message_chain.get(Reply)[0].id
                    msg = await bot.get_msg(reply_msg_id)
                    if msg.message_chain.has(Image):
                        traget_img = msg.message_chain.get(Image)[0].url

                elif(event.message_chain.has(At)):
                    qq_num = event.message_chain.get(At)[0].qq
                    traget_img = f"https://q1.qlogo.cn/g?b=qq&nk={qq_num}&s=640"

                traget_id = len(os.listdir(target_dir))+1
                traget_path = f"{target_dir}target_{traget_id}.jpg"

                download_image(traget_img, traget_path, bot)

                result_id = len(os.listdir(result_dir))+1
                result_path = await get_more_img_func(function,[traget_path],result_id,result_type,options,details)
                await bot.send(event,Image(file=result_path))
            elif(min_img_num > 1 and max_img_num > 1):

                traget_img_list = []
                qq_self = event.user_id
                traget_img_1 = f"https://q1.qlogo.cn/g?b=qq&nk={qq_self}&s=640"
                traget_id = len(os.listdir(target_dir))+1
                traget_path_1 = f"{target_dir}target_{traget_id}.jpg"
                download_image(traget_img_1, traget_path_1, bot)
                traget_img_list.append(traget_path_1) #默认第一张图片为本人头像

                if(event.message_chain.has(Image)):
                    traget_img = event.message_chain.get(Image)[0].url

                elif(event.message_chain.has(Reply)):
                    reply_msg_id = event.message_chain.get(Reply)[0].id
                    msg = await bot.get_msg(reply_msg_id)
                    if msg.message_chain.has(Image):
                        traget_img = msg.message_chain.get(Image)[0].url

                elif(event.message_chain.has(At)):
                    qq_num = event.message_chain.get(At)[0].qq
                    traget_img = f"https://q1.qlogo.cn/g?b=qq&nk={qq_num}&s=640"

                traget_id = len(os.listdir(target_dir))+1
                traget_path = f"{target_dir}target_{traget_id}.jpg"

                download_image(traget_img, traget_path, bot)

                traget_img_list.append(traget_path)

                result_id = len(os.listdir(result_dir))+1
                result_path = await get_more_img_func(function,traget_img_list,result_id,result_type,options,details)
                await bot.send(event,Image(file=result_path))
            return
        if(event.message_chain.has(Text)):
            text = find_first_prefix_match(event.message_chain.get(Text)[0].text.strip(),keys)
            if text is not None:
                func_strings = []
                func_strings.append(event.message_chain.get(Text)[0].text.strip().replace(text,"").strip())
                bot.logger.info(f"[meme_generate] 检测到{text}指令，开始处理")
                print(func_strings)

                function = mapping[text]["function"]
                min_img_num = mapping[text]["min_img_num"]
                max_img_num = mapping[text]["max_img_num"]
                string_num = mapping[text]["string_num"]
                result_type = mapping[text]["type"]

                result_id = len(os.listdir(result_dir))+1
                result_path = await get_func(function,[],func_strings,result_id,result_type)
                msg = await bot.send(event,Image(file=result_path))
                #await delay_recall(bot, msg, event, 300)


def download_image(url, save_path ,bot: ExtendBot):
    try:
        # 发送 GET 请求获取图片数据
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
    
    except Exception as e:
        bot.logger.error(f"[meme_generate]图片下载失败：{e}")
def find_first_prefix_match(target: str, str_list: list) -> str | None:
    """
    找到第一个str在str_list中的前缀并返回
    target: 目标字符串
    str_list: 前缀列表
    :return: 第一个匹配的前缀,无匹配返回None
    """
    for pre in str_list:
        if target.startswith(pre):
            return pre  # 找到第一个匹配项立即返回
    return None  # 无匹配
def read_json_mapping(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        # 直接解析为字典
        return json.load(f)