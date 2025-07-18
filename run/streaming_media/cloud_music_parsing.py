import json

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import File, Image, Video, Node, Text
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.manshuo_draw import manshuo_draw
from run.streaming_media.service.cloud_music.cloud_music_parsing import CloudMusicParsing


async def parse_cloud_music(bot:ExtendBot,event,config,url):
    bot.logger.info(f"开始解析网易云音乐链接:{url}")
    await bot.send(event, [Text("正在解析网易云音乐链接...")])
    async with CloudMusicParsing() as music:
        # 测试参数
        api_type = "api1"
        region = "exhigh"  # 音质：standard, exhigh, lossless, hires, jyeffect, sky, jymaster
        audio_type = "song"  # 类型：song, playlist, album, artist

        result = await music.parse_music(api_type, url, region, audio_type)
        #print(json.dumps(result, indent=2, ensure_ascii=False))
        result=result["data"]
        music_name=result["song_info"]["name"]+" - "+result["song_info"]["artist"]
        await music.download_music(result["url_info"]["url"],f"data/voice/cache/{music_name}")
        try:
            await bot.send(event,[File(file=f"data/voice/cache/{music_name}")])
            await bot.send(event, [Image(file=(await manshuo_draw([{'type': 'basic_set', 'img_width': 750},
                                                                  {'type': 'img', 'subtype': 'common_with_des_right',
                                                                   'img': [result["song_info"]["cover"]], 'content': [f"歌曲名称：{music_name}\n歌曲链接：{result['url_info']['url']}\n专辑：{result['song_info']['album']}"]}])))])

        except Exception as e:
            bot.logger.error(f"发送音乐失败:{e}")
            await bot.send(event, [Text("发送音乐失败")])
def main(bot,config):
    @bot.on(GroupMessageEvent)
    async def dl_youtube_audio(event):
        if event.pure_text.startswith("/网易云解析"):
            url = event.pure_text.split("/网易云解析")[1]
            await parse_cloud_music(bot,event,config,url)