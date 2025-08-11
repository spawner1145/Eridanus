import json

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import File, Image, Video, Node, Text
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.manshuo_draw import manshuo_draw
from framework_common.utils.utils import download_img
from run.streaming_media.service.cloud_music.cloud_music_parsing import CloudMusicParser


async def parse_cloud_music(bot:ExtendBot,event,config,url):
    """
    处理代理问题
    """
    if config.streaming_media.config["网易云解析"]["enable_proxy"] and config.common_config.basic_config["proxy"]["http_proxy"]:
        proxies={"http://":config.common_config.basic_config["proxy"]["http_proxy"],"https://":config.common_config.basic_config["proxy"]["http_proxy"]}
    else:
        proxies=None
    bot.logger.info(f"开始解析网易云音乐链接:{url}")
    await bot.send(event, [Text("正在解析网易云音乐链接...")])
    music=CloudMusicParser(proxies=proxies)


    detail_result = await music.getSongDetail(url)
    #print(json.dumps(result, indent=2, ensure_ascii=False))
    detail_result=detail_result["data"]
    music_name=detail_result["name"]+" - "+detail_result["singer"]
    music_url_data=await music.getMusicUrl(url)
    music_url=music_url_data[0]["url"]
    save_path=f"data/voice/cache/{music_name.replace('/','_')}"
    if not save_path.endswith(".mp3"):
        save_path += ".mp3"
    await music.download_music(music_url, save_path)
    #print(result["song_info"]["cover"])

    try:
        await bot.send(event,[File(file=save_path)])
        await download_img(detail_result['picimg'], f"data/voice/cache/{music_name.replace('/', '_')}.jpg")
        await bot.send(event, [Image(file=(await manshuo_draw([{'type': 'basic_set', 'img_width': 750},
                                                              {'type': 'img', 'subtype': 'common_with_des_right',
                                                               'img': [f"data/voice/cache/{music_name.replace('/','_')}.jpg"], 'content': [f"歌曲名称：{music_name}\n专辑：{detail_result['album']}"]}])))])

    except Exception as e:
        bot.logger.error(f"发送音乐失败:{e}")
        await bot.send(event, [Text("发送音乐失败")])
def main(bot,config):
    @bot.on(GroupMessageEvent)
    async def dl_youtube_audio(event):
        if event.pure_text.startswith("/网易云解析"):
            url = event.pure_text.split("/网易云解析")[1]
            await parse_cloud_music(bot,event,config,url.lstrip())