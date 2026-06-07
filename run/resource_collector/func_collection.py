import asyncio
import os.path
import re
import traceback
from pathlib import Path

import aiohttp

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Text, Node, File, Image
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.utils.utils import delay_recall
from framework_common.utils.zip import compress_files, sanitize_filename
from framework_common.utils.zip_2_pwd_version import compress_files_with_pwd
from run.resource_collector.service.iwara.iwara1 import search_videos, download_specific_video, fetch_video_info
from run.resource_collector.service.telegram_operator import tg_api_request, download_and_convert_task, create_zip_sync


async def telegram_stickers_download(bot,event,config,url):
    text = url
    CACHE_DIR = Path("data/pictures/cache")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


    match = re.search(r"addstickers/([^/]+)", text)
    if not match:
        await bot.send(event,"参数错误！请发送完整的链接，例如：下载tg贴纸 https://t.me/addstickers/moe_sticker_bot")
        return

    pack_name = match.group(1)
    await bot.send(event, f"🕒 正在向 Telegram 官方请求贴纸包 `{pack_name}` 的数据，请稍候...")

    # 1. 获取包数据
    async with aiohttp.ClientSession() as session:
        pack_data = await tg_api_request(session, "getStickerSet", {"name": pack_name})

        if not pack_data or not pack_data.get("ok"):
            await bot.send(event, "❌ 获取贴纸数据失败，包名不存在或网络不通（国内机器请检查代理）。")
            return

        stickers = pack_data["result"].get("stickers", [])
        title = pack_data["result"].get("title", pack_name)

        if not stickers:
            await bot.send(event, f"「{title}」贴纸包为空！")
            return

        #await bot.send(event, f"✅ 读取到「{title}」，共 {len(stickers)} 张，开始下载转换...")

        # 2. 并发下载与转换 (限制5个并发)
        sem = asyncio.Semaphore(5)
        tasks = [
            download_and_convert_task( session, st, idx, sem)
            for idx, st in enumerate(stickers)
        ]
        results = await asyncio.gather(*tasks)

    valid_paths = [path for path in results if path is not None]

    if not valid_paths:
        await bot.send(event, "⚠️ 全部贴纸下载或转换失败！")
        return

    bot.logger.info(f"成功转换完成贴纸: {valid_paths}")
    await bot.send(event, f"🎉 处理完成，成功转换 {len(valid_paths)} 张，正在生成压缩包和折叠消息...")
    # =========================================
    # 4. 生成 ZIP 压缩包并作为文件发送
    # =========================================
    zip_path = CACHE_DIR / f"{pack_name}.zip"
    try:
        loop = asyncio.get_running_loop()
        # 放入线程池执行压缩，防止阻塞主线程
        await loop.run_in_executor(None, create_zip_sync, valid_paths, zip_path)

        if zip_path.exists():
            await bot.send(event, File(file=str(zip_path.absolute())))
    except Exception as e:
        bot.logger.error(f"打包发送压缩文件失败: {e}")
        await bot.send(event, "打包发送压缩文件失败，请检查运行日志。")
    # =========================================
    # 3. 构造合并转发消息 (折叠聊天记录)
    # =========================================
    '''cmList = []
    for path in valid_paths:
        cmList.append(Node(content=[Image(file=path)]))

    try:
        # 提示：如果贴纸多于 100 张，部分平台可能会限制单条合并转发的节点数，一般情况可以直接发
        await bot.send(event, cmList)
    except Exception as e:
        bot.logger.error(f"发送折叠消息失败: {e}")
        await bot.send(event, "发送折叠消息失败，可能是单次转发图片数量过多被风控。")'''



async def iwara_search(bot:ExtendBot,event:GroupMessageEvent,config,aim:str,operation:str):
    user_info = await get_user(event.user_id)
    if operation=="search":
        user_info = await get_user(event.user_id)
        if not user_info.permission >= config.resource_collector.config["iwara"]["iwara_search_level"]:
            await bot.send(event, "无权限")
            return
        msg=await bot.send(event, Text(f"正在iwara搜索{aim}"))
        await delay_recall(bot, msg)
        count_num=0
        while count_num<4:
            try:
                list = await search_videos(aim, config,config.resource_collector.config["iwara"]["iwara_gray_layer"])
                if len(list) == 0:
                    await bot.send(event, Text(f"未搜索到{aim}相关iwara视频"))
                    return
                node_list = [
                    Node(content=[Text(i.get('title')), Text("\nvideo_id:"), Text(i.get('video_id')), Image(file=i.get('path'))])
                    for i in list
                ]
                bot.logger.info(node_list)
                await bot.send(event, node_list)
                return
            except Exception as e:
                traceback.print_exc()
            finally:
                count_num+=1
        await bot.send(event, Text(f"iwara搜索{aim}失败：{e}"))
    elif operation=="download":
        if not user_info.permission >= config.resource_collector.config["iwara"]["iwara_download_level"]:
            await bot.send(event, "无权限")
            return
        videoid = aim
        msg=await bot.send(event, Text(f"正在下载iwara视频{videoid}"))
        await delay_recall(bot, msg)
        try:
            list = await download_specific_video(videoid, config)
            if config.resource_collector.config["iwara"]["zip_file"]:
                zip_name=f"{list.get('title')}.zip"
                bot.logger.info(f"正在压缩文件至data/video/cache/{zip_name}")
                if os.path.exists(f"data/video/cache/{sanitize_filename(list.get('title'))}.zip"):
                    bot.logger.warning("iwara要下载的文件已经存在")
                    if config.resource_collector.config["iwara"]["zip_password"]:
                        await bot.send(event, Text(f"文件密码：{config.resource_collector.config['iwara']['zip_password']}"))
                elif config.resource_collector.config["iwara"]["zip_password"]:
                    compress_files_with_pwd(list.get('path'), "data/video/cache", zip_name=zip_name, password=config.resource_collector.config["iwara"]["zip_password"])
                    await bot.send(event, Text(f"文件压缩中，密码：{config.resource_collector.config['iwara']['zip_password']}"))
                else:
                    compress_files(list.get('path'),
                   "data/video/cache",
                   zip_name=zip_name)
                file_ziped = f"data/video/cache/{sanitize_filename(list.get('title'))}.zip"
                await bot.send(event,File(file=file_ziped))
                msg = [Node(content=[Text(list.get('title')), Text("\nvideo_id:"), Text(list.get('video_id'))])]
            else:
                await bot.send(event, File(file=list.get('path')))
                msg = [Node(content=[Text(list.get('title')), Text("\nvideo_id:"), Text(list.get('video_id'))])]
            await bot.send(event, msg)
        except Exception as e:
            await bot.send(event, Text(f"iwara视频{videoid}下载失败：{e}"))
async def iwara_tendency(bot:ExtendBot,event:GroupMessageEvent,config,aim_type:str):
    user_info = await get_user(event.user_id)
    if not user_info.permission >= config.resource_collector.config["iwara"]["iwara_search_level"]:
        await bot.send(event, "无权限")
        return
    if aim_type=="hotest":
        await bot.send(event, Text(f"正在获取iwara热门视频"))
        try:
            list = await fetch_video_info('popularity', config)
            if len(list) == 0:
                await bot.send(event, Text(f"未获取到iwara热门视频"))
                return
            node_list = [
                Node(content=[Text(i.get('title')), Text("\nvideo_id:"), Text(i.get('video_id')),
                              Image(file=i.get('path'))])
                for i in list
            ]
            await bot.send(event, node_list)
        except Exception as e:
            await bot.send(event, Text(f"iwara热门获取失败：{e}"))
    if aim_type=="trending":
        await bot.send(event, Text(f"正在获取iwara趋势视频"))
        try:
            list = await fetch_video_info('trending', config)
            if len(list) == 0:
                await bot.send(event, Text(f"未获取到iwara趋势视频"))
                return
            node_list = [
                Node(content=[Text(i.get('title')), Text("\nvideo_id:"), Text(i.get('video_id')),
                              Image(file=i.get('path'))])
                for i in list
            ]
            await bot.send(event, node_list)
        except Exception as e:
            await bot.send(event, Text(f"iwara趋势获取失败：{e}"))
    if aim_type=="latest":
        await bot.send(event, Text(f"正在获取iwara最新视频"))
        try:
            list = await fetch_video_info('date', config)
            if len(list) == 0:
                await bot.send(event, Text(f"未获取到iwara最新视频"))
                return
            node_list = [
                Node(content=[Text(i.get('title')), Text("\nvideo_id:"), Text(i.get('video_id')),
                              Image(file=i.get('path'))])
                for i in list
            ]
            await bot.send(event, node_list)
        except Exception as e:
            await bot.send(event, Text(f"iwara最新获取失败：{e}"))
