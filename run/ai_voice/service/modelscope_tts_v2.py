import asyncio
import json
import time

import httpx

from developTools.utils.logger import get_logger
from framework_common.utils.random_session_hash import random_session_hash
logger=get_logger(__name__)

cookie = "cna=j117HdPDmkoCAXjC3hh/4rjk; ajs_anonymous_id=5aa505b4-8510-47b5-a1e3-6ead158f3375; t=27c49d517b916cf11d961fa3769794dd; uuid_tt_dd=11_99759509594-1710000225471-034528; log_Id_click=16; log_Id_pv=12; log_Id_view=277; xlly_s=1; csrf_session=MTcxMzgzODI5OHxEdi1CQkFFQ180SUFBUkFCRUFBQU12LUNBQUVHYzNSeWFXNW5EQW9BQ0dOemNtWlRZV3gwQm5OMGNtbHVad3dTQUJCNFkwRTFkbXAwV0VVME0wOUliakZwfHNEIp5sKWkjeJWKw1IphSS3e4R_7GyEFoKKuDQuivUs; csrf_token=TkLyvVj3to4G5Mn_chtw3OI8rRA%3D; _samesite_flag_=true; cookie2=11ccab40999fa9943d4003d08b6167a0; _tb_token_=555ee71fdee17; _gid=GA1.2.1037864555.1713838369; h_uid=2215351576043; _xsrf=2|f9186bd2|74ae7c9a48110f4a37f600b090d68deb|1713840596; csg=242c1dff; m_session_id=769d7c25-d715-4e3f-80de-02b9dbfef325; _gat_gtag_UA_156449732_1=1; _ga_R1FN4KJKJH=GS1.1.1713838368.22.1.1713841094.0.0.0; _ga=GA1.1.884310199.1697973032; tfstk=fE4KxBD09OXHPxSuRWsgUB8pSH5GXivUTzyBrU0oKGwtCSJHK7N3ebe0Ce4n-4Y8X8wideDotbQ8C7kBE3queYwEQ6OotW08WzexZUVIaNlgVbmIN7MQBYNmR0rnEvD-y7yAstbcoWPEz26cnZfu0a_qzY_oPpRUGhg5ntbgh_D3W4ZudTQmX5MZwX9IN8ts1AlkAYwSdc9sMjuSF8g56fGrgX9SFbgs5bGWtBHkOYL8Srdy07KF-tW4Wf6rhWQBrfUt9DHbOyLWPBhKvxNIBtEfyXi_a0UyaUn8OoyrGJ9CeYzT1yZbhOxndoh8iuFCRFg38WZjVr6yVWunpVaQDQT762H3ezewpOHb85aq5cbfM5aaKWzTZQ_Ss-D_TygRlsuKRvgt_zXwRYE_VymEzp6-UPF_RuIrsr4vHFpmHbxC61Ky4DGguGhnEBxD7Zhtn1xM43oi_fHc61Ky4DGZ6xfGo3-rjf5..; isg=BKKjOsZlMNqsZy8UH4-lXjE_8ygE86YNIkwdKew665XKv0I51IGvHCUz7_tDrx6l"


class MihoyoTTS:
    async def modelscope_tts_v2(self, text, speaker,proxy=None):

        if proxy:
            proxies = {"http://": proxy, "https://": proxy}
        else:
            proxies = None

        # 随机session hash
        session_hash = random_session_hash(11)
        # 请求studio_token
        async with httpx.AsyncClient(proxies=proxies) as client:
            response = await client.get("https://www.modelscope.cn/api/v1/studios/token",
                                        headers={"cookie": cookie})
            response_data = response.json()
            studio_token = response_data["Data"]["Token"]
        logger.info(f"studio_token: {studio_token}")
        # 第一个请求的URL和参数
        queue_join_url = "https://mugemst-hoyotts.ms.show/gradio_api/queue/join"
        queue_join_params = {
            't': str(int(time.time() * 1000)),
            '__theme': 'dark',
            'studio_token': studio_token,
            'backend_url': '/'
        }
        # 第二个请求的URL和headers
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/json",
            "cookie": f"studio_token={studio_token}",
            "Origin": "https://mugemst-hoyotts.ms.show",
            "priority": "u=1, i",
            "referer": f"https://mugemst-hoyotts.ms.show/?t=1740729127503&__theme=light&studio_token={studio_token}&backend_url=/",
            "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "active",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
            "x-studio-token": studio_token
        }





        payload = {"data":[text,speaker,0.2,0.6,0.8,1],"event_data":None,"fn_index":0,"trigger_id":20,"dataType":["textbox","dropdown","slider","slider","slider","slider"],"session_hash":session_hash}

        # 发起第一个请求
        async with httpx.AsyncClient(headers=headers, proxies=proxies) as client:
            response = await client.post(queue_join_url, params=queue_join_params, json=payload)
            # print(f"POST request status code: {response.status_code}")
            # for header in response.headers:
            #     if header[0].lower() == 'set-cookie':
            #         cookie = SimpleCookie(header[1])
            #         for key, morsel in cookie.items():
            #             cookies[key] = morsel.value
            response_data = response.json()
            event_id = response_data['event_id']
            # print(event_id)

            queue_data_url = f"https://mugemst-hoyotts.ms.show/gradio_api/queue/data?session_hash={session_hash}&studio_token={studio_token}"

            async with client.stream("GET", queue_data_url, headers=headers, timeout=60) as event_stream_response:
                async for line in event_stream_response.aiter_text():
                    event = line.replace("data:", "").strip()
                    event = json.loads(event)
                    print(event)
                    if event:
                        if "output" in event:
                            audio_url=event["output"]["data"][1]["url"]
                            async with httpx.AsyncClient(proxies=proxies,headers=headers) as client:
                                response = await client.get(audio_url)
                                with open(f"data/voice/cache/{session_hash}.wav", "wb") as f:
                                    f.write(response.content)
                            return f"data/voice/cache/{session_hash}.wav"
    async def get_speakers(self):
        speakers = ['托马', '妮露', '帕姆', '达达利亚', '安西', '胡桃', '菲谢尔', '玛乔丽', '托克', '大毫', '伦纳德',
                    '八重神子', '希露瓦', '埃舍尔', '掇星攫辰天君', '塞塔蕾', '杰帕德', '停云', '霄翰', '艾丝妲', '宛烟',
                    '埃尔欣根', '纳比尔', '凯瑟琳', '流浪者', '松浦', '奥列格', '莫娜', '吴船长', '鹿野奈奈', '琳妮特',
                    '云堇', '重云', '金人会长', '康纳', '久利须', '博易', '伊利亚斯', '欧菲妮', '阿洛瓦', '帕斯卡',
                    '「公子」', '阿拉夫', '三月七', '旁白', '安柏', '田铁嘴', '明曦', '坎蒂丝', '长生', '龙二', '多莉',
                    '卡波特', '查尔斯', '爱德琳', '天目十五', '优菈', '阿晃', '女士', '艾尔海森', '迪希雅', '阿守',
                    '斯坦利', '埃勒曼', '银狼', '沙扎曼', '镜流', '迈勒斯', '珊瑚', '钟离', '青雀', '「信使」', '诺艾尔',
                    '开拓者(男)', '笼钓瓶一心', '希儿', '老孟', '丹吉尔', '浣溪', '丹枢', '悦', '百闻', '珐露珊', '上杉',
                    '柯莱', '「博士」', '莫塞伊思', '罗刹', '柊千里', '霍夫曼', '宵宫', '言笑', '知易', '斯科特', '虎克',
                    '卡芙卡', '陆行岩本真蕈·元素生命', '瑶瑶', '玛塞勒', '阿佩普', '那维莱特', '彦卿', '常九爷', '嘉玛',
                    '螺丝咕姆', '辛焱', '阿祇', '史瓦罗', '烟绯', '北斗', '埃洛伊', '萨齐因', '舒伯特', '夏洛蒂',
                    '「大肉丸」', '奥兹', '九条镰治', '深渊法师', '毗伽尔', '西拉杰', '影', '阿巴图伊', '拉赫曼', '空',
                    '慧心', '德沃沙克', '砂糖', '米卡', '埃泽', '回声海螺', '神里绫华', '岩明', '克拉拉', '迪奥娜', '五郎',
                    '景元', '莱依拉', '莎拉', '赛诺', '元太', '「散兵」', '克列门特', '费斯曼', '迪卢克', '佩拉', '刃',
                    '石头', '玲可', '大慈树王', '夜兰', '天叔', '阿尔卡米', '阿圆', '「白老先生」', '戴因斯雷布', '博来',
                    '桑博', '素裳', '艾莉丝', '刻晴', '雷电将军', '温迪', '枫原万叶', '艾文', '玛格丽特', '恶龙',
                    '公输师傅', '留云借风真君', '阿扎尔', '瓦尔特', '开拓者(女)', '佐西摩斯', '纳西妲', '香菱', '林尼',
                    '杜拉夫', '娜维娅', '卢卡', '芙宁娜', '式大将', '莺儿', '白术', '班尼特', '克罗索', '凯亚', '纯水精灵？',
                    '拉齐', '久岐忍', '晴霓', '白露', '艾伯特', '娜塔莎', '丹恒', '申鹤', '昆钧', '荧', '琴', '九条裟罗',
                    '塞琉斯', '伊迪娅', '阿娜耶', '早柚', '鹿野院平藏', '七七', '羽生田千鹤', '提纳里', '阿兰', '阿贝多',
                    '凝光', '可可利亚', '浮游水蕈兽·元素生命', '绿芙蓉', '嘉良', '姬子', '魈', '哲平', '蒂玛乌斯', '迈蒙',
                    '塔杰·拉德卡尼', '半夏', '芭芭拉', '海妮耶', '珊瑚宫心海', '「女士」', '卡维', '罗莎莉亚', '驭空',
                    '爱贝尔', '行秋', 'anzai', '萨赫哈蒂', '绮良良', '可莉', '青镞', '丽莎', '符玄', '荒泷一斗', '菲米尼',
                    '雷泽', '埃德', '迪娜泽黛', '巴达维', '恕筠', '海芭夏', '布洛妮娅', '黑塔', '萍姥姥', '甘雨', '派蒙',
                    '神里绫人', '深渊使徒']
        return speakers