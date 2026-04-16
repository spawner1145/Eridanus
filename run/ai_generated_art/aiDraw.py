import asyncio
import base64
import traceback
from io import BytesIO

import httpx
from bs4 import BeautifulSoup

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Image, Node, Text

from run.ai_generated_art.service.modelscope_text2img import modelscope_drawer
from run.ai_generated_art.service.hf_t2i import hf_drawer
from run.ai_generated_art.service.setu_moderate import pic_audit_standalone
from run.basic_plugin.service.ai_text2img import bing_dalle3, flux_ultra, doubao
from framework_common.database_util.User import get_user, User
from framework_common.utils.random_str import random_str
from run.ai_generated_art.service.aiDraw import n4, n3, SdDraw0, getloras, getcheckpoints, ckpt2, n4re0, n3re0, \
    SdmaskDraw, getsampler, getscheduler, interrupt, skipsd, SdOutpaint, get_img_info, aiArtModerate
from run.ai_generated_art.service.wildcard import get_available_wildcards, replace_wildcards
from framework_common.utils.utils import download_img, url_to_base64, parse_arguments, get_img, delay_recall
from run.basic_plugin.service.imgae_search.anime_trace import anime_trace

turn = 0
UserGet = {}
tag_user = {}
style_transfer_user = {}
info_user = {}
sd_user_args = {}
sd_re_args = {}
UserGet1 = {}
n4re = {}
n3re = {}
mask = {}
UserGetm = {}
default_prompt = {}
from framework_common.framework_util.yamlLoader import YAMLManager

config = YAMLManager.get_instance()

aiDrawController = config.ai_generated_art.config.get("ai绘画")
ckpt = aiDrawController.get("sd默认启动模型") if aiDrawController else None
allow_nsfw_groups = [int(item) for item in aiDrawController.get("allow_nsfw_groups", [])] if aiDrawController else []


async def call_text2img(bot, event, config, prompt):
    tag = prompt

    async def run_tasks():
        tasks = [
            asyncio.create_task(func)
            for func in [
                call_text2img1(bot, event, config, tag),
                call_text2img2(bot, event, config, tag),
                nai4(bot, event, config, tag),
                call_text2img3(bot, event, config, tag),
                call_text2img4(bot, event, config, tag),
                # nai3(bot, event, config, tag),
            ]
        ]
        r = None
        for future in asyncio.as_completed(tasks):
            try:
                f1 = await future
                if f1:
                    r = f1
            except Exception as e:
                bot.logger.error(f"Task failed: {e}")
        bot.logger.info(f"text2img 任务完成: {r}")
    # 在后台运行任务，不等待完成
    asyncio.create_task(run_tasks())


async def call_text2img3(bot, event, config, prompt):
    user_info = await get_user(event.user_id)
    if user_info.permission >= config.ai_generated_art.config["ai绘画"]["内置ai绘画2所需权限等级"] and \
            config.ai_generated_art.config["ai绘画"]["内置ai绘画2开关"]:
        bot.logger.info(f"Received text2img prompt: {prompt}")
        img = await modelscope_drawer(prompt, config.common_config.basic_config["proxy"]["http_proxy"],
                                      sd_user_args.get(event.sender.user_id, {}))
        bot.logger.info(f"NoobXL-EPS-v1.1：{img}")
        if img:
            await bot.send(event, [Text(f"NoobXL-EPS-v1.1："), Image(file=img)])


async def call_text2img4(bot, event, config, prompt):
    if config.common_config.basic_config:
        try:
            user: User = await get_user(event.user_id)
            if user.permission >= config.ai_generated_art.config["ai绘画"]["内置ai绘画2所需权限等级"] and \
                    config.ai_generated_art.config["ai绘画"]["内置ai绘画2开关"]:
                bot.logger.info(f"Received text2img prompt: {prompt}")
                img = await hf_drawer(prompt, config.common_config.basic_config["proxy"]["http_proxy"],
                                      sd_user_args.get(event.sender.user_id, {}))
                bot.logger.info(f"ani4：{img}")
                if img:
                    await bot.send(event, [Text(f"ani4："), Image(file=img)])
        except Exception as e:
            print(f"ani4：{e}")


async def call_text2img2(bot, event, config, tag):
    prompt = tag
    user_info = await get_user(event.user_id)

    if user_info.permission >= config.ai_generated_art.config["ai绘画"]["内置ai绘画1所需权限等级"] and \
            config.ai_generated_art.config["ai绘画"]["内置ai绘画1开关"]:
        bot.logger.info(f"Received text2img prompt: {prompt}")
        proxy = config.common_config.basic_config

        functions = [
            bing_dalle3(prompt, proxy),
            flux_ultra(prompt, proxy),
            doubao(prompt, proxy),
            # ideo_gram(prompt, proxy),
            # flux_speed(prompt, proxy), #也不要这个
            # recraft_v3(prompt, proxy), #不要这个
        ]

        tasks = [asyncio.create_task(func) for func in functions]

        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                if result:
                    sendMes = []
                    for r in result:
                        sendMes.append(Node(content=[Image(file=r)]))
                    await bot.send(event, sendMes)
            except Exception as e:
                bot.logger.error(f"Task failed with prompt '{prompt}': {e}")
    else:
        pass
        # await bot.send(event, "你没有权限使用该功能。")


async def call_text2img1(bot, event, config, tag):
    user_info = await get_user(event.user_id)
    if user_info.permission < config.ai_generated_art.config["ai绘画"]["ai绘画所需权限等级"]:
        bot.logger.info(f"reject text2img request: 权限不足")
        msg = await bot.send(event, "无绘图功能使用权限", True)
        await delay_recall(bot, msg)
        return
    if config.ai_generated_art.config["ai绘画"]["sd画图"] and config.ai_generated_art.config["ai绘画"][
        "sdUrl"] != "" and config.ai_generated_art.config["ai绘画"]["sdUrl"] != '':
        global turn
        global sd_user_args
        tag, log = await replace_wildcards(tag)
        if log:
            await bot.send(event, log)
        path = f"data/pictures/cache/{random_str()}.png"
        bot.logger.info(f"调用sd api: path:{path}|prompt:{tag} 当前队列人数：{turn}")
        try:
            if turn != 0:
                if turn > config.ai_generated_art.config["ai绘画"]["sd队列长度限制"] and event.user_id != \
                        config.common_config.basic_config["master"]["id"]:
                    msg = await bot.send(event, "服务端任务队列已满，稍后再试")
                    await delay_recall(bot, msg)
                    return
                msg = await bot.send(event, f'请求已加入绘图队列，当前排队任务数量：{turn}，请耐心等待~', True)
                await delay_recall(bot, msg)
            else:
                msg = await bot.send(event, f"正在绘制，请耐心等待~", True)
                await delay_recall(bot, msg)
            turn += 1
            args = sd_user_args.get(event.sender.user_id, {})
            if hasattr(event, "group_id"):
                id_ = event.group_id
            else:
                id_ = event.user_id
            try:
                p = await SdDraw0(tag, path, config, id_, args)
            except Exception as e:
                bot.logger.error(e)
                bot.logger.error("sd自动重试")
                p = await SdDraw0(tag, path, config, id_, args)
            if not p:
                turn -= 1
                bot.logger.info("色图已屏蔽")
                msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                await delay_recall(bot, msg)
            elif p.startswith("审核api"):
                turn -= 1
                bot.logger.info(p)
                msg = await bot.send(event, p, True)
                await delay_recall(bot, msg)
            else:
                turn -= 1
                await bot.send(event, [Image(file=p)], True)
            return p

        except Exception as e:
            bot.logger.error(e)
            turn -= 1
            bot.logger.error(f"sd api调用失败。{e}")
            msg = await bot.send(event, f"sd api调用失败。{e}")
            await delay_recall(bot, msg)


async def call_aiArtModerate(bot, event, config, img_url):
    try:
        """
        traceanime检测
        """
        try:
            res = await anime_trace(img_url)
            bot.logger.info("traceanime调用成功,结果：{res[2]}")
            res = f"traceanime检测结果：{res[2]}(True为ai作品，False为非ai作品)"
        except Exception as e:
            res = "traceanime调用失败"

        try:
            r = await aiArtModerate(img_url, config.ai_generated_art.config["sightengine"]["api_user"],
                                    config.ai_generated_art.config["sightengine"]["api_secret"])
            r = f"aiArtModerate调用成功，ai生成的可能性为：{r}"
        except Exception as e:
            r = f"aiArtModerate调用失败。{e}"
        if config.ai_llm.config["llm"]["aiReplyCore"]:
            return {"msg": f"api调用结果为，{res}\n{r}"}
        else:
            await bot.send(event, f"图片为ai创作的可能性为{r}%", True)
    except Exception as e:
        bot.logger.error(e)
        msg = await bot.send(event, f"aiArtModerate调用失败。{e}")
        await delay_recall(bot, msg)


async def nai4(bot, event, config, tag):
    if config.ai_generated_art.config["ai绘画"]["novel_ai画图"]:
        tag, log = await replace_wildcards(tag)
        if log:
            await bot.send(event, log, True)
        path = f"data/pictures/cache/{random_str()}.png"
        bot.logger.info(f"发起nai4绘画请求，path:{path}|prompt:{tag}")

        retries_left = 50
        while retries_left > 0:
            try:
                p = await n4(tag, path, event.group_id, config, sd_user_args.get(event.sender.user_id, {}))
                if p is False:
                    bot.logger.info("色图已屏蔽")
                    msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                    await delay_recall(bot, msg)
                elif p.startswith("审核api"):
                    bot.logger.info(p)
                    msg = await bot.send(event, p, True)
                    await delay_recall(bot, msg)
                else:
                    await bot.send(event, [Text("nai4画图结果"), Image(file=p)], True)
                return
            except Exception as e:
                retries_left -= 1
                bot.logger.error(f"nai4报错{e}，剩余尝试次数：{retries_left}")
                if retries_left == 0:
                    bot.logger.info(f"nai4调用失败。{e}")
                    msg = await bot.send(event, f"nai4画图失败{e}", True)
                    await delay_recall(bot, msg)


async def nai3(bot, event, config, tag):
    if config.ai_generated_art.config["ai绘画"]["novel_ai画图"]:
        tag, log = await replace_wildcards(tag)
        if log:
            await bot.send(event, log, True)
        path = f"data/pictures/cache/{random_str()}.png"
        bot.logger.info(f"发起nai3绘画请求，path:{path}|prompt:{tag}")

        retries_left = 50
        while retries_left > 0:
            try:
                p = await n3(tag, path, event.group_id, config, sd_user_args.get(event.sender.user_id, {}))
                if p is False:
                    bot.logger.info("色图已屏蔽")
                    msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                    await delay_recall(bot, msg)
                    break  # 结束循环，因为没有需要重试的情况
                elif p.startswith("审核api"):
                    bot.logger.info(p)
                    msg = await bot.send(event, p, True)
                    await delay_recall(bot, msg)
                else:
                    await bot.send(event, [Text("nai3画图结果"), Image(file=p)], True)
                    break  # 成功获取结果后结束循环
            except Exception as e:
                retries_left -= 1
                bot.logger.error(f"nai3报错{e}，剩余尝试次数：{retries_left}")
                if retries_left == 0:
                    bot.logger.error(f"nai3调用失败。{e}")
                    msg = await bot.send(event, f"nai3画图失败{e}", True)
                    await delay_recall(bot, msg)


def main(bot, config):
    ai_img_recognize = {}

    @bot.on(GroupMessageEvent)
    async def search_image(event:GroupMessageEvent):
        try:
            if str(event.pure_text) == "ai图检测" or (
                    event.get("at") and event.get("at")[0]["qq"] == str(bot.id) and event.get("text")[0] == "ai图检测"):
                msg = await bot.send(event, "请发送要检测的图片")
                await delay_recall(bot, msg)
                ai_img_recognize[event.sender.user_id] = []
            if "ai图检测" in str(event.pure_text) or event.sender.user_id in ai_img_recognize:
                if await get_img(event,bot):
                    img_url = await get_img(event,bot)
                    await call_aiArtModerate(bot, event, config, img_url)
                    ai_img_recognize.pop(event.sender.user_id)
        except Exception as e:
            pass

    @bot.on(GroupMessageEvent)
    async def collection_draw(event):
        if str(event.pure_text).startswith("画 "):
            prompt = str(event.pure_text).replace("画 ", "")
            await call_text2img(bot, event, config, prompt)

    @bot.on(GroupMessageEvent)
    async def naiDraw4(event):
        if str(event.pure_text).startswith("n4 ") and config.ai_generated_art.config["ai绘画"]["novel_ai画图"]:
            tag = str(event.pure_text).replace("n4 ", "")
            msg = await bot.send(event, '正在进行nai4画图', True)
            await delay_recall(bot, msg)
            await nai4(bot, event, config, tag)

    @bot.on(GroupMessageEvent)
    async def naiDraw3(event):
        if str(event.pure_text).startswith("n3 ") and config.ai_generated_art.config["ai绘画"]["novel_ai画图"]:
            tag = str(event.pure_text).replace("n3 ", "")
            msg = await bot.send(event, '正在进行nai3画图', True)
            await delay_recall(bot, msg)
            await nai3(bot, event, config, tag)

    @bot.on(GroupMessageEvent)
    async def db(event):
        if str(event.pure_text).startswith("dan "):
            tag = str(event.pure_text).replace("dan ", "")
            bot.logger.info(f"收到来自群{event.group_id}的请求，prompt:{tag}")
            msg = await bot.send(event, f'正在搜索词条{tag}')
            await delay_recall(bot, msg)
            limit = 5
            if config.common_config.basic_config["proxy"]["http_proxy"]:
                proxies = {"http://": config.common_config.basic_config["proxy"]["http_proxy"],
                           "https://": config.common_config.basic_config["proxy"]["http_proxy"]}
            else:
                proxies = None

            db_base_url = "https://hijiribe.donmai.us"  # 这是反代，原来的是https://danbooru.donmai.us
            # 把danbooru换成sonohara、kagamihara、hijiribe这三个任意一个试试，后面的不用改

            build_msg = [Node(content=[Text(f"{tag}的搜索结果:")])]

            msg = tag
            try:
                async with httpx.AsyncClient(timeout=1000, proxies=proxies) as client:
                    resp = await client.get(
                        f"{db_base_url}/autocomplete?search%5Bquery%5D={msg}&search%5Btype%5D=tag_query&version=1&limit={limit}",
                        follow_redirects=True,
                    )
                    resp.raise_for_status()  # 检查请求是否成功
                    bot.logger.info(f"Autocomplete request successful for tag: {tag}")
            except Exception as e:
                bot.logger.error(f"Failed to get autocomplete data for tag: {tag}. Error: {e}")
                msg = await bot.send(event, f"获取{tag}的搜索结果失败")
                await delay_recall(bot, msg)
                return

            soup = BeautifulSoup(resp.text, 'html.parser')
            tags = soup.find_all('li', class_='ui-menu-item')

            data_values = []
            raw_data_values = []
            for tag in tags:
                data_value = tag['data-autocomplete-value']
                raw_data_values.append(data_value)
                data_value_space = data_value.replace('_', ' ')
                data_values.append(data_value_space)
                bot.logger.info(f"Found autocomplete tag: {data_value_space}")

            for tag in raw_data_values:
                tag1 = tag.replace('_', ' ')
                b1 = Node(content=[Text(f"{tag1}")])
                build_msg.append(b1)
                formatted_tag = tag.replace(' ', '_').replace('(', '%28').replace(')', '%29')

                try:
                    async with httpx.AsyncClient(timeout=1000, proxies=proxies) as client:
                        image_resp = await client.get(
                            f"{db_base_url}/posts?tags={formatted_tag}",
                            follow_redirects=True
                        )
                        image_resp.raise_for_status()  # 检查请求是否成功
                        bot.logger.info(f"Posts request successful for tag: {formatted_tag}")
                except Exception as e:
                    bot.logger.error(f"Failed to get posts for tag: {formatted_tag}. Error: {e}")
                    continue  # 继续处理下一个标签

                soup = BeautifulSoup(image_resp.text, 'html.parser')
                img_urls = [img['src'] for img in soup.find_all('img') if img['src'].startswith('http')][:2]
                bot.logger.info(f"Found {len(img_urls)} images for tag: {formatted_tag}")

                async def download_img1(image_url: str):
                    try:
                        async with httpx.AsyncClient(timeout=1000, proxies=proxies) as client:
                            response = await client.get(image_url)
                            response.raise_for_status()
                            content_type = response.headers.get('content-type', '').lower()
                            if not content_type.startswith('image/'):
                                raise ValueError(f"URL {image_url} does not point to an image.")
                            bytes_image = response.content

                            buffered = BytesIO(bytes_image)
                            base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

                            bot.logger.info(f"Downloaded image from URL: {image_url}")
                            return base64_image, bytes_image

                    except httpx.RequestError as e:
                        bot.logger.error(f"Failed to download image from {image_url}: {e}")
                        raise
                    except Exception as e:
                        bot.logger.error(f"An error occurred while processing the image from {image_url}: {e}")
                        raise

                async def process_image(image_url):
                    image_url = image_url.replace('180x180', '720x720').replace('360x360', '720x720').replace('.jpg',
                                                                                                              '.webp')
                    try:
                        base64_image, bytes_image = await download_img1(image_url)
                        if event.group_id not in allow_nsfw_groups and config.ai_generated_art.config['ai绘画'][
                            "禁止nsfw"]:
                            if config.ai_generated_art.config['ai绘画']['sd审核和反推api']:
                                try:
                                    audit_result = await pic_audit_standalone(base64_image, return_none=True, url=
                                    config.ai_generated_art.config["ai绘画"]["sd审核和反推api"])
                                    if audit_result:
                                        bot.logger.info(
                                            f"Image at URL {image_url} was flagged by audit: {audit_result}")
                                        return [Text(f"太涩了{image_url}")]
                                except Exception as e:
                                    bot.logger.error(f"error to audit image at {image_url}: {e}")
                                    return [Text(f"审核失败{image_url}: {e}")]
                            else:
                                bot.logger.warning(f"审核api未配置，为了安全起见，已屏蔽图片{image_url}")
                                return [Text(f"审核api未配置，为了安全起见，已屏蔽图片{image_url}")]

                        bot.logger.info(f"Image at URL {image_url} passed the audit")
                        path = f"data/pictures/cache/{random_str()}.png"
                        p = await download_img(image_url, path)
                        return [Image(file=p), Text(image_url)]
                    except Exception as e:
                        bot.logger.error(f"Failed to process image at {image_url}: {e}")
                        return None

                async def process_images(img_urls):
                    tasks = [process_image(url) for url in img_urls]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # 过滤掉异常和 None 结果
                    filtered_results = [result for result in results if
                                        not isinstance(result, Exception) and result is not None]

                    # 创建 ForwardMessageNode 列表
                    forward_messages = [
                        Node(
                            content=result
                        )
                        for result in filtered_results
                    ]

                    bot.logger.info(f"Processed {len(filtered_results)} images for tag: {formatted_tag}")
                    return forward_messages

                results = await process_images(img_urls)
                build_msg.extend(results)

            try:
                await bot.send(event, build_msg)
                bot.logger.info("Successfully sent the compiled message to the group.")
            except Exception as e:
                msg = await bot.send(event, f"发送失败{e}")
                await delay_recall(bot, msg)
                bot.logger.error(f"Failed to send the compiled message to the group. Error: {e}")

    @bot.on(GroupMessageEvent)
    async def tagger(event):
        global tag_user

        if str(event.pure_text) == "tag":
            if not await get_img(event,bot):
                if config.ai_generated_art.config['ai绘画']['sd审核和反推api'] == "" or \
                        config.ai_generated_art.config['ai绘画']['sd审核和反推api'] is None:
                    msg = await bot.send(event, "未配置审核和反推api")
                    await delay_recall(bot, msg)
                    return
                tag_user[event.sender.user_id] = []
                msg = await bot.send(event, "请发送要识别的图片")
                await delay_recall(bot, msg)
                return

        # 处理图片和重绘命令
        if str(event.pure_text) == "tag" or event.sender.user_id in tag_user:
            #print(event.processed_message)
            if await get_img(event,bot):
                if config.ai_generated_art.config['ai绘画']['sd审核和反推api'] == "" or \
                        config.ai_generated_art.config['ai绘画']['sd审核和反推api'] is None:
                    msg = await bot.send(event, "未配置审核和反推api")
                    await delay_recall(bot, msg)
                    return
                if str(event.pure_text) == "tag":
                    tag_user[event.sender.user_id] = []

                # 日志记录
                bot.logger.info(f"接收来自群：{event.group_id} 用户：{event.sender.user_id} 的tag反推指令")

                # 获取图片路径
                path = f"data/pictures/cache/{random_str()}.png"
                img_url = await get_img(event,bot)
                bot.logger.info(f"发起反推tag请求，path:{path}")
                tag_user.pop(event.sender.user_id)

                try:
                    b64_in = await url_to_base64(img_url)
                    msg = await bot.send(event, "tag反推中", True)
                    await delay_recall(bot, msg)
                    message, tags, tags_str = await pic_audit_standalone(b64_in, is_return_tags=True,
                                                                         url=config.ai_generated_art.config["ai绘画"][
                                                                             "sd审核和反推api"])
                    tags_str = tags_str.replace("_", " ")
                    await bot.send(event, Text(tags_str), True)
                except Exception as e:
                    bot.logger.error(f"反推失败: {e}")
                    msg = await bot.send(event, f"反推失败: {e}", True)
                    await delay_recall(bot, msg)

    @bot.on(GroupMessageEvent)
    async def sdsettings(event):
        if str(event.pure_text).startswith("setsd "):
            global sd_user_args
            sd_user_args.setdefault(event.sender.user_id, {})
            command = str(event.pure_text).replace("setsd ", "")
            if command == "0":
                sd_user_args[event.sender.user_id] = {}
                await bot.send(event, f"当前绘画参数已重置", True)
                return
            cmd_dict = parse_arguments(command, sd_user_args[event.sender.user_id])  # 不需要 await
            sd_user_args[event.sender.user_id] = cmd_dict
            await bot.send(event, f"当前绘画参数设置: {sd_user_args[event.sender.user_id]}", True)

    @bot.on(GroupMessageEvent)
    async def sdresettings(event):
        if str(event.pure_text).startswith("setre "):
            global sd_re_args
            sd_re_args.setdefault(event.sender.user_id, {})
            command = str(event.pure_text).replace("setre ", "")
            if command == "0":
                sd_re_args[event.sender.user_id] = {}
                await bot.send(event, f"当前重绘参数已重置", True)
                return
            cmd_dict = parse_arguments(command, sd_re_args[event.sender.user_id])  # 不需要 await
            sd_re_args[event.sender.user_id] = cmd_dict
            await bot.send(event, f"当前重绘参数设置: {sd_re_args[event.sender.user_id]}", True)

    @bot.on(GroupMessageEvent)
    async def sdreDrawRun(event):
        global UserGet
        global turn

        if event.pure_text == "重绘" or event.pure_text.startswith("重绘 "):
            user_info = await get_user(event.user_id)
            if not await get_img(event,bot):
                prompt = str(event.pure_text).replace("重绘 ", "").replace("重绘", "").strip()
                if user_info.permission < config.ai_generated_art.config["ai绘画"]["ai绘画所需权限等级"]:
                    bot.logger.info(f"reject text2img request: 权限不足")
                    msg = await bot.send(event, "无绘图功能使用权限", True)
                    try:
                        UserGet.remove(event.sender.user_id)
                    except:
                        pass
                    await delay_recall(bot, msg)
                    return
                UserGet[event.sender.user_id] = [prompt]
                msg = await bot.send(event, "请发送要重绘的图片")
                await delay_recall(bot, msg)
                return

        # 处理图片和重绘命令
        if event.pure_text == "重绘" or event.pure_text.startswith("重绘 ") or event.sender.user_id in UserGet:
            if await get_img(event,bot):
                user_info = await get_user(event.user_id)
                if user_info.permission < config.ai_generated_art.config["ai绘画"]["ai绘画所需权限等级"]:
                    bot.logger.info(f"reject text2img request: 权限不足")
                    msg = await bot.send(event, "无绘图功能使用权限", True)
                    await delay_recall(bot, msg)
                    return
                if str(event.pure_text).startswith("重绘"):
                    prompt = str(event.pure_text).replace("重绘 ", "").replace("重绘", "").strip()
                    UserGet[event.sender.user_id] = [prompt]

                # 日志记录
                prompts = ', '.join(UserGet[event.sender.user_id])
                if prompts:
                    prompts, log = await replace_wildcards(prompts)
                    if log:
                        await bot.send(event, log, True)
                user_info = await get_user(event.user_id)

                bot.logger.info(f"接收来自群：{event.group_id} 用户：{event.sender.user_id} 的重绘指令 prompt: {prompts}")

                # 获取图片路径
                path = f"data/pictures/cache/{random_str()}.png"
                img_url = await get_img(event,bot)
                bot.logger.info(f"发起SDai重绘请求，path:{path}|prompt:{prompts}")
                prompts_str = ' '.join(UserGet[event.sender.user_id]) + ' '
                UserGet.pop(event.sender.user_id)
                if turn > config.ai_generated_art.config["ai绘画"]["sd队列长度限制"] and event.user_id != \
                        config.common_config.basic_config["master"]["id"]:
                    msg = await bot.send(event, "服务端任务队列已满，稍后再试")
                    await delay_recall(bot, msg)
                    return

                try:
                    args = sd_re_args.get(event.sender.user_id, {})
                    b64_in = await url_to_base64(img_url)

                    msg = await bot.send(event, f"开始重绘啦~sd前面排队{turn}人，请耐心等待喵~", True)
                    await delay_recall(bot, msg)
                    turn += 1
                    # 将 UserGet[event.sender.user_id] 列表中的内容和 positive_prompt 合并成一个字符串
                    p = await SdOutpaint(prompts_str, path, config, event.group_id, b64_in, args)
                    if not p:
                        turn -= 1
                        bot.logger.info("色图已屏蔽")
                        msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                        await delay_recall(bot, msg)
                    elif p.startswith("审核api"):
                        turn -= 1
                        bot.logger.info(p)
                        msg = await bot.send(event, p, True)
                        await delay_recall(bot, msg)
                    else:
                        turn -= 1
                        await bot.send(event, [Text("sd重绘结果"), Image(file=p)], True)
                except Exception as e:
                    bot.logger.error(f"重绘失败: {e}")
                    msg = await bot.send(event, f"sd api重绘失败。{e}", True)
                    await delay_recall(bot, msg)

    @bot.on(GroupMessageEvent)
    async def AiSdDraw(event):
        global turn
        global sd_user_args
        if str(event.pure_text) == "lora" and config.ai_generated_art.config["ai绘画"]["sd画图"]:  # 获取lora列表
            bot.logger.info('查询loras中...')
            try:
                p = await getloras(config)
                bot.logger.info(str(p))
                await bot.send(event, p, True)
                # logger.info("success")
            except Exception as e:
                bot.logger.error(e)

        if str(event.pure_text) == "ckpt" and config.ai_generated_art.config["ai绘画"]["sd画图"]:  # 获取lora列表
            bot.logger.info('查询checkpoints中...')
            try:
                p = await getcheckpoints(config)
                bot.logger.info(str(p))
                await bot.send(event, p, True)
                # logger.info("success")
            except Exception as e:
                bot.logger.error(e)

        if str(event.pure_text).startswith("ckpt2 ") and config.ai_generated_art.config["ai绘画"]["sd画图"]:
            tag = str(event.pure_text).replace("ckpt2 ", "")
            bot.logger.info('切换ckpt中')
            if event.user_id == config.common_config.basic_config["master"]["id"]:
                try:
                    await ckpt2(tag, config)
                    msg = await bot.send(event, "切换成功喵~第一次会慢一点~", True)
                    await delay_recall(bot, msg)
                    # logger.info("success")
                except Exception as e:
                    bot.logger.error(e)
                    msg = await bot.send(event, "ckpt切换失败", True)
                    await delay_recall(bot, msg)
            else:
                msg = await bot.send(event, "仅master可执行此操作", True)
                await delay_recall(bot, msg)

        if str(event.pure_text) == "sampler" and config.ai_generated_art.config["ai绘画"]["sd画图"]:
            bot.logger.info('查询sampler中...')
            try:
                p = await getsampler(config)
                bot.logger.info(str(p))
                await bot.send(event, p, True)
                # logger.info("success")
            except Exception as e:
                bot.logger.error(e)

        if str(event.pure_text) == "scheduler" and config.ai_generated_art.config["ai绘画"]["sd画图"]:
            bot.logger.info('查询scheduler中...')
            try:
                p = await getscheduler(config)
                bot.logger.info(str(p))
                await bot.send(event, p, True)
                # logger.info("success")
            except Exception as e:
                bot.logger.error(e)

        if str(event.pure_text) == "interrupt" and config.ai_generated_art.config["ai绘画"][
            "sd画图"] and event.user_id == config.common_config.basic_config["master"]["id"]:
            global turn
            try:
                await interrupt(config)
                msg = await bot.send(event, f"中断任务成功")
                await delay_recall(bot, msg, 20)
            except Exception as e:
                bot.logger.error(e)
                msg = await bot.send(event, f"中断任务失败: {e}")
                await delay_recall(bot, msg, 20)

        if str(event.pure_text) == "skip" and config.ai_generated_art.config["ai绘画"]["sd画图"] and event.user_id == \
                config.common_config.basic_config["master"]["id"]:
            global turn
            try:
                await skipsd(config)
                msg = await bot.send(event, f"跳过任务成功")
                await delay_recall(bot, msg, 20)
            except Exception as e:
                bot.logger.error(e)
                msg = await bot.send(event, f"跳过任务失败: {e}")
                await delay_recall(bot, msg, 20)

    @bot.on(GroupMessageEvent)
    async def wdcard(event):
        message = str(event.pure_text)
        if message == 'getwd':
            r = await get_available_wildcards()
            await bot.send(event, r, True)
        elif message.startswith('getwd '):
            prompts = message.replace("getwd ", "")
            if prompts:
                prompts, log = await replace_wildcards(prompts)
                if log:
                    await bot.send(event, prompts)

    @bot.on(GroupMessageEvent)
    async def n4reDrawRun(event):
        global n4re

        if str(event.pure_text) == "n4re" or str(event.pure_text).startswith("n4re "):
            if not await get_img(event,bot):
                prompt = str(event.pure_text).replace("n4re ", "").replace("n4re", "").strip()
                n4re[event.sender.user_id] = [prompt]
                msg = await bot.send(event, "请发送要重绘的图片")
                await delay_recall(bot, msg)
                return

        # 处理图片和重绘命令
        if str(event.pure_text) == "n4re" or str(event.pure_text).startswith("n4re ") or event.sender.user_id in n4re:
            if await get_img(event,bot):
                if str(event.pure_text).startswith("n4re"):
                    prompt = str(event.pure_text).replace("n4re ", "").replace("n4re", "").strip()
                    n4re[event.sender.user_id] = [prompt]

                # 日志记录
                prompts = ', '.join(n4re[event.sender.user_id])
                if prompts:
                    prompts, log = await replace_wildcards(prompts)
                    if log:
                        await bot.send(event, log, True)
                bot.logger.info(f"接收来自群：{event.group_id} 用户：{event.sender.user_id} 的n4re指令 prompt: {prompts}")

                # 获取图片路径
                path = f"data/pictures/cache/{random_str()}.png"
                img_url = await get_img(event,bot)
                bot.logger.info(f"发起n4re请求，path:{path}|prompt:{prompts}")
                prompts_str = ' '.join(n4re[event.sender.user_id]) + ' '
                msg = await bot.send(event, "正在nai4重绘", True)
                await delay_recall(bot, msg)
                n4re.pop(event.sender.user_id)

                async def attempt_draw(retries_left=50):  # 这里是递归请求的次数
                    try:
                        args = sd_re_args.get(event.sender.user_id, {})
                        b64_in = await url_to_base64(img_url)
                        # 将 n4re[event.sender.user_id] 列表中的内容和 positive_prompt 合并成一个字符串
                        p = await n4re0(prompts_str, path, event.group_id, config, b64_in, args)
                        if not p:
                            bot.logger.info("色图已屏蔽")
                            msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                            await delay_recall(bot, msg)
                        elif p.startswith("审核api"):
                            bot.logger.info(p)
                            msg = await bot.send(event, p, True)
                            await delay_recall(bot, msg)
                        else:
                            await bot.send(event, [Text("nai4重绘结果"), Image(file=p)], True)
                    except Exception as e:
                        bot.logger.error(e)
                        if retries_left > 0:
                            bot.logger.error(f"尝试重新请求nai4re，剩余尝试次数：{retries_left - 1}")
                            await attempt_draw(retries_left - 1)
                        else:
                            msg = await bot.send(event, f"nai4重绘失败。{e}", True)
                            await delay_recall(bot, msg)

                await attempt_draw()

    @bot.on(GroupMessageEvent)
    async def n3reDrawRun(event):
        global n3re

        if str(event.pure_text) == "n3re" or str(event.pure_text).startswith("n3re "):
            if not await get_img(event,bot):
                prompt = str(event.pure_text).replace("n3re ", "").replace("n3re", "").strip()
                n3re[event.sender.user_id] = [prompt]
                msg = await bot.send(event, "请发送要重绘的图片")
                await delay_recall(bot, msg, 20)
                return

        # 处理图片和重绘命令
        if str(event.pure_text) == "n3re" or str(event.pure_text).startswith("n3re ") or event.sender.user_id in n3re:
            if await get_img(event,bot):
                if str(event.pure_text).startswith("n3re"):
                    prompt = str(event.pure_text).replace("n3re ", "").replace("n3re", "").strip()
                    n3re[event.sender.user_id] = [prompt]

                # 日志记录
                prompts = ', '.join(n3re[event.sender.user_id])
                if prompts:
                    prompts, log = await replace_wildcards(prompts)
                    if log:
                        await bot.send(event, log, True)
                bot.logger.info(f"接收来自群：{event.group_id} 用户：{event.sender.user_id} 的n3re指令 prompt: {prompts}")

                # 获取图片路径
                path = f"data/pictures/cache/{random_str()}.png"
                img_url = await get_img(event,bot)
                bot.logger.info(f"发起n3re请求，path:{path}|prompt:{prompts}")
                prompts_str = ' '.join(n3re[event.sender.user_id]) + ' '
                msg = await bot.send(event, "正在nai3重绘", True)
                await delay_recall(bot, msg, 20)
                n3re.pop(event.sender.user_id)

                async def attempt_draw(retries_left=50):  # 这里是递归请求的次数
                    try:
                        args = sd_re_args.get(event.sender.user_id, {})
                        b64_in = await url_to_base64(img_url)
                        # 将 n3re[event.sender.user_id] 列表中的内容和 positive_prompt 合并成一个字符串
                        p = await n3re0(prompts_str, path, event.group_id, config, b64_in, args)
                        if not p:
                            bot.logger.info("色图已屏蔽")
                            msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                            await delay_recall(bot, msg, 20)
                        elif p.startswith("审核api"):
                            bot.logger.info(p)
                            msg = await bot.send(event, p, True)
                            await delay_recall(bot, msg, 20)
                        else:
                            await bot.send(event, [Text("nai3重绘结果"), Image(file=p)], True)
                    except Exception as e:
                        bot.logger.error(e)
                        if retries_left > 0:
                            bot.logger.error(f"尝试重新请求nai3re，剩余尝试次数：{retries_left - 1}")
                            await attempt_draw(retries_left - 1)
                        else:
                            msg = await bot.send(event, f"nai3重绘失败。{e}", True)
                            await delay_recall(bot, msg, 20)

                await attempt_draw()

    @bot.on(GroupMessageEvent)
    async def sdmaskDrawRun(event):
        global UserGetm
        global turn
        global mask

        if str(event.pure_text) == "局部重绘" or str(event.pure_text).startswith("局部重绘 "):
            if not await get_img(event,bot):
                prompt = str(event.pure_text).replace("局部重绘 ", "").replace("局部重绘", "").strip()
                UserGetm[event.sender.user_id] = prompt  # 直接将值设置为字符串
                msg = await bot.send(event, "请发送要局部重绘的图片")
                await delay_recall(bot, msg, 20)
                return
            else:
                prompt = str(event.pure_text).replace("局部重绘 ", "").replace("局部重绘", "").strip()
                UserGetm[event.sender.user_id] = prompt
                img_url = await get_img(event,bot)
                msg = await bot.send(event, "请发送蒙版")
                await delay_recall(bot, msg, 20)
                mask[event.sender.user_id] = img_url
                return

        # 处理图片和重绘命令
        if event.sender.user_id in UserGetm and event.sender.user_id not in mask:
            if await get_img(event,bot):
                img_url = await get_img(event,bot)
                msg = await bot.send(event, "请发送蒙版")
                await delay_recall(bot, msg, 20)
                mask[event.sender.user_id] = img_url
                return

        if event.sender.user_id in UserGetm and event.sender.user_id in mask:
            if await get_img(event,bot):
                path = f"data/pictures/cache/{random_str()}.png"
                prompts = UserGetm[event.sender.user_id]  # 直接使用字符串
                mask_url = await get_img(event,bot)
                img_url = mask[event.sender.user_id]  # 直接使用字符串
                bot.logger.info(
                    f"接收来自群：{event.group_id} 用户：{event.sender.user_id} 的局部重绘指令 prompt: {prompts}")
                UserGetm.pop(event.sender.user_id)
                mask.pop(event.sender.user_id)

                try:
                    args = sd_re_args.get(event.sender.user_id, {})
                    b64_in = await url_to_base64(img_url)
                    mask_b64 = await url_to_base64(mask_url)

                    msg = await bot.send(event, f"开始局部重绘啦~sd前面排队{turn}人，请耐心等待喵~", True)
                    await delay_recall(bot, msg, 20)
                    turn += 1
                    p = await SdmaskDraw(prompts, path, config, event.group_id, b64_in, args, mask_b64)
                    if not p:
                        turn -= 1
                        bot.logger.info("色图已屏蔽")
                        msg = await bot.send(event, "杂鱼，色图不给你喵~", True)
                        await delay_recall(bot, msg, 20)
                    elif p.startswith("审核api"):
                        turn -= 1
                        bot.logger.info(p)
                        msg = await bot.send(event, p, True)
                        await delay_recall(bot, msg, 20)
                    else:
                        turn -= 1
                        await bot.send(event, [Text("sd局部重绘结果"), Image(file=p)], True)
                except Exception as e:
                    bot.logger.error(f"局部重绘失败: {e}")
                    msg = await bot.send(event, f"sd api局部重绘失败。{e}", True)
                    await delay_recall(bot, msg, 20)
                return

    @bot.on(GroupMessageEvent)
    async def end_re(event):
        if str(event.pure_text) == "/clearre":
            global UserGet
            global tag_user
            global UserGet1
            global n4re
            global n3re
            global mask
            global UserGetm

            dictionaries = {
                'UserGet': UserGet,
                'tag_user': tag_user,
                'UserGet1': UserGet1,
                'n4re': n4re,
                'n3re': n3re,
                'mask': mask,
                'UserGetm': UserGetm
            }

            user_id = event.sender.user_id

            for dict_name, dictionary in dictionaries.items():
                # 确保dictionary是一个字典
                if isinstance(dictionary, dict):
                    try:
                        dictionary.pop(user_id)
                        bot.logger.info(f"User ID {user_id} cleared in {dict_name}.")
                    except KeyError:
                        bot.logger.info(f"User ID {user_id} not found in {dict_name}.")
                else:
                    bot.logger.info(f"Expected a dictionary for {dict_name}, but got {type(dictionary)}.")

            msg = await bot.send(event, "已清除所有输入图片和文本缓存", True)
            await delay_recall(bot, msg, 20)

    @bot.on(GroupMessageEvent)
    async def img_info(event):
        global info_user

        if str(event.pure_text) == "imginfo":
            if not await get_img(event,bot):
                if config.ai_generated_art.config["ai绘画"]["sdUrl"][0] == "" or \
                        config.ai_generated_art.config["ai绘画"]["sdUrl"][0] is None:
                    msg = await bot.send(event, "sd api未配置，无法读图")
                    await delay_recall(bot, msg)
                    return
                info_user[event.sender.user_id] = []
                msg = await bot.send(event, "请发送要读的图片")
                await delay_recall(bot, msg, 20)
                return

        if str(event.pure_text) == "imginfo" or event.sender.user_id in info_user:
            if await get_img(event,bot):
                if config.ai_generated_art.config["ai绘画"]["sdUrl"][0] == "" or \
                        config.ai_generated_art.config["ai绘画"]["sdUrl"][0] is None:
                    msg = await bot.send(event, "sd api未配置，无法读图")
                    await delay_recall(bot, msg)
                    return
                if str(event.pure_text) == "imginfo":
                    info_user[event.sender.user_id] = []

                bot.logger.info(f"接收来自群：{event.group_id} 用户：{event.sender.user_id} 的读图指令")

                path = f"data/pictures/cache/{random_str()}.png"
                img_url = await get_img(event,bot)
                bot.logger.info(f"发起读图请求，path:{path}")
                info_user.pop(event.sender.user_id)

                try:
                    msg = await bot.send(event, "正在读图", True)
                    await delay_recall(bot, msg, 20)
                    b64_in = await url_to_base64(img_url)
                    tags_str = await get_img_info(b64_in, config.ai_generated_art.config["ai绘画"]["sdUrl"][0])
                    sendMes = [Node(content=[Text(str(event.sender.nickname) + "的图片信息：")]),
                               Node(content=[Text(tags_str)])]
                    await bot.send(event, sendMes)
                except Exception as e:
                    bot.logger.error(f"读图失败: {e}")
                    msg = await bot.send(event, f"读图失败: {e}", True)
                    await delay_recall(bot, msg, 20)
