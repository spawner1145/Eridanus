import traceback
import uuid
import aiohttp
import asyncio
import os

from framework_common.framework_util.yamlLoader import YAMLManager

config = YAMLManager.get_instance()
class AsyncGPTSoVITSClient:
    def __init__(
        self,
        base_url=None,
        ref_audio_path=None,
        ref_text=None,
    ):
        """
        :param base_url: api_v2.py 服务端地址 (例如: http://123.45.67.89:9880)
        """
        self.speakers=config.tts_v2.config["gpt_sovits"]["speakers"]

    async def generate_tts(
        self,
        target_text,
        ref_audio_path=None,
        ref_text=None,
        target_lang="zh",
        ref_lang="zh",
        output_save_path=None,
        # 以下为可选推理参数
        top_k=None,
        top_p=None,
        temperature=None,
        text_split_method="cut5",
        batch_size=None,
        speed_factor=None,
        streaming_mode=None,
        seed=None,
        media_type="wav",
    ):
        """
        调用 api_v2.py 的 /tts 接口生成语音
        :param ref_audio_path: 参考音频本地路径（服务端能访问到的绝对路径，或远程服务器上的路径）
        """
        if ref_audio_path is None:
            ref_audio_path = config.tts_v2.config["gpt_sovits"]["ref_audio_path"]
        if ref_text is None:
            ref_text = config.tts_v2.config["gpt_sovits"]["ref_text"]
        if output_save_path is None:
            output_save_path = "data/voice/cache/" + uuid.uuid4().hex + ".wav"

        payload = {
            "text": target_text,
            "text_lang": target_lang,
            "ref_audio_path": ref_audio_path,   # api_v2 直接接受服务端路径，无需上传
            "prompt_text": ref_text,
            "prompt_lang": ref_lang,
            "top_k": top_k or config.tts_v2.config["gpt_sovits"]["top_k"],
            "top_p": top_p or config.tts_v2.config["gpt_sovits"]["top_p"],
            "temperature": temperature or config.tts_v2.config["gpt_sovits"]["temperature"],
            "text_split_method": text_split_method or config.tts_v2.config["gpt_sovits"]["text_split_method"],
            "batch_size": batch_size or config.tts_v2.config["gpt_sovits"]["batch_size"],
            "batch_threshol": 0.75,
            "split_bucket": True,
            "speed_factor": speed_factor or config.tts_v2.config["gpt_sovits"]["speed_factor"],
            "fragment_interval": 0.3,
            "sample_steps": 32,
            "super_sampling": False,
            "streaming_mode": streaming_mode or config.tts_v2.config["gpt_sovits"]["streaming_mode"],
            "seed": seed or config.tts_v2.config["gpt_sovits"]["seed"],
            "media_type": media_type,
            "parallel_infer": True,
            "repetition_penalty": 1.35 or config.tts_v2.config["gpt_sovits"]["repetition_penalty"],
        }
        print(payload)
        print(f"正在请求 TTS: {target_text[:20]}...")
        base_url=config.tts_v2.config["gpt_sovits"]["api_base"]
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/tts", json=payload
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"TTS 请求失败! HTTP {resp.status}: {error}")
                #print(resp.text)

                out_dir = os.path.dirname(output_save_path)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(output_save_path, "wb") as f:
                    f.write(await resp.read())

        print(f"生成完成，已保存至: {output_save_path}")
        return output_save_path

    async def set_gpt_weights(self, weights_path: str):
        base_url=config.tts_v2.config["gpt_sovits"]["api_base"]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/set_gpt_weights",
                params={"weights_path": weights_path},
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise Exception(f"切换 GPT 模型失败: {data}")
                print(f"GPT 模型已切换: {weights_path}")

    async def set_sovits_weights(self, weights_path: str):
        base_url = config.tts_v2.config["gpt_sovits"]["api_base"]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/set_sovits_weights",
                params={"weights_path": weights_path},
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise Exception(f"切换 SoVITS 模型失败: {data}")
                print(f"SoVITS 模型已切换: {weights_path}")




