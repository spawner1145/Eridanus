import asyncio
import gc
import shutil
import os
import json as json_handle
from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Image, File, Video, Node, Text, Image, Music
from run.streaming_media.service.Link_parsing.core.login_core import ini_login_Link_Prising
from run.streaming_media.service.Link_parsing.Link_parsing import download_video_link_prising
from run.streaming_media.service.Link_parsing.music_link_parsing import netease_music_link_parse
from run.streaming_media.service.Link_parsing import *

from collections import defaultdict
from time import time
teamlist = defaultdict(lambda: {'data': None, 'expire_at': 0})


async def call_bili_download_video(bot, event, config,type_download='video'):
    if event.group_id in teamlist:
        json_linking = teamlist[event.group_id]['data']
        teamlist.pop(event.group_id)
        if f'{event.group_id}_recall' in teamlist:
            await bot.recall(teamlist[f'{event.group_id}_recall']['data']['message_id'])
            teamlist.pop(f'{event.group_id}_recall')
    else:
        return {"status": "当前群聊没有已缓存的解析结果。"}
    if json_linking['soft_type'] not in {'bilibili', 'dy', 'wb', 'xhs', 'x'}:
        await bot.send(event, '该类型视频图片暂未提供下载支持，敬请期待')
        return
    proxy = config.common_config.basic_config["proxy"]["http_proxy"]
    if type_download == 'video' and json_linking['video_url']:
        try:
            video_json = await download_video_link_prising(json_linking, filepath='data/pictures/cache/', proxy=proxy)
            if 'video' in video_json['type']:
                if video_json['type'] == 'video_bigger':recall_id =await bot.send(event, f'视频有些大，请耐心等待喵~~')
                await bot.send(event, Video(file=video_json['video_path']))
                if video_json['type'] == 'video_bigger':await bot.recall(recall_id['data']['message_id'])
            elif video_json['type'] == 'file':
                recall_id =await bot.send(event, f'好大的视频，小的将发送至群文件喵~')
                await bot.send(event, File(file=video_json['video_path']))
                await bot.recall(recall_id['data']['message_id'])
            elif video_json['type'] == 'too_big':
                await bot.send(event, f'太大了，罢工！')
        except Exception as e:
            await bot.send(event, f'下载失败\n{e}')
    elif type_download == 'img' and json_linking['pic_url_list'] != []:
        node_list = [Node(
            content=[Text("小的找的图片如下，请君过目喵")])]
        for pic_url in json_linking['pic_url_list']:
            node_list.append(Node(content=[Image(file=await download_img(pic_url,'data/pictures/cache/', proxy=proxy))]))
        await bot.send(event, node_list)


def main(bot, config):
    botname = config.common_config.basic_config["bot"]
    bili_login_check, douyin_login_check, xhs_login_check = ini_login_Link_Prising(type=0)
    if bili_login_check and douyin_login_check and xhs_login_check:
        bot.logger.info('✅ 链接解析功能已上线！')
    else:
        if not bili_login_check:
            #bot.logger.warning('⚠️ B站session未能成功获取')
            pass
        else:
            bot.logger.warning('✅ B站session成功获取')
        if not douyin_login_check:
            bot.logger.warning('⚠️ 未能获取到设置抖音的ck')
        else:
            bot.logger.info('✅ 抖音的ck成功获取！')
        if not xhs_login_check:
            bot.logger.warning('⚠️ 未能获取到设置小红书的ck')
        else:
            bot.logger.info('✅ 小红书的ck成功获取！')

    node_path = shutil.which("node")  # 自动查找 Node.js 可执行文件路径
    if not node_path:
        bot.logger.warning("⚠️ Node.js 未安装或未正确添加到系统 PATH 中!")
    try:
        import execjs
        if "Node.js" in execjs.get().name:
            bot.logger.info('✅ 系统已正确读取到node.js')
    except:
        pass
    global Cachecleaner
    Cachecleaner=False

    @bot.on(GroupMessageEvent)
    async def Link_Prising_search(event: GroupMessageEvent):
        proxy = config.common_config.basic_config["proxy"]["http_proxy"]
        url = event.pure_text
        #print(url)
        if url == '' and 'json' in event.processed_message[0]:
            try:
                url = event.processed_message[0]['json']['data']
                event_context = json_handle.loads(event.message_chain[0].data)
                if 'meta' in event_context:
                    url = "QQ小程序" + event_context['meta']['detail_1']['qqdocurl']
            except:
                pass
        if 'http' not in url: url = event.raw_message
        #print(url)
        if event.group_id in teamlist:
            json = teamlist[event.group_id]['data']
            if event.get("text") is not None and event.get("text")[0] == "下载视频":
                if json['soft_type'] not in {'bilibili', 'dy', 'wb', 'xhs', 'x'}:
                    await bot.send(event, '该类型视频暂未提供下载支持，敬请期待')
                    teamlist.pop(event.group_id)
                else:
                    bot.logger.info('视频下载ing')
                    await call_bili_download_video(bot, event, config)
            elif event.get("text") is not None and event.get("text")[0] == "下载图片":
                bot.logger.info('图片下载ing')
                await call_bili_download_video(bot, event, config,'img')

        link_prising_json = await link_prising(url, filepath='data/pictures/cache/', proxy=proxy)
        send_context = f'{botname}识别结果：'
        #print(link_prising_json)
        if link_prising_json['status']:
            bot.logger.info('链接解析成功，开始推送~~')
            if link_prising_json['video_url']:
                teamlist[event.group_id] = {'data': link_prising_json, 'expire_at': time() + 300}
                if event.pure_text.startswith('下载视频'):
                    bot.logger.info('视频下载ing')
                    await call_bili_download_video(bot, event, config)
                    return
                else:
                    send_context = f'该视频可下载，发送“下载视频”以推送喵'
                    if "QQ小程序" in url and config.streaming_media.config["bili_dynamic"]["is_QQ_chek"] is not True:
                        teamlist[f'{event.group_id}_recall'] = await bot.send(event, [f'{send_context}'])
                        return
            elif link_prising_json['pic_url_list'] != []:
                send_context = f'{botname}发现了图片哟，发送‘下载图片’来推送喵'
                teamlist[event.group_id] = {'data': link_prising_json, 'expire_at': time() + 300}
            teamlist[f'{event.group_id}_recall'] = await bot.send(event, [f'{send_context}\n', Image(file=link_prising_json['pic_path'])])
        else:
            if link_prising_json['reason']:
                #print(link_prising_json)
                bot.logger.error(str('bili_link_error ') + link_prising_json['reason'])
    @bot.on(LifecycleMetaEvent)
    async def cleanup_teamlist(event: LifecycleMetaEvent):
        global Cachecleaner
        if Cachecleaner:
            return
        while True:
            bot.logger.info('清理链接解析过期缓存')
            Cachecleaner=True
            current_time = time()
            expired_keys = []
            for k, v in teamlist.items():
                if isinstance(k,str) and k.endswith('_recall'):
                    continue
                if isinstance(v, dict) and 'expire_at' in v:
                    if v['expire_at'] < current_time:
                        expired_keys.append(k)
                else:
                    expired_keys.append(k)
                    bot.logger.warning(f"teamlist[{k}] 格式错误，强制清理: {type(v)}")

            for key in expired_keys:
                # 同时清理对应的 _recall 键（如果存在）
                recall_key = f'{key}_recall'
                teamlist.pop(key, None)
                teamlist.pop(recall_key, None)
                bot.logger.debug(f"清理 teamlist 键: {key} 和 {recall_key}")

            bot.logger.debug(f"teamlist 当前键数: {len(teamlist)}")
            collected = gc.collect()
            bot.logger.info_func(f"回收了 {collected} 个对象")
            await asyncio.sleep(1000)

    @bot.on(GroupMessageEvent)
    async def Music_Link_Prising_search(event: GroupMessageEvent):
        url = event.pure_text
        if config.streaming_media.config["网易云卡片"]["enable"]:
            if "music.163.com" not in url:
                return
            link_parsing_json = await netease_music_link_parse(url, filepath='data/pictures/cache/')
            if link_parsing_json['status']:
                bot.logger.info('网易云音乐链接解析成功，开始推送~~~')
                await bot.send(event, Image(file=link_parsing_json['pic_path']))
                if config.streaming_media.config["网易云卡片"]["解析自带音频下载url"]:
                    try:
                        await bot.send(event, File(file='data/pictures/cache/不允许进行传播、销售等商业活动!!.txt'))
                    except Exception as e:
                        bot.logger.logger(f"{e}\n没有开启解析自带音频下载url，不给你发")
                os.remove('data/pictures/cache/不允许进行传播、销售等商业活动!!.txt')
            return
