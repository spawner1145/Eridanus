import httpx
from pytubefix import YouTube
from ruamel.yaml import YAML
import asyncio
from framework_common.utils.utils import get_headers
import re
from framework_common.framework_util.yamlLoader import YAMLManager

yamlmanager = YAMLManager.get_instance()
try:
    proxy = yamlmanager.common_config.basic_config.get("proxy").get("http_proxy")
except:
    proxy = None

if not proxy:
    proxy = None

proxies = {
    "http://": proxy,
    "https://": proxy
}
pyproxies = {  # pytubefix代理
    "http": proxy,
    "https": proxy
}
def audio_download(video_id):

    url = f"https://www.youtube.com/watch?v={video_id}"
    #
    yt = YouTube(url=url, client='IOS', proxies=pyproxies, use_oauth=True, allow_oauth_cache=True)

    ys = yt.streams.get_audio_only()
    ys.download(output_path="data/voice/cache/", filename=f"{video_id}.mp3")
    return f"data/voice/cache/{video_id}.mp3"
def video_download(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    #
    yt = YouTube(url=url, client='IOS', proxies=pyproxies, use_oauth=True, allow_oauth_cache=True)

    ys = yt.streams.get_highest_resolution()
    ys.download(output_path="data/video/cache/",filename=f"{video_id}.mp4")
    return f"data/video/cache/{video_id}.mp4"
async def get_img(video_id):
    path = f"data/pictures/cache/{video_id}.jpg"
    url = f"https://i.ytimg.com/vi/{video_id}/hq720.jpg"  # 下载视频封面
    async with httpx.AsyncClient(headers=get_headers(), proxies=proxies, timeout=100) as client:
        response = await client.get(url)
    with open(path, 'wb') as f:
        f.write(response.content)
    return path
async def get_info(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    yt = YouTube(url, client='IOS', proxies=pyproxies, use_oauth=True, allow_oauth_cache=True)
    print(f"标题: {yt.title}")
    print(f"作者: {yt.author}")
    print(f"时长(秒): {yt.length}")
    print(f"观看次数: {yt.views}")
    print(f"描述: {yt.description[:200]}...")  # 打印描述前200字符
    print("可用视频流列表:")
    for stream in yt.streams.filter(progressive=True).order_by('resolution').desc():
        print(f" - {stream.itag}: {stream.mime_type}, {stream.resolution}, {stream.fps}fps")



if __name__ == '__main__':
    url = 'https://youtu.be/Fs0CIFsbee4?si=rnP7rTTVoBbv_-y1'
    regex = r"(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([a-zA-Z0-9_-]{11})"
    match1 = re.search(regex, url)
    video_id = match1.group(1)
    print(video_id)
    asyncio.run(get_info(video_id))