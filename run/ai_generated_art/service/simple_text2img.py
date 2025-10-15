from loguru import logger

from framework_common.utils.random_str import random_str
from run.ai_generated_art.service.aiDraw import SdDraw0
from run.ai_generated_art.service.wildcard import replace_wildcards


async def simple_call_text2img1( config, tag):

    if config.ai_generated_art.config["ai绘画"]["sd画图"] and config.ai_generated_art.config["ai绘画"][
        "sdUrl"] != "" and config.ai_generated_art.config["ai绘画"]["sdUrl"] != '':
        global turn
        global sd_user_args
        tag, log = await replace_wildcards(tag)

        path = f"data/pictures/cache/{random_str()}.png"
        log.info(f"开始调用sd api。{tag}")
        try:

            args = sd_user_args.get(114514, {})

            p = await SdDraw0(tag, path, config, 114514, args)

            return p

        except Exception as e:
            logger.error(e)
            logger.error(f"sd api调用失败。{e}")
