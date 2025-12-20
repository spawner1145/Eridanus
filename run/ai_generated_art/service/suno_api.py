import httpx
import asyncio
import json
import time
import random
import string
import uuid
from typing import Optional, Dict, Any
import os

HEADERS: Dict[str, str] = {
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'authorization': 'Bearer 1145141919810',
    'browser-token': '{"token":"1145141919810"}',
    'device-id': '3ec42485-1028-45a1-9750-c6890a4b5245',
    'content-type': 'application/json; charset=utf-8',
    'dnt': '1',
    'origin': 'https://suno.com',
    'priority': 'u=1, i',
    'referer': 'https://suno.com/',
    'sec-ch-ua': '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0',
}

PAYLOAD: Dict[str, Any] = {
    "token": None,
    "generation_type": "TEXT",
    "title": "",
    "tags": "// Genre & Style\nINSTRUMENTAL COMPLEXTRO, HIGH-ENERGY RHYTHM GAME ANTHEM, J-CORE, HARDCORE TECHNO\n\n// Mood & Atmosphere\nAn intense, adrenaline-fueled, euphoric and aggressive track, with a futuristic, cybernetic, and slightly chaotic feel, Designed for fast-paced, precision gameplay, // Technical & Production\nDriving 155 BPM, powerful four-on-the-floor rhythm with syncopated breakbeats, Pristine, professional, and polished production quality, heavy sidechain compression for a pumping feel, wide stereo field, impactful dynamics, powerful sub-bass and crystal-clear highs", # 简化为实际请求中的格式
    "negative_tags": "",
    "mv": "chirp-crow",
    "prompt": "[Intro]\n(Starts with a filtered kick drum and a ticking hi-hat pattern. A digital riser sweep builds tension.)\n[Silence]\n\n[Verse]\n(The full PUNCHY KICK DRUM and CRISP LAYERED SNARES enter, driving the beat. An AGGRESSIVE GROWLING BASSLINE, heavily modulated with LFOs, takes the rhythmic lead. Fast, sharp, metallic HI-HATS create a sense of urgency.)\n\n[Build-up]\n(The beat simplifies to just kicks and hi-hats. FAST ARPEGGIATED SYNTHS start to bubble up. Snare rolls get faster and faster. Add GLITCH SFX and a rising white noise SWEEP.)\n\n[Drop]\n(Maximum impact. The RAZOR-SHARP SAWTOOTH SYNTH LEAD plays an intricate, fragmented melody. Bright SUPER-SAW CHORDS provide powerful harmonic background. STUTTERING VOCAL CHOPS are used as a percussive and melodic hook. The growling bassline becomes even more complex.)\n\n[Verse 2]\n(The sawtooth lead drops out. The growling bass and a new, chopped-up melodic fragment take center stage. The drum pattern becomes more syncopated with added digital percussion fills.)\n\n[Bridge]\n(Atmospheric breakdown. The heavy drums and bass fade out, leaving behind echoing SUPER-SAW PADS and a gentle, melodic synth pluck sequence. A sense of calm before the final storm.)\n\n[Build-up 2]\n(The kick drum re-enters with a heavy sidechain pump. The fast arpeggiated synths return, more intense than before. Add video game sound effects and a powerful riser.)\n\n[Final Drop]\n(Explosive energy. All elements combine. The sawtooth synth lead returns with a higher octave and more aggression. The vocal chops are faster and more glitched. The track is filled with complex drum fills and chaotic glitch sound effects.)\n\n[Outro]\n(Music comes to a hard cut at the climax, followed by the sound of a decaying reverb tail from the final synth chord and a final, single \"glitch\" sound effect.)",
    "make_instrumental": False,
    "user_uploaded_images_b64": None,
    "metadata": {
        "web_client_pathname": "/create",
        "is_max_mode": False,
        "is_mumble": False,
        "create_mode": "custom",
        "user_tier": "3eaebef3-ef46-446a-931c-3d50cd1514f1",
        "create_session_token": "281c0a17-f18c-48f3-a9ae-4f24912f77fe",
        "disable_volume_normalization": False,
        "can_control_sliders": ["weirdness_constraint", "style_weight"]
    },
    "override_fields": [],
    "cover_clip_id": None,
    "cover_start_s": None,
    "cover_end_s": None,
    "persona_id": None,
    "artist_clip_id": None,
    "artist_start_s": None,
    "artist_end_s": None,
    "continue_clip_id": None,
    "continued_aligned_prompt": None,
    "continue_at": None,
    "transaction_uuid": "1145141919810"
}

def generate_browser_token() -> str:
    import base64
    timestamp = int(time.time() * 1000)
    payload = {"timestamp": timestamp}
    payload_json = json.dumps(payload)
    encoded_payload = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
    return json.dumps({"token": encoded_payload})

def get_authorization_token(cookie: str) -> str:
    # 这个网址我也不知道以后会不会改，如果变了的话就手动改一下吧(
    url = "https://auth.suno.com/v1/client?__clerk_api_version=2025-11-10&_clerk_js_version=5.111.0"
    headers = {
        'accept': '*/*',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'cookie': cookie,
        'dnt': '1',
        'origin': 'https://suno.com',
        'priority': 'u=1, i',
        'referer': 'https://suno.com/',
        'sec-ch-ua': '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0',
    }
    
    response = httpx.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    session_id = data['response']['sessions'][0]['id']
    touch_url = f"https://auth.suno.com/v1/client/sessions/{session_id}/touch?__clerk_api_version=2025-11-10&_clerk_js_version=5.111.0"
    touch_data = "__clerk_api_version=2025-11-10&_clerk_js_version=5.111.0"
    httpx.post(touch_url, headers=headers, data=touch_data)
    
    jwt = data['response']['sessions'][0]['last_active_token']['jwt']
    return f"Bearer {jwt}"

def generate_random_filename(length: int = 10) -> str:
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for _ in range(length)) + ".mp3"

async def download_audio(client: httpx.AsyncClient, audio_url: str, clip_id: str, download_dir: str = "data/pictures/cache") -> str:
    try:
        print(f"[{clip_id}] 状态完成, 开始下载音频: {audio_url}")
        async with client.stream("GET", audio_url) as response:
            response.raise_for_status()
            filename = generate_random_filename()
            os.makedirs(download_dir, exist_ok=True)
            filepath = os.path.join(download_dir, filename)
            with open(filepath, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
            print(f"[{clip_id}] 下载完成, 已保存为: {filepath}")
            return filepath
    except httpx.HTTPStatusError as e:
        print(f"[{clip_id}] 下载失败 (HTTP {e.response.status_code}): {audio_url}")
        return None
    except Exception as e:
        print(f"[{clip_id}] 下载时发生未知错误: {e}")
        return None

async def generate_songs(cookie: str, prompt: str = "", tags: str = "", negative_tags: str = "", proxy: Optional[str] = None, make_instrumental: bool = False, generate_url: str = "https://studio-api.prod.suno.com/api/generate/v2-web/", feed_url: str = "https://studio-api.prod.suno.com/api/feed/v2?ids=", max_retries: int = 3, download_dir: str = "data/pictures/cache") -> list[str]:
    authorization = get_authorization_token(cookie)
    #print(f"获取到的authorization: {authorization}")
    
    proxies = {"http://": proxy, "https://": proxy} if proxy else None
    HEADERS['authorization'] = authorization
    PAYLOAD['prompt'] = prompt
    PAYLOAD['tags'] = tags
    PAYLOAD['negative_tags'] = negative_tags
    PAYLOAD['make_instrumental'] = make_instrumental
    
    downloaded_files = []
    
    async with httpx.AsyncClient(proxies=proxies, timeout=60) as client:
        try:
            PAYLOAD['transaction_uuid'] = str(uuid.uuid4())
            PAYLOAD['metadata']['create_session_token'] = str(uuid.uuid4())
            browser_token = generate_browser_token()
            HEADERS['browser-token'] = browser_token
            print(f"已生成新的 UUID. Transaction: {PAYLOAD['transaction_uuid']}, Session Token: {PAYLOAD['metadata']['create_session_token']}")
            print(f"生成的 browser-token: {browser_token}")
            
            print("正在向 Suno API 发起 POST 请求以生成歌曲...")
            response = await client.post(generate_url, headers=HEADERS, json=PAYLOAD)
            if response.status_code == 401:
                if retry_count >= max_retries:
                    raise Exception(f"Authorization expired after {max_retries} retries during generation. Last error: 401 Unauthorized")
                retry_count += 1
                authorization = get_authorization_token(cookie)
                HEADERS['authorization'] = authorization
                print(f"Authorization updated for generation, retrying... (attempt {retry_count})")
                response = await client.post(generate_url, headers=HEADERS, json=PAYLOAD)
            
            response.raise_for_status()
            
            data = response.json()
            
            clip_ids = [clip['id'] for clip in data.get('clips', [])]
            
            if not clip_ids:
                print("错误: 未能在响应中找到任何 clip IDs")
                print("API 响应:", json.dumps(data, indent=2))
                return downloaded_files

            print(f"成功发起请求, 获得 Clip IDs: {clip_ids}")
            
            pending_ids = list(clip_ids)
            retry_count = 0
            retry_count = 0
            while pending_ids:
                print(f"\n等待 10 秒后开始轮询... 剩余待处理 IDs: {len(pending_ids)}")
                await asyncio.sleep(10)
                
                ids_to_check = ",".join(pending_ids)
                feed_check_url = f"{feed_url}{ids_to_check}"
                print(f"正在轮询: {feed_check_url}")
                try:
                    feed_response = await client.get(feed_check_url, headers=HEADERS)
                    if feed_response.status_code == 401:
                        if retry_count >= max_retries:
                            raise Exception(f"Authorization expired after {max_retries} retries. Last error: 401 Unauthorized")
                        retry_count += 1
                        authorization = get_authorization_token(cookie)
                        HEADERS['authorization'] = authorization
                        print(f"Authorization updated, retrying... (attempt {retry_count})")
                        continue
                    feed_response.raise_for_status()
                    feed_data = feed_response.json()
                    completed_clips_this_round = []
                    for clip in feed_data.get('clips', []):
                        clip_id = clip.get('id')
                        status = clip.get('status')
                        print(f"- Clip ID: {clip_id}, 状态: {status}")
                        if status == 'error':
                            raise Exception(f"Clip {clip_id} 生成失败，状态: error")
                        elif status == 'complete':
                            audio_url = clip.get('audio_url')
                            if audio_url:
                                filename = await download_audio(client, audio_url, clip_id, download_dir)
                                if filename:
                                    downloaded_files.append(filename)
                                completed_clips_this_round.append(clip_id)
                            else:
                                print(f"警告: Clip {clip_id} 状态为 complete 但没有 audio_url")
                    for clip_id in completed_clips_this_round:
                        if clip_id in pending_ids:
                            pending_ids.remove(clip_id)
                    retry_count = 0

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        if retry_count >= max_retries:
                            raise Exception(f"Authorization expired after {max_retries} retries. Last error: {e}")
                        retry_count += 1
                        authorization = get_authorization_token(cookie)
                        HEADERS['authorization'] = authorization
                        print(f"Authorization updated due to error, retrying... (attempt {retry_count})")
                        continue
                    else:
                        print(f"轮询失败 (HTTP {e.response.status_code})将在10秒后重试")
                except Exception as e:
                    print(f"轮询时发生错误: {e}将在10秒后重试")
            
            print("\n所有歌曲均已处理完毕")
            return downloaded_files

        except httpx.HTTPStatusError as e:
            print(f"请求失败: HTTP {e.response.status_code}")
            print("响应内容:", e.response.text)
            return downloaded_files
        except Exception as e:
            print(f"发生未知错误: {e}")
            return downloaded_files

async def main():
    # complextro是世界上最好的曲风！不接受反驳
    # 去suno那个生成页面(https://suno.com/create)点f12然后刷新，找到https://auth.suno.com/v1/client?__clerk_api_version=2025-11-10&_clerk_js_version=5.111.0这个js请求，把请求体里面的Cookie复制到下面
    cookie = '114514'
    # 生成歌曲的描述性提示文本，包含结构和元素描述，这里面是写歌词之类的，不过乐器之类的也能写
    prompt = "[Intro]\n(Starts with a filtered kick drum and a ticking hi-hat pattern. A digital riser sweep builds tension.)\n[Silence]\n\n[Verse]\n(The full PUNCHY KICK DRUM and CRISP LAYERED SNARES enter, driving the beat. An AGGRESSIVE GROWLING BASSLINE, heavily modulated with LFOs, takes the rhythmic lead. Fast, sharp, metallic HI-HATS create a sense of urgency.)\n\n[Build-up]\n(The beat simplifies to just kicks and hi-hats. FAST ARPEGGIATED SYNTHS start to bubble up. Snare rolls get faster and faster. Add GLITCH SFX and a rising white noise SWEEP.)\n\n[Drop]\n(Maximum impact. The RAZOR-SHARP SAWTOOTH SYNTH LEAD plays an intricate, fragmented melody. Bright SUPER-SAW CHORDS provide powerful harmonic background. STUTTERING VOCAL CHOPS are used as a percussive and melodic hook. The growling bassline becomes even more complex.)\n\n[Verse 2]\n(The sawtooth lead drops out. The growling bass and a new, chopped-up melodic fragment take center stage. The drum pattern becomes more syncopated with added digital percussion fills.)\n\n[Bridge]\n(Atmospheric breakdown. The heavy drums and bass fade out, leaving behind echoing SUPER-SAW PADS and a gentle, melodic synth pluck sequence. A sense of calm before the final storm.)\n\n[Build-up 2]\n(The kick drum re-enters with a heavy sidechain pump. The fast arpeggiated synths return, more intense than before. Add video game sound effects and a powerful riser.)\n\n[Final Drop]\n(Explosive energy. All elements combine. The sawtooth synth lead returns with a higher octave and more aggression. The vocal chops are faster and more glitched. The track is filled with complex drum fills and chaotic glitch sound effects.)\n\n[Outro]\n(Music comes to a hard cut at the climax, followed by the sound of a decaying reverb tail from the final synth chord and a final, single \"glitch\" sound effect.)"
    # 正面标签，用于指定歌曲风格、类型、情绪和技术参数
    tags = "// Genre & Style\nINSTRUMENTAL COMPLEXTRO, HIGH-ENERGY RHYTHM GAME ANTHEM, J-CORE, HARDCORE TECHNO\n\n// Mood & Atmosphere\nAn intense, adrenaline-fueled, euphoric and aggressive track, with a futuristic, cybernetic, and slightly chaotic feel, Designed for fast-paced, precision gameplay, // Technical & Production\nDriving 155 BPM, powerful four-on-the-floor rhythm with syncopated breakbeats, Pristine, professional, and polished production quality, heavy sidechain compression for a pumping feel, wide stereo field, impactful dynamics, powerful sub-bass and crystal-clear highs"
    # 负面标签，用于排除某些元素
    negative_tags = ""
    # 梯子的代理
    proxy = "http://127.0.0.1:7890"
    # 是否生成纯音乐版本，默认False（有歌词）,但是complextro没有歌词才是最冰的(
    make_instrumental = True
    # 生成歌曲的API URL
    generate_url = "https://studio-api.prod.suno.com/api/generate/v2-web/"
    # 轮询状态的API URL
    feed_url = "https://studio-api.prod.suno.com/api/feed/v2?ids="
    # 下载目录，默认当前目录
    download_dir = "."
    
    files = await generate_songs(cookie, prompt, tags, negative_tags, proxy, make_instrumental, generate_url, feed_url, download_dir=download_dir)
    print(f"下载的文件: {files}")

if __name__ == "__main__":
    asyncio.run(main())
