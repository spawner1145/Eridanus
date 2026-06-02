import re
import asyncio
import aiohttp
import subprocess
import zipfile
from pathlib import Path

# 引入你框架的相关组件
from developTools.event.events import GroupMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from developTools.message.message_components import Image, Node, Text, File, Card

# ==================================
# 核心配置区域
# ==================================
# 1. 填入你在 @BotFather 申请的 Token


config=YAMLManager.get_instance()
# 2. 如果服务器在国内，请务必填写代理地址；如果在海外，请填 None
PROXY =config.common_config.basic_config["proxy"]["http_proxy"] if config.common_config.basic_config["proxy"].get("http_proxy") else None
TG_BOT_TOKEN=config.resource_collector.config["telegram_stickers"]["bot_token"]

CACHE_DIR = Path("data/pictures/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def tg_api_request(session: aiohttp.ClientSession, method: str, params: dict = None):
    """请求 TG 官方 Bot API"""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}"
    try:
        async with session.get(url, params=params, proxy=PROXY) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
    except Exception as e:
        print(f"TG API 请求异常: {e}")
        return None


def convert_image_sync(input_file: Path, output_file: Path, is_video: bool):
    """使用标准 subprocess.run 同步执行 ffmpeg，捕获真实报错"""
    if is_video:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_file),
            "-vf", "fps=15,scale=512:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            str(output_file)
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_file),
            str(output_file)
        ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg执行失败，错误码 {result.returncode}: {result.stderr.strip()}")


def create_zip_sync(file_paths: list, zip_out_path: Path):
    """将下载好的贴纸打包为ZIP压缩包"""
    with zipfile.ZipFile(zip_out_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            # 仅使用文件名作为压缩包内的路径，去掉前面长长的绝对路径
            arcname = Path(file_path).name
            zipf.write(file_path, arcname)


async def download_and_convert_task(bot: ExtendBot, session: aiohttp.ClientSession, sticker: dict, index: int,
                                    sem: asyncio.Semaphore) -> str:
    """并发下载与转换的单个任务"""
    async with sem:
        file_id = sticker.get("file_id")
        file_unique_id = sticker.get("file_unique_id", f"idx_{index}")

        is_animated = sticker.get("is_animated", False)
        is_video = sticker.get("is_video", False)

        if is_animated:
            bot.logger.warning(f"贴纸 {file_unique_id} 是 TGS(Lottie) 格式，暂时跳过。")
            return None

        # 1. 向官方换取真实下载路径
        file_info = await tg_api_request(session, "getFile", {"file_id": file_id})
        if not file_info or not file_info.get("ok"):
            return None

        file_path = file_info["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{file_path}"

        temp_ext = ".webm" if is_video else ".webp"
        out_ext = ".gif" if is_video else ".png"

        temp_path = CACHE_DIR / f"temp_{file_unique_id}{temp_ext}"
        out_path = CACHE_DIR / f"sticker_{file_unique_id}{out_ext}"

        # 2. 异步下载文件
        try:
            async with session.get(download_url, proxy=PROXY) as resp:
                if resp.status == 200:
                    with open(temp_path, 'wb') as f:
                        f.write(await resp.read())
                else:
                    return None
        except Exception as e:
            bot.logger.error(f"贴纸下载失败: {e}")
            return None

        # 3. 放入线程池进行转换
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, convert_image_sync, temp_path, out_path, is_video)
        except Exception as e:
            bot.logger.error(f"贴纸转换失败 {file_unique_id}: {repr(e)}")
            out_path = None
        finally:
            if temp_path.exists():
                temp_path.unlink()

        if out_path and out_path.exists():
            return str(out_path.absolute())
        return None


# ==================================
# 插件入口
# ==================================
def main(bot: ExtendBot, config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        text = event.pure_text.strip()

        if text.startswith("下载tg贴纸"):
            if TG_BOT_TOKEN == "在此处填入你的_TG_BOT_TOKEN":
                await bot.send(event, "⚠️ 开发者尚未配置 Telegram Bot Token。")
                return

            match = re.search(r"addstickers/([^/]+)", text)
            if not match:
                await bot.send(event,
                               "参数错误！请发送完整的链接，例如：下载tg贴纸 https://t.me/addstickers/moe_sticker_bot")
                return

            pack_name = match.group(1)
            await bot.send(event, f"🕒 正在向 Telegram 官方请求贴纸包 `{pack_name}` 的数据，请稍候...")

            # 1. 获取包数据
            async with aiohttp.ClientSession() as session:
                pack_data = await tg_api_request(session, "getStickerSet", {"name": pack_name})

                if not pack_data or not pack_data.get("ok"):
                    await bot.send(event, "❌ 获取贴纸数据失败，包名不存在或网络不通（国内机器请检查代理）。")
                    return

                stickers = pack_data["result"].get("stickers", [])
                title = pack_data["result"].get("title", pack_name)

                if not stickers:
                    await bot.send(event, f"「{title}」贴纸包为空！")
                    return

                await bot.send(event, f"✅ 读取到「{title}」，共 {len(stickers)} 张，开始下载转换...")

                # 2. 并发下载与转换 (限制5个并发)
                sem = asyncio.Semaphore(5)
                tasks = [
                    download_and_convert_task(bot, session, st, idx, sem)
                    for idx, st in enumerate(stickers)
                ]
                results = await asyncio.gather(*tasks)

            valid_paths = [path for path in results if path is not None]

            if not valid_paths:
                await bot.send(event, "⚠️ 全部贴纸下载或转换失败！")
                return

            bot.logger.info(f"成功转换完成贴纸: {valid_paths}")
            await bot.send(event, f"🎉 处理完成，成功转换 {len(valid_paths)} 张，正在生成压缩包和折叠消息...")

            # =========================================
            # 3. 构造合并转发消息 (折叠聊天记录)
            # =========================================
            cmList = []
            for path in valid_paths:
                cmList.append(Node(content=[Image(file=path)]))

            try:
                # 提示：如果贴纸多于 100 张，部分平台可能会限制单条合并转发的节点数，一般情况可以直接发
                await bot.send(event, cmList)
            except Exception as e:
                bot.logger.error(f"发送折叠消息失败: {e}")
                await bot.send(event, "发送折叠消息失败，可能是单次转发图片数量过多被风控。")

            # =========================================
            # 4. 生成 ZIP 压缩包并作为文件发送
            # =========================================
            zip_path = CACHE_DIR / f"{pack_name}.zip"
            try:
                loop = asyncio.get_running_loop()
                # 放入线程池执行压缩，防止阻塞主线程
                await loop.run_in_executor(None, create_zip_sync, valid_paths, zip_path)

                if zip_path.exists():
                    await bot.send(event, File(file=str(zip_path.absolute())))
            except Exception as e:
                bot.logger.error(f"打包发送压缩文件失败: {e}")
                await bot.send(event, "打包发送压缩文件失败，请检查运行日志。")