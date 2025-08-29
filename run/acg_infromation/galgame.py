import datetime
import asyncio
from typing import Optional

from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Node, Text, Image
from framework_common.utils.system_logger import get_logger
from run.acg_infromation.service.galgame import Get_Access_Token, Get_Access_Token_json, flag_check, params_check, \
    get_game_image, \
    context_assemble, get_introduction
from run.streaming_media.service.Link_parsing import *
logger=get_logger(__name__)

def main(bot, config):
    """
    ai生成。
    """
    @bot.on(GroupMessageEvent)
    async def galgame_group_reply(event: GroupMessageEvent):
        if not should_handle_message(event.pure_text):
            return

        await galgame_group_check(event, bot, config)


def should_handle_message(text: str) -> bool:
    """快速检查消息是否需要处理，避免不必要的任务创建"""
    text_lower = text.lower()
    return (
            "gal" in text_lower or
            "新作" in text or
            "galgame推荐" == text or
            "gal推荐" == text or
            ("随机" in text and "gal" in text_lower)
    )


async def galgame_group_check(event: GroupMessageEvent, bot, config):
    """优化后的主处理函数"""
    # 暂定标记状态flag：
    # flag：1，精确游戏查询
    # flag：2，游戏列表查询
    # flag：3，gid 查询单个游戏的详情
    # flag：4，orgId 查询机构详情
    # flag：5，cid 查询角色详情
    # flag：6，orgId 查询机构下的游戏
    # flag：7，查询日期区间内发行的游戏
    # flag：8，随机游戏

    flag = 0
    flag_check_test = 0
    keyword = str(event.pure_text)
    filepath = 'data/pictures/galgame'
    cmList = []
    access_token: Optional[str] = None

    try:
        # 解析命令和参数
        flag, keyword, flag_check_test, date_info = parse_command(keyword)

        if flag == 0:
            return

        # 只有在需要时才获取access_token
        access_token = await Get_Access_Token()
        bot.logger.info(f'access_token：{access_token}，flag:{flag}，gal查询目标：{keyword}')

        # 根据不同的flag处理不同的逻辑
        result = await process_by_flag(flag, keyword, access_token, filepath, flag_check_test, date_info)

        if result is None:
            return

        # 发送结果
        await send_result(bot, event, result, flag_check_test, config)

    except Exception as e:
        bot.logger.error(f"处理galgame请求失败: {e}")
        await bot.send(event, "处理请求时发生错误，请稍后重试")


def parse_command(text: str) -> tuple:
    """解析命令，返回(flag, keyword, flag_check_test, date_info)"""
    flag = 0
    keyword = text
    flag_check_test = 0
    date_info = None

    # 处理gal查询相关
    if "gal" in text.lower():
        if "查询" in text:
            index = text.find("查询")
            if index != -1:
                keyword = text[index + len("查询"):].strip()
                if keyword.startswith((':', ' ', '：')):
                    keyword = keyword[1:].strip()

            flag = 2  # 默认列表查询

            if "精确" in text:
                flag = 1
            elif "机构" in text:
                flag = 4
                if "游戏" in text:
                    flag = 6
                    flag_check_test = 3
            elif "id" in text:
                flag = 3
            elif "角色" in text:
                flag = 5

    # 处理新作查询
    elif "新作" in text:
        now = datetime.datetime.now().date()
        flag = 7
        flag_check_test = 3

        if any(word in text for word in ["本日", "今日", "今天"]):
            date_info = (now, now)
            logger.info('本日新作查询')
        elif "昨日" in text:
            yesterday = now - datetime.timedelta(days=1)
            date_info = (yesterday, yesterday)
            logger.info('昨日新作查询')
        elif "本月" in text:
            first_day_this_month = now.replace(day=1)
            date_info = (first_day_this_month, now)
            logger.info('本月新作查询')
        else:
            flag = 0  # 无效的新作查询

    # 处理推荐
    elif (text in ["galgame推荐", "Galgame推荐", "gal推荐", "Gal推荐"] or
          ("随机" in text and "gal" in text.lower())):
        flag = 8
        flag_check_test = 3
        logger.info('galgame推荐开启')

    return flag, keyword, flag_check_test, date_info


async def process_by_flag(flag: int, keyword: str, access_token: str, filepath: str,
                          flag_check_test: int, date_info: tuple) -> dict:
    """根据flag处理不同的业务逻辑"""

    if flag == 2:  # 列表查询
        return await handle_list_search(flag, keyword, access_token, filepath)
    elif flag == 1:  # 精确查询
        return await handle_exact_search(flag, keyword, access_token, filepath)
    elif flag in [3, 4, 5]:  # 详情查询
        return await handle_detail_search(flag, keyword, access_token, filepath)
    elif flag == 6:  # 机构游戏查询
        return await handle_org_games(flag, keyword, access_token, filepath)
    elif flag == 7:  # 日期范围查询
        return await handle_date_range_search(flag, access_token, filepath, date_info)
    elif flag == 8:  # 随机推荐
        return await handle_random_recommendation(flag, keyword, access_token, filepath)

    return None


async def handle_list_search(flag: int, keyword: str, access_token: str, filepath: str) -> dict:
    """处理列表搜索"""
    url = flag_check(flag)
    params = params_check(flag, keyword)
    json_check = await Get_Access_Token_json(access_token, url, params)

    if not json_check.get('success'):
        return {'status': False, 'message': '查询失败'}

    total = json_check["data"]["total"]

    if total > 1:
        # 多个结果，返回列表
        gal_namelist = ''
        total = min(int(total), 10)  # 限制显示数量

        for i in range(total):
            data = json_check['data']['result'][i]
            name_check = data.get("chineseName") or data.get("name", "未知")
            gal_namelist += f"{name_check}\n"

        context = f'存在多个匹配对象，请发送 "gal精确查询" 来精确您的查询目标:\n{gal_namelist}'
        return {'status': True, 'type': 'text_only', 'context': context}

    elif total == 1:
        # 只有一个结果，直接返回详情
        data = json_check['data']['result'][0]
        name_check = data.get("chineseName") or data.get("name", "未知")
        return await handle_exact_search(1, name_check, access_token, filepath)

    return {'status': False, 'message': '未找到匹配结果'}


async def handle_exact_search(flag: int, keyword: str, access_token: str, filepath: str) -> dict:
    """处理精确搜索"""
    url = flag_check(flag)
    params = params_check(flag, keyword)
    json_check = await Get_Access_Token_json(access_token, url, params)

    if not json_check.get('success'):
        return {'status': False, 'message': '查询失败'}

    context = await context_assemble(json_check)
    mainImg_state = json_check["data"]["game"]["mainImg"]
    img_path = await get_game_image(mainImg_state, filepath)

    return {
        'status': True,
        'type': 'image_text',
        'context': context,
        'img_path': img_path
    }


async def handle_detail_search(flag: int, keyword: str, access_token: str, filepath: str) -> dict:
    """处理详情查询(gid/orgId/cid)"""
    url = flag_check(flag)
    params = params_check(flag, keyword)
    json_check = await Get_Access_Token_json(access_token, url, params)

    if not json_check.get('success'):
        return {'status': False, 'message': '查询失败'}

    context = await context_assemble(json_check)

    # 根据不同类型获取图片
    if flag == 3:  # game
        mainImg_state = json_check["data"]["game"]["mainImg"]
    elif flag == 4:  # org
        if 'mainImg' not in json_check["data"]["org"]:
            return {'status': False, 'message': '机构信息不完整'}
        mainImg_state = json_check["data"]["org"]["mainImg"]
    elif flag == 5:  # character
        mainImg_state = json_check["data"]["character"]["mainImg"]

    img_path = await get_game_image(mainImg_state, filepath)

    return {
        'status': True,
        'type': 'image_text',
        'context': context,
        'img_path': img_path
    }


async def handle_org_games(flag: int, keyword: str, access_token: str, filepath: str) -> dict:
    """处理机构游戏查询"""
    url = flag_check(flag)
    params = params_check(flag, keyword)
    json_check = await Get_Access_Token_json(access_token, url, params)

    if not json_check.get('success'):
        return {'status': False, 'message': '查询失败'}

    data_count = len(json_check["data"])
    if data_count == 0:
        return {'status': False, 'message': '该机构暂无游戏'}

    # 并发处理多个游戏信息
    tasks = []
    for data in json_check["data"]:
        tasks.append(process_single_game(data, filepath))

    results = await asyncio.gather(*tasks)

    return {
        'status': True,
        'type': 'multiple_games',
        'results': results
    }


async def handle_date_range_search(flag: int, access_token: str, filepath: str, date_info: tuple) -> dict:
    """处理日期范围查询"""
    url = flag_check(flag)
    start_date, end_date = date_info
    params = params_check(flag, True, start_date, end_date)
    json_check = await Get_Access_Token_json(access_token, url, params)

    if not json_check.get('success'):
        return {'status': False, 'message': '查询失败'}

    data_count = len(json_check["data"])
    if data_count == 0:
        return {'status': False, 'message': '该时间段暂无新作'}

    # 并发处理
    tasks = []
    for data in json_check["data"]:
        if data_count < 4:
            # 少于4个时获取详细介绍
            tasks.append(process_single_game_with_intro(data, filepath))
        else:
            tasks.append(process_single_game(data, filepath))

    results = await asyncio.gather(*tasks)

    return {
        'status': True,
        'type': 'multiple_games',
        'results': results
    }


async def handle_random_recommendation(flag: int, keyword: str, access_token: str, filepath: str) -> dict:
    """处理随机推荐"""
    url = flag_check(flag)
    params = params_check(flag, keyword)
    json_check = await Get_Access_Token_json(access_token, url, params)

    if not json_check.get('success'):
        return {'status': False, 'message': '推荐失败'}

    results = []
    for data in json_check["data"]:
        result = await process_single_game_with_intro(data, filepath)
        results.append(result)

    return {
        'status': True,
        'type': 'recommendation',
        'results': results
    }


async def process_single_game(data: dict, filepath: str) -> dict:
    """处理单个游戏信息"""
    context = await context_assemble(data)
    mainImg_state = data["mainImg"]
    img_path = await get_game_image(mainImg_state, filepath)

    return {
        'context': context,
        'img_path': img_path
    }


async def process_single_game_with_intro(data: dict, filepath: str) -> dict:
    """处理单个游戏信息（包含介绍）"""
    # 并发获取基础信息和介绍
    context_task = context_assemble(data)
    img_task = get_game_image(data["mainImg"], filepath)
    intro_task = get_introduction(data["gid"])

    context, img_path, introduction = await asyncio.gather(
        context_task, img_task, intro_task
    )

    return {
        'context': context,
        'img_path': img_path,
        'introduction': introduction
    }


async def send_result(bot, event: GroupMessageEvent, result: dict, flag_check_test: int, config):
    """发送处理结果"""
    if not result['status']:
        await bot.send(event, result.get('message', '处理失败'))
        return

    cmList = []

    if result['type'] == 'text_only':
        await bot.send(event, result['context'])
        return

    elif result['type'] == 'image_text':
        cmList.append(Node(content=[Image(file=result['img_path'])]))
        cmList.append(Node(content=[Text(result['context'])]))

    elif result['type'] == 'multiple_games':
        for item in result['results']:
            cmList.append(Node(content=[Image(file=item['img_path'])]))
            cmList.append(Node(content=[Text(item['context'])]))
            if 'introduction' in item:
                cmList.append(Node(content=[Text(item['introduction'])]))

    elif result['type'] == 'recommendation':
        cmList.append(Node(content=[Text('今天的gal推荐，请君过目：')]))

        # 检查是否使用绘图框架
        if config.acg_infromation.config["绘图框架"]['gal_recommend']:
            # 使用绘图框架处理
            for item in result['results']:
                text = f"{item['context']}\n{item['introduction']}"
                mainImg_state = f"https://store.ymgal.games/{item['img_path']}"

                bangumi_json = await gal_PILimg(
                    text, [mainImg_state], 'data/pictures/cache/',
                    type_soft='Galgame 推荐'
                )

                if bangumi_json['status']:
                    bot.logger.info('gal推荐图片制作成功，开始推送~~~')
                    await bot.send(event, Image(file=bangumi_json['pic_path']))
            return
        else:
            # 常规处理
            for item in result['results']:
                cmList.append(Node(content=[Image(file=item['img_path'])]))
                cmList.append(Node(content=[Text(item['context'])]))
                cmList.append(Node(content=[Text(item['introduction'])]))

    # 添加菜单信息
    if flag_check_test != 1:  # 不是列表查询时添加菜单
        menu_text = ('当前菜单：\n'
                     '1，gal查询\n'
                     '2，gid_gal单个游戏详情查询\n'
                     '3，orgId_gal机构详情查询\n'
                     '4，cid_gal游戏角色详情查询\n'
                     '5，orgId_gal机构下的游戏查询\n'
                     '6，本月新作，本日新作（单此一项请艾特bot食用\n'
                     '7，galgame推荐')

        footer_text = ('该功能由YMGalgame API实现，支持一下谢谢喵\n'
                       '本功能由"漫朔"开发\n'
                       '部分功能还在完善，欢迎催更')

        cmList.append(Node(content=[Text(menu_text)]))
        cmList.append(Node(content=[Text(footer_text)]))

    await bot.send(event, cmList)
