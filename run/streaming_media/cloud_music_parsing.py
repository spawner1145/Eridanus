import json

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import File, Image, Video, Node, Text, At
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.manshuo_draw import manshuo_draw
from framework_common.utils.utils import download_img
from run.streaming_media.service.cloud_music.cloud_music_parsing import CloudMusicParser
import traceback
import re
import pprint

song_level = {'标准':'standard','standard':'标准',
              '极高':'exhigh', 'exhigh':'极高',
              '无损':'lossless', 'lossless':'无损',
              '超清母带':'jyeffect', 'jyeffect':'超清母带'}

async def parse_cloud_music(bot:ExtendBot,event,config,url,level):
    """
    处理代理问题
    """
    if config.streaming_media.config["网易云解析"]["enable_proxy"] and config.common_config.basic_config["proxy"]["http_proxy"]:
        proxies = {"http://":config.common_config.basic_config["proxy"]["http_proxy"],"https://":config.common_config.basic_config["proxy"]["http_proxy"]}
    else:
        proxies = None
    bot.logger.info(f"开始解析网易云音乐链接:{url}")
    recall_id = await bot.send(event, [Text("正在解析网易云音乐链接...")])

    try:
        music = CloudMusicParser(proxies=proxies, base_url=config.streaming_media.config["网易云解析"]["wyy_prase_url"])
        detail_result = await music.getSongDetail(url)
        # print(json.dumps(result, indent=2, ensure_ascii=False))
        #pprint.pprint(detail_result)
        detail_result = detail_result["data"]
        music_name = detail_result["al_name"] + " - " + detail_result["ar_name"]
        music_url = detail_result["url"]
        save_path = f"data/voice/cache/{music_name.replace('/', '_')}"
        if not save_path.endswith(".mp3"):
            save_path += ".mp3"
        if level is None:
            await music.download_music(music_url, save_path)
        else:
            await music.download_music_stream(detail_result["id"], save_path, song_level[level])
        # print(result["song_info"]["cover"])
        await bot.send(event,[File(file=save_path)])
        await download_img(detail_result['pic'], f"data/voice/cache/{music_name.replace('/', '_')}.jpg")
        await bot.send(event, [Image(file=(await manshuo_draw([{'type': 'basic_set', 'img_width': 750},
                                                              {'type': 'img', 'subtype': 'common_with_des_right',
                                                               'img': [f"data/voice/cache/{music_name.replace('/','_')}.jpg"],
                                                               'content': [f"[title]{detail_result['al_name']}\n[/title]"
                                                                           f"歌手：{detail_result['ar_name']}\n"
                                                                           f"歌曲品质：{level}"]}])))])
    except Exception as e:
        bot.logger.error(f"音乐解析失败，请联系管理员:{e}")
        traceback.print_exc()
        await bot.send(event, [Text("发送音乐失败")])
    finally:
        await bot.recall(recall_id['data']['message_id'])
def main(bot,config):
    @bot.on(GroupMessageEvent)
    async def dl_youtube_audio(event):
        context, userid, nickname, group_id = event.pure_text, str(event.sender.user_id), event.sender.nickname, int(event.group_id)
        if event.message_chain.has(At) and event.message_chain.has(Text):  context = event.message_chain.get(Text)[0].text
        order_list = ["网易云解析", "网易云下载", 'wyy下载', '网易云歌曲下载','网易云歌曲解析']
        level_list =  ['标准', '极高', '无损', 'hires', '超清母带']
        if not (any(context.startswith(word) for word in order_list)):return
        level = next((t for t in level_list if t in context), None)
        song = re.compile('|'.join(map(re.escape, order_list + level_list))).sub('', context)
        url_pattern = r'(https?://[^\s]+)'
        song = re.findall(url_pattern, song)[0]
        await parse_cloud_music(bot,event,config,song.lstrip(),level)