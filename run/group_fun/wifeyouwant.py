import asyncio
import datetime
import os
import random
import re
import threading
import traceback
from asyncio import sleep
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import weakref
import gc

import aiosqlite
import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from developTools.event.events import GroupMessageEvent, LifecycleMetaEvent
from developTools.message.message_components import Node, Text, Image, At
from run.group_fun.service.wife_you_want import manage_group_status, manage_group_add, \
    manage_group_check, PIL_lu_maker, \
    run_async_task, today_check_api, query_group_users, add_or_update_user_collect




def main(bot, config):
    global last_messages, membercheck, filepath

    # 使用有限大小的双端队列
    last_messages = {}
    filepath = 'data/pictures/cache'
    if not os.path.exists(filepath):
        os.makedirs(filepath)

    membercheck = {}

    # 启动定时清理任务
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_async_task, trigger=CronTrigger(hour=0, minute=0))

    def cleanup_memory():
        """定期清理内存中的无用数据"""
        global last_messages, membercheck

        try:
            current_time = datetime.now().timestamp()
            expired_keys = []

            for key, (timestamp, _) in list(membercheck.items()):
                if current_time - timestamp > 600:  # 10分钟
                    expired_keys.append(key)

            for key in expired_keys:
                membercheck.pop(key, None)

            if len(last_messages) > 100:
                sorted_groups = sorted(last_messages.keys())
                groups_to_remove = sorted_groups[:-100]
                for group_id in groups_to_remove:
                    last_messages.pop(group_id, None)

            # 强制垃圾回收
            gc.collect()

            bot.logger.info(f"内存清理完成，membercheck: {len(membercheck)}, last_messages: {len(last_messages)}")

        except Exception as e:
            bot.logger.error(f"内存清理失败: {e}")
    scheduler.add_job(cleanup_memory, trigger=CronTrigger(minute=0))  # 每小时清理一次
    scheduler.start()

    today_wife_api, header = config.group_fun.config["today_wife"]["api"], config.group_fun.config["today_wife"][
        "header"]



    @bot.on(GroupMessageEvent)
    async def today_wife(event: GroupMessageEvent):
        async with httpx.AsyncClient(timeout=30.0) as client:
            if not event.pure_text.startswith("今") or not config.group_fun.config["today_wife"]["今日老婆"]:
                return

            if ('今日' in str(event.pure_text) or '今天' in str(event.pure_text)) and '老婆' in str(event.pure_text):
                bot.logger.info("今日老婆开启！")

                if '张' in str(event.pure_text) or '个' in str(event.pure_text) or '位' in str(event.pure_text):
                    cmList = []
                    context = str(event.pure_text)
                    name_id_number = re.search(r'\d+', context)
                    if name_id_number:
                        number = int(name_id_number.group())
                        if number > 5:
                            await bot.send(event, '数量过多，渣男！！！！')
                            return

                    # 批量处理图片，避免多次创建临时文件
                    for i in range(number):
                        try:
                            response = await today_check_api(today_wife_api, header)
                            temp_path = f'{filepath}/today_wife_{i}.jpg'
                            with open(temp_path, 'wb') as file:
                                file.write(response.content)
                            bot.logger.info(f"api获取到第{i + 1}个老婆！")
                            cmList.append(Node(content=[Image(file=temp_path)]))
                        except Exception as e:
                            bot.logger.error(f"获取图片失败: {e}")
                            continue

                    if cmList:
                        await bot.send(event, cmList)

                    # 清理临时文件
                    for i in range(number):
                        temp_path = f'{filepath}/today_wife_{i}.jpg'
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            pass
                else:
                    try:
                        response = await today_check_api(today_wife_api, header)
                        img_path = f'{filepath}/today_wife.jpg'
                        with open(img_path, 'wb') as file:
                            file.write(response.content)
                        await bot.send(event, Image(file=img_path))

                        # 清理临时文件
                        try:
                            if os.path.exists(img_path):
                                os.remove(img_path)
                        except Exception:
                            pass
                    except Exception as e:
                        bot.logger.error(f"获取今日老婆失败: {e}")

    @bot.on(GroupMessageEvent)
    async def today_husband(event: GroupMessageEvent):
        async with httpx.AsyncClient(timeout=30.0) as client:
            if str(event.pure_text).startswith("今") and config.group_fun.config["today_wife"]["今日老公"]:
                if ('今日' in str(event.pure_text) or '今天' in str(event.pure_text)) and '老公' in str(
                        event.pure_text):
                    bot.logger.info("今日老公开启！")
                    params = {
                        "format": "json",
                        "num": '1',
                        'tag': '男子'
                    }
                    url = 'https://api.hikarinagi.com/random/v2/?'
                    try:
                        response = await client.get(url, params=params)
                        data = response.json()
                        url = data[0]['url']
                        proxy_url = url.replace("https://i.pximg.net/", "https://i.yuki.sh/")
                        bot.logger.info(f"搜索成功，作品pid：{data[0]['pid']}，反代url：{proxy_url}")
                        await bot.send(event, [Image(file=proxy_url)])
                    except Exception as e:
                        bot.logger.error(f"Error in today_husband: {e}")
                        await bot.send(event, 'api失效，望君息怒')

    @bot.on(GroupMessageEvent)
    async def today_luoli(event: GroupMessageEvent):
        async with httpx.AsyncClient(timeout=30.0) as client:
            if str(event.pure_text).startswith("今") and config.group_fun.config["today_wife"]["今日萝莉"]:
                if ('今日' in str(event.pure_text) or '今天' in str(event.pure_text)) and '萝莉' in str(
                        event.pure_text):
                    bot.logger.info("今日萝莉开启！")
                    params = {
                        "format": "json",
                        "num": '1',
                        'tag': 'ロリ'
                    }
                    url = 'https://api.hikarinagi.com/random/v2/?'
                    try:
                        response = await client.get(url, params=params)
                        data = response.json()
                        url = data[0]['url']
                        proxy_url = url.replace("https://i.pximg.net/", "https://i.yuki.sh/")
                        bot.logger.info(f"搜索成功，作品pid：{data[0]['pid']}，反代url：{proxy_url}")
                        await bot.send(event, [Image(file=proxy_url)])
                    except Exception as e:
                        bot.logger.error(f"Error in today_luoli: {e}")
                        await bot.send(event, 'api失效，望君息怒')

    @bot.on(GroupMessageEvent)
    async def api_collect(event: GroupMessageEvent):
        async with httpx.AsyncClient(timeout=30.0) as client:
            flag = 0
            url = None

            if '今日一言' == str(event.pure_text) or '答案之书' == str(event.pure_text) or '每日一言' == str(
                    event.pure_text):
                url = 'https://api.dwo.cc/api/yi?api=yan'
                flag = 1
                bot.logger.info("今日一言")
            elif 'emo时刻' == str(event.pure_text) or 'emo了' == str(event.pure_text) or '网抑云' == str(
                    event.pure_text):
                url = 'https://api.dwo.cc/api/yi?api=emo'
                flag = 1
                bot.logger.info("emo时刻")
            elif 'wyy评论' == str(event.pure_text) or '网易云评论' == str(event.pure_text):
                url = 'https://api.dwo.cc/api/yi?api=wyy'
                flag = 1
                bot.logger.info("网易云评论")
            elif '舔狗日记' == str(event.pure_text):
                url = 'https://api.dwo.cc/api/dog'
                flag = 1
                bot.logger.info("舔狗日记")

            if flag == 1 and url:
                try:
                    response = await client.get(url)
                    context = str(response.text)
                    await bot.send(event, context)
                except Exception as e:
                    bot.logger.error(f"API请求失败: {e}")
                    await bot.send(event, 'api出错了喵')

    @bot.on(GroupMessageEvent)
    async def today_LU(event: GroupMessageEvent):
        global membercheck
        context = event.pure_text or event.raw_message
        membercheck_id = int(event.sender.user_id)
        current_time = datetime.now().timestamp()

        if context.startswith('🦌') or context in {'戒🦌', '补🦌', '开启贞操锁', '关闭贞操锁'}:
            # 检查冷却时间（使用时间戳）
            if membercheck_id in membercheck:
                last_time, _ = membercheck[membercheck_id]
                if current_time - last_time < 5:  # 5秒冷却
                    if context in {'补🦌'}:
                        membercheck.pop(membercheck_id, None)
                    else:
                        await bot.send(event, '技能冷却ing')
                        bot.logger.info('检测到有人过于勤奋的🦌，跳过')
                        membercheck.pop(membercheck_id, None)
                        return

            membercheck[membercheck_id] = (current_time, 1)
        else:
            return

        lu_recall = ['不！给！你！🦌！！！', '我靠你怎么这么坏！', '再🦌都🦌出火星子了！！', '让我来帮你吧~', '好恶心啊~~',
                     '有变态！！', '你这种人渣我才不会喜欢你呢！', '令人害怕的坏叔叔', '才不给你计数呢！（哼', '杂鱼杂鱼',
                     '杂鱼哥哥还是处男呢', '哥哥怎么还在这呀，好可怜']

        try:
            if context.startswith('🦌'):
                target_id = int(event.sender.user_id)
                times_add = 0
                match = re.search(r"qq=(\d+)", context)
                if match:
                    target_id = match.group(1)
                else:
                    for context_check in context:
                        if context_check != '🦌':
                            membercheck.pop(membercheck_id, None)
                            return

                flag = random.randint(0, 100)
                if flag <= 8:
                    await bot.send(event, lu_recall[random.randint(0, len(lu_recall) - 1)])
                    membercheck.pop(membercheck_id, None)
                    return

                bot.logger.info(f'yes! 🦌!!!!, 目标：{target_id}')
                target_name = (await bot.get_group_member_info(event.group_id, target_id))['data']['nickname']

                if await manage_group_status('lu_limit', f'lu_others', target_id) == 1 and int(target_id) != int(
                        event.sender.user_id):
                    await bot.send(event, [At(qq=target_id), f' 是个好孩子，才不会给你呢~'])
                    membercheck.pop(membercheck_id, None)
                    return

                for context_check in context:
                    if context_check == '🦌':
                        times_add += 1

                current_date = datetime.now()
                current_year = current_date.year
                current_month = current_date.month
                current_year_month = f'{current_year}_{current_month}'
                current_day = current_date.day

                await manage_group_status(current_day, current_year_month, target_id, 1)
                times = await manage_group_status('lu', f'{current_year}_{current_month}_{current_day}', target_id)
                await manage_group_status('lu', f'{current_year}_{current_month}_{current_day}', target_id,
                                          times + times_add)

                times_total = await manage_group_status('lu_times_total', f'basic_info', target_id)
                await manage_group_status('lu_times_total', f'basic_info', target_id, times_total + times_add)

                length_add = sum(random.randint(1, 10) for _ in range(times_add))
                length_total = await manage_group_status('lu_length_total', f'basic_info', target_id)
                await manage_group_status('lu_length_total', f'basic_info', target_id, length_total + length_add)
                length_total_today = await manage_group_status('lu_length',
                                                               f'{current_year}_{current_month}_{current_day}',
                                                               target_id)
                await manage_group_status('lu_length', f'{current_year}_{current_month}_{current_day}', target_id,
                                          length_total_today + length_add)

                bot.logger.info(f'进入图片制作')
                img_url = await PIL_lu_maker(current_date, target_id, target_name)

                if img_url:
                    bot.logger.info('制作成功，开始发送~~')
                    if int(times + times_add) in {0, 1}:
                        times_record = int(await manage_group_status('lu_record', f'lu_others', target_id)) + 1
                        await manage_group_status('lu_record', f'lu_others', target_id, times_record)
                        recall_id = await bot.send(event, [At(qq=target_id), f' 今天🦌了！', Image(file=img_url)])
                    else:
                        recall_id = await bot.send(event, [At(qq=target_id), f' 今天🦌了{times + times_add}次！',
                                                           Image(file=img_url)])

                    if config.group_fun.config["today_wife"]["签🦌撤回"] is True:
                        await sleep(60)
                        try:
                            await bot.recall(recall_id['data']['message_id'])
                        except Exception:
                            pass

            elif '戒🦌' == context:
                bot.logger.info('No! 戒🦌!!!!')
                target_id = int(event.sender.user_id)
                target_name = (await bot.get_group_member_info(event.group_id, target_id))['data']['nickname']
                current_date = datetime.now()
                current_year = current_date.year
                current_month = current_date.month
                current_year_month = f'{current_year}_{current_month}'
                current_day = current_date.day
                await manage_group_status(current_day, current_year_month, target_id, 2)
                times = await manage_group_status('lu', f'{current_year}_{current_month}_{current_day}', target_id)
                await manage_group_status('lu', f'{current_year}_{current_month}_{current_day}', target_id, times + 1)
                img_url = await PIL_lu_maker(current_date, target_id, target_name, type='nolu')
                if img_url:
                    bot.logger.info('制作成功，开始发送~~')
                    await bot.send(event, [At(qq=target_id), f' 今天戒🦌了！', Image(file=img_url)])

            elif '补🦌' == context:
                bot.logger.info('yes! 补🦌!!!!')
                target_id = int(event.sender.user_id)
                target_name = (await bot.get_group_member_info(event.group_id, target_id))['data']['nickname']
                current_date = datetime.now()
                current_year = current_date.year
                current_month = current_date.month
                current_year_month = f'{current_year}_{current_month}'
                current_day = current_date.day

                membercheck.pop(membercheck_id, None)

                try:
                    times_record = int(await manage_group_status('lu_record', f'lu_others', target_id))
                    times_record_check = times_record // 3
                    if times_record_check == 0:
                        await bot.send(event, [At(qq=target_id),
                                               f' 您的补🦌次数好像不够呢喵~~（已连续{times_record}天）(3天1次)'])
                    else:
                        for i in range(current_day):
                            day = current_day - i
                            if int(await manage_group_status(day, current_year_month, target_id)) not in {1, 2}:
                                await manage_group_status(day, current_year_month, target_id, 1)
                                await manage_group_status('lu_record', f'lu_others', target_id, times_record - 3)

                                times_total = await manage_group_status('lu_times_total', f'basic_info', target_id)
                                await manage_group_status('lu_times_total', f'basic_info', target_id, times_total + 1)

                                length_total = await manage_group_status('lu_length_total', f'basic_info', target_id)
                                await manage_group_status('lu_length_total', f'basic_info', target_id,
                                                          length_total + random.randint(1, 10))

                                img_url = await PIL_lu_maker(current_date, target_id, target_name, type='supple_lu')
                                await bot.send(event, [At(qq=target_id), f' 您已成功补🦌！', Image(file=img_url)])
                                break
                except Exception as e:
                    bot.logger.error(f"补🦌失败: {e}")
                    await bot.send(event, [At(qq=target_id), f' 补🦌失败了喵~'])

            elif context in {'开启贞操锁', '关闭贞操锁'}:
                target_id = int(event.sender.user_id)
                value = 1 if context == '开启贞操锁' else 0
                await manage_group_status('lu_limit', f'lu_others', target_id, value)
                membercheck.pop(membercheck_id, None)
                message = '您已开启贞操锁~' if value else '您已关闭贞操锁~'
                await bot.send(event, message)

        except Exception as e:
            bot.logger.error(f"🦌功能处理异常: {e}")
        finally:
            # 确保清理membercheck
            if membercheck_id in membercheck:
                await sleep(5)
                membercheck.pop(membercheck_id, None)

    @bot.on(GroupMessageEvent)
    async def today_group_owner(event: GroupMessageEvent):
        flag_persona = 0
        target_id = None

        if event.message_chain.has(At):
            try:
                if '今日群友' in event.processed_message[0]['text'] or '今日老婆' in event.processed_message[0]['text']:
                    target_id = event.message_chain.get(At)[0].qq
                    flag_persona = 3
            except Exception:
                pass
        elif '今日群主' == str(event.pure_text):
            flag_persona = 1
            check = 'owner'
        elif '今日管理' == str(event.pure_text):
            flag_persona = 2
            check = 'admin'
        elif '今日群友' == str(event.pure_text):
            flag_persona = 3

        if flag_persona != 0:
            bot.logger.info("今日群主or群友任务开启")
            target_group = int(event.group_id)

            if target_id is None:
                try:
                    friendlist_get = await bot.get_group_member_list(event.group_id)
                    data_count = len(friendlist_get["data"])

                    if flag_persona in [2, 3, 4, 5] and data_count > 1000:
                        await bot.send(event, '抱歉，群聊人数过多，bot服务压力过大，仅开放今日群主功能，谢谢')
                        return

                    friendlist = []
                    for friend in friendlist_get["data"]:
                        data_check = friend['role']
                        if flag_persona in [1, 2, 5] and data_check == check:
                            friendlist.append(friend['user_id'])
                            if flag_persona in [1, 5] and data_check == 'owner':
                                break
                        elif flag_persona in [3, 4]:
                            friendlist.append(friend['user_id'])

                    if friendlist:
                        target_id = random.choice(friendlist)
                    else:
                        await bot.send(event, '未找到合适的目标')
                        return

                except Exception as e:
                    bot.logger.error(f"获取群成员列表失败: {e}")
                    return

            try:
                target_name = (await bot.get_group_member_info(target_group, target_id))['data']['nickname']
                today_wife_api, header = config.group_fun.config["today_wife"]["api"], config.group_fun.config["today_wife"]["header"]
                response = await today_check_api(today_wife_api, header)
                img_path = f'data/pictures/wife_you_want_img/today_wife.jpg'

                with open(img_path, 'wb') as file:
                    file.write(response.content)

                if config.group_fun.config["today_wife"]["is_at"]:
                    await bot.send_group_message(target_group, [f'这里是今天的 ', At(qq=target_id), f' 哟~~~\n',
                                                                Image(file=img_path)])
                else:
                    await bot.send(event, [f'这里是今天的 {target_name} 哟~~~\n', Image(file=img_path)])

                # 清理临时文件
                try:
                    if os.path.exists(img_path):
                        os.remove(img_path)
                except Exception:
                    pass

            except Exception as e:
                bot.logger.error(f"处理今日群友失败: {e}")
                traceback.print_exc()


    @bot.on(GroupMessageEvent)
    async def wife_you_want(event: GroupMessageEvent):
        wifePrefix = config.group_fun.config["today_wife"]["wifePrefix"]
        context = event.pure_text or event.raw_message

        if wifePrefix not in context:
            return

        # 热门群友统计
        if config.group_fun.config["today_wife"]["仅热门群友"]:
            target_group, from_id = int(event.group_id), int(event.sender.user_id)
            try:
                count_check = await manage_group_status(from_id, target_group, 'group_owner_record')
                await manage_group_status(from_id, target_group, 'group_owner_record', (count_check or 0) + 1)
            except Exception as e:
                bot.logger.error(f"更新热门群友统计失败: {e}")

        # 解析命令类型
        flag_persona = 0
        target_id_aim = None
        flag_aim = 0
        check = None
        from_id = int(event.sender.user_id)
        target_group = int(event.group_id)

        if '透群主' in context:
            flag_persona = 1
            check = 'owner'
        elif '透管理' in context:
            flag_persona = 2
            check = 'admin'
        elif '透群友' in context or '透' in context:
            flag_persona = 3
        elif '娶群友' in context:
            flag_persona = 4
            try:
                existing_wife = await manage_group_status(from_id, target_group, 'wife_you_get')
                if existing_wife != 0:
                    target_id_aim = existing_wife
                    flag_aim = 1
                else:
                    flag_aim = 0
            except Exception:
                flag_aim = 0
        elif '离婚' in context:
            try:
                if await manage_group_status(from_id, target_group, 'wife_you_get') != 0:
                    await manage_group_status(from_id, target_group, 'wife_you_get', 0)
                    await bot.send(event, '离婚啦，您现在是单身贵族咯~')
            except Exception as e:
                bot.logger.error(f"离婚处理失败: {e}")
            return
        elif '/今日群主' == context:
            flag_persona = 5
            check = 'owner'

        # 处理透群友逻辑
        if flag_persona in [3, 4] and not any(keyword in context for keyword in ["管理", "群主"]):
            # 解析目标用户
            name_id_number = re.search(r'\d+', context)
            target_found = False

            if name_id_number:
                target_id_aim = int(name_id_number.group())
                target_found = True
            elif "群友" not in context:
                # 按昵称搜索
                search_term = None
                if "透" in context:
                    index = context.find("透")
                    search_term = context[index + len("透"):]
                elif "娶" in context:
                    index = context.find("娶")
                    search_term = context[index + len("娶"):]

                if search_term:
                    try:
                        friendlist_get = await bot.get_group_member_list(event.group_id)
                        for friend in friendlist_get["data"]:
                            friend_names = [name for name in [friend.get("nickname"), friend.get("card")] if name]

                            if search_term in friend_names:
                                target_id_aim = friend['user_id']
                                target_found = True
                                flag_persona = 3 if "透" in context else 4
                                break
                    except Exception as e:
                        bot.logger.error(f"搜索群友失败: {e}")

            # 验证目标用户
            if target_found:
                if flag_persona == 4 and flag_aim == 1:
                    await bot.send(event, '渣男！吃着碗里的想着锅里的！', True)
                    return
                else:
                    # 验证用户是否在群内
                    if random.randint(1, 20) > 3:  # 85%概率通过
                        try:
                            group_member_check = await bot.get_group_member_info(target_group, target_id_aim)
                            if group_member_check['status'] == 'ok':
                                flag_aim = 1
                            else:
                                target_found = False
                        except Exception:
                            target_found = False

            # 随机拒绝
            if random.randint(1, 20) == 1:
                lu_recall = ['不许瑟瑟！！！！', '你是坏蛋！！', '色色是不允许的！', '不给！', '笨蛋哥哥',
                             '为什么不是我？', '看着我啊，我才不会帮你呢！', '逃跑喵']
                await bot.send(event, random.choice(lu_recall))
                return

        # 执行透群友功能
        if flag_persona != 0:
            bot.logger.info("透群友任务开启")

            try:
                from_name = str(event.sender.nickname)
                target_id = None

                # 获取目标用户
                if flag_aim == 1:
                    target_id = target_id_aim
                else:
                    # 获取群成员列表
                    try:
                        friendlist_get = await bot.get_group_member_list(event.group_id)
                        data_count = len(friendlist_get["data"])

                        if flag_persona in [2, 3, 4] and data_count > 1000:
                            await bot.send(event, '抱歉，群聊人数过多，bot服务压力过大，仅开放/透群主功能，谢谢')
                            return

                        friendlist = []

                        # 尝试获取热门群友列表
                        try:
                            if (config.group_fun.config["today_wife"]["仅热门群友"] and flag_persona not in [2, 1]):
                                friendlist_check = await query_group_users('group_owner_record', target_group)
                                friendlist = [member[0] for member in friendlist_check[:50]]  # 限制50个
                        except Exception:
                            bot.logger.error('透热门群友列表加载出错，执行全局随机')

                        # 如果热门群友列表为空，使用全员列表
                        if not friendlist:
                            for friend in friendlist_get["data"]:
                                if flag_persona in [1, 2, 5]:
                                    if friend['role'] == check:
                                        friendlist.append(friend['user_id'])
                                        if flag_persona in [1, 5] and friend['role'] == 'owner':
                                            break
                                elif flag_persona in [3, 4]:
                                    friendlist.append(friend['user_id'])

                        if friendlist:
                            target_id = random.choice(friendlist)
                        else:
                            await bot.send(event, '未找到合适的目标')
                            return

                    except Exception as e:
                        bot.logger.error(f"获取群成员列表失败: {e}")
                        return

                # 更新统计
                if flag_aim == 0 and flag_persona == 1:
                    await manage_group_status(from_id, target_group, 'group_owner')

                bot.logger.info(f'群：{target_group}，透群友目标：{target_id}')

                # 获取目标用户信息
                try:
                    group_member_check = await bot.get_group_member_info(target_group, target_id)
                    if flag_persona == 4 and await manage_group_status(from_id, target_group, 'wife_you_get') != 0:
                        target_name = str(await manage_group_status(from_id, target_group, 'wife_you_get'))
                    else:
                        target_name = str(group_member_check['data']['nickname'])

                    if flag_persona == 4:
                        if await manage_group_status(from_id, target_group, 'wife_you_get') == 0:
                            await manage_group_status(from_id, target_group, 'wife_you_get', target_id)
                except Exception as e:
                    bot.logger.error(f"获取目标用户信息失败: {e}")
                    return

                # 构建头像URL
                target_img_path = f"https://q1.qlogo.cn/g?b=qq&nk={target_id}&s=640"

                # 发送消息
                recall_id = None
                try:
                    if flag_persona == 1:
                        times = await manage_group_status(target_id, target_group, 'group_owner') or 0
                        times += 1
                        await manage_group_status(target_id, target_group, 'group_owner', times)
                        recall_id = await bot.send(event, [
                            f'@{from_name} 恭喜你涩到群主！！！！',
                            Image(file=target_img_path),
                            f'群主【{target_name}】今天这是第{times}次被透了呢'
                        ])
                    elif flag_persona == 2:
                        recall_id = await bot.send(event, [
                            f'@{from_name} 恭喜你涩到管理！！！！',
                            Image(file=target_img_path),
                            f'【{target_name}】 ({target_id})哒！'
                        ])
                    elif flag_persona == 3:
                        message_text = ('恭喜你涩到了群友！！！！' if flag_aim == 1 else '今天你的色色对象是')
                        recall_id = await bot.send(event, [
                            f'@{from_name} {message_text}',
                            Image(file=target_img_path),
                            f'【{target_name}】 ({target_id})哒！'
                        ])
                    elif flag_persona == 4:
                        message_text = ('恭喜你娶到了群友！！！！' if flag_aim == 1 else '今天你的结婚对象是')
                        recall_id = await bot.send(event, [
                            f'@{from_name} {message_text}',
                            Image(file=target_img_path),
                            f'【{target_name}】 ({target_id})哒！'
                        ])
                    elif flag_persona == 5:
                        today_wife_api, header = (config.group_fun.config["today_wife"]["api"],
                                                  config.group_fun.config["today_wife"]["header"])
                        response = await today_check_api(today_wife_api, header)
                        img_path = f'data/pictures/wife_you_want_img/today_wife.jpg'
                        with open(img_path, 'wb') as file:
                            file.write(response.content)
                        await bot.send(event, [f'这里是今天的{target_name}哟~~~\n', Image(file=img_path)])

                        # 清理临时文件
                        try:
                            if os.path.exists(img_path):
                                os.remove(img_path)
                        except Exception:
                            pass

                    # 撤回消息
                    if (config.group_fun.config["today_wife"]["透群友撤回"] is True and
                            recall_id and 'data' in recall_id):
                        try:
                            await sleep(20)
                            await bot.recall(recall_id['data']['message_id'])
                        except Exception as e:
                            bot.logger.error(f"撤回消息失败: {e}")

                    # 更新记录
                    if target_name:
                        await manage_group_add(from_id, target_id, target_group)

                except Exception as e:
                    bot.logger.error(f"发送透群友消息失败: {e}")

            except Exception as e:
                bot.logger.error(f"透群友功能异常: {e}")

        # 处理记录查询
        if ('记录' in context and
                any(keyword in context for keyword in ['色色', '瑟瑟', '涩涩'])):
            bot.logger.info('色色记录启动！')

            try:
                # 确定查询类型
                if any(keyword in context for keyword in ['本周', '每周', '星期']):
                    type_context = '以下是本周色色记录：'
                    query_type = 'week'
                elif any(keyword in context for keyword in ['本月', '月份', '月']):
                    query_type = 'month'
                    type_context = '以下是本月色色记录：'
                elif '年' in context:
                    query_type = 'Year'
                    type_context = '以下是年度色色记录：'
                else:
                    type_context = '以下是本日色色记录：'
                    query_type = 'day'

                list_from, list_target = await manage_group_check(target_group, query_type)

                if not list_from or not list_target:
                    await bot.send(event, '本群好像还没有一个人开过趴捏~')
                    return

                # 获取群成员信息
                friendlist_get = await bot.get_group_member_list(event.group_id)
                member_dict = {str(member['user_id']): member['nickname'] for member in friendlist_get['data']}

                # 构建消息
                cmList = [Node(content=[Text(type_context)])]

                # 透别人最多的人
                from_king_id = list_from[0][0]
                from_king_name = member_dict.get(from_king_id, '未知用户')
                cmList.append(Node(content=[
                    Text('透群友最多的人诞生了！！'),
                    Image(file=f"https://q1.qlogo.cn/g?b=qq&nk={from_king_id}&s=640"),
                    Text(f'是【{from_king_name}】 ({from_king_id})哦~')
                ]))

                # 透别人次数列表
                context_from = '以下是透别人的次数~\n'
                for user_id, count in list_from:
                    user_name = member_dict.get(user_id, '未知用户')
                    context_from += f'{user_name} ({user_id}): {count} 次\n'
                cmList.append(Node(content=[Text(context_from)]))

                # 被透最多的人
                target_king_id = list_target[0][0]
                target_king_name = member_dict.get(target_king_id, '未知用户')
                cmList.append(Node(content=[
                    Text('被群友透最多的人诞生了！！'),
                    Image(file=f"https://q1.qlogo.cn/g?b=qq&nk={target_king_id}&s=640"),
                    Text(f'是【{target_king_name}】 ({target_king_id})哦~')
                ]))

                # 被透次数列表
                context_target = '以下是被别人透的次数~\n'
                for user_id, count in list_target:
                    user_name = member_dict.get(user_id, '未知用户')
                    context_target += f'{user_name} ({user_id}): {count} 次\n'
                cmList.append(Node(content=[Text(context_target)]))

                await bot.send(event, cmList)

            except Exception as e:
                bot.logger.error(f"生成色色记录失败: {e}")
                await bot.send(event, '生成记录时出现错误，请稍后重试')



