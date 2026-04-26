import asyncio
import aiohttp
import random
import string
import json
from typing import Optional


BASE_URL = "https://kit-lemonfoot-hololive-style-bert-vits2.hf.space"

HEADERS = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "origin": BASE_URL,
    "referer": f"{BASE_URL}/?__theme=system",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

SPEAKERS = {
    "MoriCalliope":      {"fn_index": 0,  "model_name": "SBV2_HoloLow",           "model_path": "model_assets/SBV2_HoloLow/SBV2_HoloLow.safetensors",                       "style": "Neutral"},
    "TakanashiKiara":    {"fn_index": 1,  "model_name": "SBV2_TakanashiKiara",    "model_path": "model_assets/SBV2_TakanashiKiara/SBV2_TakanashiKiara.safetensors",         "style": "Neutral"},
    "NinomaeInanis":     {"fn_index": 2,  "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "GawrGura":          {"fn_index": 3,  "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "AmeliaWatson":      {"fn_index": 4,  "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "IRyS":              {"fn_index": 5,  "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "TsukumoSana":       {"fn_index": 6,  "model_name": "SBV2_HoloAus",           "model_path": "model_assets/SBV2_HoloAus/SBV2_HoloAus.safetensors",                       "style": "Neutral"},
    "CeresFauna":        {"fn_index": 7,  "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "OuroKronii":        {"fn_index": 8,  "model_name": "SBV2_HoloLow",           "model_path": "model_assets/SBV2_HoloLow/SBV2_HoloLow.safetensors",                       "style": "Neutral"},
    "NanashiMumei":      {"fn_index": 9,  "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "HakosBaelz":        {"fn_index": 10, "model_name": "SBV2_HoloAus",           "model_path": "model_assets/SBV2_HoloAus/SBV2_HoloAus.safetensors",                       "style": "Neutral"},
    "ShioriNovella":     {"fn_index": 11, "model_name": "SBV2_HoloHi",            "model_path": "model_assets/SBV2_HoloHi/SBV2_HoloHi.safetensors",                         "style": "Neutral"},
    "KosekiBijou":       {"fn_index": 12, "model_name": "SBV2_KosekiBijou",       "model_path": "model_assets/SBV2_KosekiBijou/SBV2_KosekiBijou.safetensors",               "style": "Neutral"},
    "NerissaRavencroft": {"fn_index": 13, "model_name": "SBV2_HoloLow",           "model_path": "model_assets/SBV2_HoloLow/SBV2_HoloLow.safetensors",                       "style": "Neutral"},
    "AyundaRisu":        {"fn_index": 14, "model_name": "SBV2_HoloESL",           "model_path": "model_assets/SBV2_HoloESL/SBV2_HoloESL.safetensors",                       "style": "Neutral"},
    "MoonaHoshinova":    {"fn_index": 15, "model_name": "SBV2_HoloESL",           "model_path": "model_assets/SBV2_HoloESL/SBV2_HoloESL.safetensors",                       "style": "Neutral"},
    "AiraniIofifteen":   {"fn_index": 16, "model_name": "SBV2_HoloESL",           "model_path": "model_assets/SBV2_HoloESL/SBV2_HoloESL.safetensors",                       "style": "Neutral"},
    "KureijiOllie":      {"fn_index": 17, "model_name": "SBV2_HoloIDFlu",         "model_path": "model_assets/SBV2_HoloIDFlu/SBV2_HoloIDFlu.safetensors",                   "style": "Neutral"},
    "AnyaMelfissa":      {"fn_index": 18, "model_name": "SBV2_HoloESL",           "model_path": "model_assets/SBV2_HoloESL/SBV2_HoloESL.safetensors",                       "style": "Neutral"},
    "VestiaZeta":        {"fn_index": 19, "model_name": "SBV2_HoloIDFlu",         "model_path": "model_assets/SBV2_HoloIDFlu/SBV2_HoloIDFlu.safetensors",                   "style": "Neutral"},
    "TokinoSora":        {"fn_index": 20, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "SakuraMiko":        {"fn_index": 21, "model_name": "SBV2_HoloJPBaby",        "model_path": "model_assets/SBV2_HoloJPBaby/SBV2_HoloJPBaby.safetensors",                 "style": "Neutral"},
    "HoshimachiSuisei":  {"fn_index": 22, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "AZKi":              {"fn_index": 23, "model_name": "SBV2_HoloJPTest2.5",     "model_path": "model_assets/SBV2_HoloJPTest2.5/SBV2_HoloJPTest2.5.safetensors",           "style": "Neutral"},
    "YozoraMel":         {"fn_index": 24, "model_name": "SBV2_HoloJPTest2.5",     "model_path": "model_assets/SBV2_HoloJPTest2.5/SBV2_HoloJPTest2.5.safetensors",           "style": "Neutral"},
    "ShirakamiFubuki":   {"fn_index": 25, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "NatsuiroMatsuri":   {"fn_index": 26, "model_name": "SBV2_HoloJPTest2.5",     "model_path": "model_assets/SBV2_HoloJPTest2.5/SBV2_HoloJPTest2.5.safetensors",           "style": "Neutral"},
    "AkiRosenthal":      {"fn_index": 27, "model_name": "SBV2_HoloJPTest2.5",     "model_path": "model_assets/SBV2_HoloJPTest2.5/SBV2_HoloJPTest2.5.safetensors",           "style": "Neutral"},
    "AkaiHaato":         {"fn_index": 28, "model_name": "SBV2_HoloJPTest2.5",     "model_path": "model_assets/SBV2_HoloJPTest2.5/SBV2_HoloJPTest2.5.safetensors",           "style": "Neutral"},
    "MinatoAqua":        {"fn_index": 29, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "NakiriAyame":       {"fn_index": 30, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "OozoraSubaru":      {"fn_index": 31, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "NekomataOkayu":     {"fn_index": 32, "model_name": "SBV2_HoloJPTest",        "model_path": "model_assets/SBV2_HoloJPTest/SBV2_HoloJPTest.safetensors",                 "style": "Neutral"},
    "UsadaPekora":       {"fn_index": 33, "model_name": "SBV2_UsadaPekora",       "model_path": "model_assets/SBV2_UsadaPekora/SBV2_UsadaPekora.safetensors",               "style": "Neutral"},
    "UruhaRushia":       {"fn_index": 34, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "ShiranuiFlare":     {"fn_index": 35, "model_name": "SBV2_HoloJPTest",        "model_path": "model_assets/SBV2_HoloJPTest/SBV2_HoloJPTest.safetensors",                 "style": "Neutral"},
    "ShiroganeNoel":     {"fn_index": 36, "model_name": "SBV2_HoloJPTest",        "model_path": "model_assets/SBV2_HoloJPTest/SBV2_HoloJPTest.safetensors",                 "style": "Neutral"},
    "HoushouMarine":     {"fn_index": 37, "model_name": "SBV2_HoloJPTest",        "model_path": "model_assets/SBV2_HoloJPTest/SBV2_HoloJPTest.safetensors",                 "style": "Neutral"},
    "AmaneKanata":       {"fn_index": 38, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "TsunomakiWatame":   {"fn_index": 39, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "TokoyamiTowa":      {"fn_index": 40, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "HimemoriLuna":      {"fn_index": 41, "model_name": "SBV2_HoloJPBaby",        "model_path": "model_assets/SBV2_HoloJPBaby/SBV2_HoloJPBaby.safetensors",                 "style": "Neutral"},
    "YukihanaLamy":      {"fn_index": 42, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "MomosuzuNene":      {"fn_index": 43, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "OmaruPolka":        {"fn_index": 44, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
    "LaplusDarknesss":   {"fn_index": 45, "model_name": "SBV2_HoloJPTest",        "model_path": "model_assets/SBV2_HoloJPTest/SBV2_HoloJPTest.safetensors",                 "style": "Neutral"},
    "TakaneLui":         {"fn_index": 46, "model_name": "SBV2_HoloJPTest2.5",     "model_path": "model_assets/SBV2_HoloJPTest2.5/SBV2_HoloJPTest2.5.safetensors",           "style": "Neutral"},
    "HakuiKoyori":       {"fn_index": 47, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "SakamataChloe":     {"fn_index": 48, "model_name": "SBV2_HoloJPTest2",       "model_path": "model_assets/SBV2_HoloJPTest2/SBV2_HoloJPTest2.safetensors",               "style": "Neutral"},
    "IchijouRirika":     {"fn_index": 49, "model_name": "SBV2_HoloJPTest",        "model_path": "model_assets/SBV2_HoloJPTest/SBV2_HoloJPTest.safetensors",                 "style": "Neutral"},
    "JuufuuteiRaden":    {"fn_index": 50, "model_name": "SBV2_HoloJPTest3",       "model_path": "model_assets/SBV2_HoloJPTest3/SBV2_HoloJPTest3.safetensors",               "style": "Neutral"},
}


class HoliveTTS:
    _instance: Optional["HoliveTTS"] = None

    def __new__(cls) -> "HoliveTTS":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._session: Optional[aiohttp.ClientSession] = None
        return cls._instance

    # ── session 生命周期 ──────────────────────────────────────────

    async def __aenter__(self) -> "HoliveTTS":
        await self.open()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def open(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── 工具方法 ─────────────────────────────────────────────────

    @staticmethod
    def speakers() -> list[str]:
        return list(SPEAKERS.keys())

    @staticmethod
    def _make_session_hash(length: int = 8) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

    @staticmethod
    def _build_data(speaker: str, text: str, language: str) -> list:
        cfg = SPEAKERS[speaker]
        return [
            cfg["model_name"], cfg["model_path"],
            text, language,
            None,               # reference_audio_path
            0.2,                # sdp_ratio
            0.6,                # noise_scale
            0.8,                # noise_scale_w
            1.0,                # length_scale
            True,               # line_split
            0.5,                # split_interval
            "",                 # assist_text
            0.7,                # assist_text_weight
            False,              # use_assist_text
            cfg["style"],       # style
            3,                  # style_weight
            "",                 # kata_tone_json_str
            False,              # use_tone
            speaker,            # speaker
        ]

    # ── 核心步骤 ─────────────────────────────────────────────────

    async def _submit(self, session_hash: str, speaker: str,
                      text: str, language: str) -> None:
        cfg = SPEAKERS[speaker]
        payload = {
            "data": self._build_data(speaker, text, language),
            "event_data": None,
            "fn_index": cfg["fn_index"],
            "session_hash": session_hash,
        }
        async with self._session.post(
            f"{BASE_URL}/queue/join",
            json=payload,
            headers={**HEADERS, "content-type": "application/json"},
        ) as resp:
            resp.raise_for_status()

    async def _poll(self, session_hash: str) -> str:
        url = f"{BASE_URL}/queue/data?session_hash={session_hash}"
        async with self._session.get(url, headers=HEADERS) as resp:
            resp.raise_for_status()
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[len("data:"):].strip())
                msg = data.get("msg", "")
                if msg == "process_completed":
                    if not data.get("success"):
                        raise RuntimeError(f"推理失败: {data}")
                    file_data = data["output"]["data"][1]
                    return file_data.get("url") or f"{BASE_URL}/file={file_data['path']}"
        raise RuntimeError("SSE 流结束但未收到 process_completed")

    async def _download(self, audio_url: str) -> bytes:
        async with self._session.get(audio_url, headers=HEADERS) as resp:
            resp.raise_for_status()
            return await resp.read()

    # ── 公开接口 ─────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        speaker: str = "MoriCalliope",
        language: str = "JP",
    ) -> bytes:
        """合成语音，返回 WAV 字节数据。"""
        if speaker not in SPEAKERS:
            raise ValueError(f"未知角色: {speaker}，可选: {self.speakers()}")
        if self._session is None or self._session.closed:
            await self.open()

        session_hash = self._make_session_hash()
        await self._submit(session_hash, speaker, text, language)
        audio_url = await self._poll(session_hash)
        return await self._download(audio_url)

    async def synthesize_to_file(
        self,
        text: str,
        save_as: str,
        speaker: str = "MoriCalliope",
        language: str = "JP",
    ) -> None:
        """合成语音并保存到文件。"""
        data = await self.synthesize(text, speaker, language)
        with open(save_as, "wb") as f:
            f.write(data)
        print(f"[done] {speaker} → {save_as} ({len(data):,} bytes)")

    async def synthesize_all(
        self,
        text: str,
        language: str = "JP",
        output_dir: str = ".",
    ) -> dict[str, bool]:
        """并发合成所有角色，返回 {speaker: 是否成功} 字典。"""
        results: dict[str, bool] = {}

        async def _one(speaker: str) -> None:
            try:
                await self.synthesize_to_file(
                    text=text,
                    save_as=f"{output_dir}/audio_{speaker}.wav",
                    speaker=speaker,
                    language=language,
                )
                results[speaker] = True
            except Exception as e:
                print(f"[error] {speaker}: {e}")
                results[speaker] = False

        await asyncio.gather(*[_one(s) for s in SPEAKERS])
        return results


# ── 使用示例 ──────────────────────────────────────────────────────

async def main():
    tts = HoliveTTS()

    # 单角色合成
    async with tts:
        await tts.synthesize_to_file(
            text="こんにちは、世界！",
            speaker="NinomaeInanis",
            language="JP",
            save_as="audio_ina.wav",
        )

    # 全角色并发测试
    async with tts:
        results = await tts.synthesize_all(
            text="こんにちは、世界！",
            language="JP",
            output_dir="output",
        )
        success = sum(v for v in results.values())
        print(f"\n完成: {success}/{len(results)} 成功")


if __name__ == "__main__":
    asyncio.run(main())