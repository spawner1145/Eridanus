import asyncio
import json
import ssl

import httpx
import websockets

from developTools.utils.logger import get_logger
from framework_common.utils.random_session_hash import random_session_hash
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.check_hostname = False  # 关闭主机名检查
ssl_context.verify_mode = ssl.CERT_NONE  # 关闭证书验证
logger=get_logger("PrettyDerby_TTS")
async def PrettyDerby_TTS(text, speaker,lang_type="ja",proxy=None):
    logger.info(f"params: speaker={speaker}, text={text}, lang_type={lang_type}")
    url = "wss://akitop-umamusume-bert-vits2.hf.space/queue/join?__theme=system"
    session_hash = random_session_hash(11)

    async with websockets.connect(url,ssl=ssl_context) as ws:
        logger.info(f"连接到 {url}")
        while True:
            await asyncio.sleep(1)
            result = await ws.recv()
            if result:
                result = json.loads(result)
                print(result)

                if result["msg"] == "send_hash":
                    await ws.send(json.dumps({"session_hash": session_hash, "fn_index": 0}))

                elif result["msg"] == "send_data":
                    await ws.send(json.dumps({"data":[text,speaker,0.2,0.6,0.8,1,"JP"],"event_data":None,"fn_index":0,"session_hash":session_hash}))

                elif "output" in result:
                    file_url = f"https://akitop-umamusume-bert-vits2.hf.space/--replicas/68bng/file={result['output']['data'][1]['name']}"
                    async with httpx.AsyncClient() as client:
                        response = await client.get(file_url)
                        with open(f"data/voice/cache/{session_hash}.wav", "wb") as f:
                            f.write(response.content)
                    return f"data/voice/cache/{session_hash}.wav"
async def get_PrettyDerby_speakers():
    return  [
    "agnes_digital_爱丽数码_アグネスデジタル",
    "curren_chan_真机伶_カレンチャン",
    "matikane_fukukitaru_待兼福来_マチカネフクキタル",
    "matikane_tannhauser_待兼诗歌剧_マチカネタンホイサ",
    "mejiro_mcqueen_目白麦昆_メジロマックイーン",
    "natuki",
    "nice_nature_优秀素质_ナイスネイチャ",
    "rice_shower_米浴_ライスシャワー",
    "satono_diamond_里见光钻_サトノダイヤモンド"
]

