import ast
import asyncio
import re
import uuid

from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from developTools.message.message_components import Text, Image,Mface
from framework_common.database_util.Group import add_to_group
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.utils import download_img
from run.auto_reply.service.cache_layer import CacheManager
from run.auto_reply.service.keyword_manager import KeywordManager

# 全局实例
keyword_manager = None
cache_manager = None

bot_name=None
ymconfig=None
def main(bot: ExtendBot, config: YAMLManager):
    global keyword_manager, cache_manager,bot_name,ymconfig
    ymconfig=config
    # 初始化管理器
    keyword_manager = KeywordManager()
    cache_manager = CacheManager(max_size=1000)  # 可配置缓存大小

    # 用户添加状态管理
    user_adding_state = {}
    # 超时任务管理
    timeout_tasks = {}
    bot_name=config.common_config.basic_config["bot"]
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        text = event.pure_text.strip()
        user_id = event.user_id
        group_id = event.group_id

        if user_id in user_adding_state:
            await handle_adding_mode(bot, event, user_adding_state, text, timeout_tasks)
            return

        if text == "开始添加":
            user_info=await get_user(event.user_id)
            if user_info.permission >= config.auto_reply.config["分群词库权限"]:
                await start_adding_mode(bot, event, user_adding_state, timeout_tasks, is_global=False)
            else:
                await bot.send(event, "你没有权限使用该功能")
            return
        elif text == "*开始添加":
            user_info=await get_user(event.user_id)
            if user_info.permission >= config.auto_reply.config["全局词库权限"]:
                await start_adding_mode(bot, event, user_adding_state, timeout_tasks, is_global=True)
            else:
                await bot.send(event, "你没有权限使用该功能")
            return
        elif text.startswith("删除关键词 "):
            user_info=await get_user(event.user_id)
            if user_info.permission >= config.auto_reply.config["分群词库权限"]:
                keyword = text[6:].strip()  # 提取关键词
                if not keyword:
                    await bot.send(event, "请提供要删除的关键词")
                    return
                await handle_delete_keyword(bot, event, keyword, group_id,isglobal=False)
            else:
                await bot.send(event, "你没有权限使用该功能")
            return
        elif text.startswith("*删除关键词 "):
            user_info=await get_user(event.user_id)
            if user_info.permission >= config.auto_reply.config["全局词库权限"]:
                keyword = text[7:].strip()  # 提取关键词
                if not keyword:
                    await bot.send(event, "请提供要删除的关键词")
                    return
                await handle_delete_keyword(bot, event, keyword, group_id,isglobal=True)
            else:
                await bot.send(event, "你没有权限使用该功能")

            return
        await process_keyword_match(bot, event, text, group_id)


async def handle_adding_mode(bot, event, user_adding_state, text, timeout_tasks):
    """处理添加模式下的消息"""
    user_id = event.user_id
    state = user_adding_state[user_id]

    if text == "结束添加":
        await finish_adding(bot, event, user_adding_state, user_id, timeout_tasks)
        return

    if state["waiting_for_key"]:
        if not text:
            await bot.send(event, "请发送要添加的关键词")
            return
        # 记录关键词
        state["current_key"] = text
        state["waiting_for_key"] = False
        state["waiting_for_values"] = True
        state["values"] = []

        await bot.send(event, f"已记录关键词：{text}\n请发送对应的回复内容，发送'结束添加'可退出添加模式")

        # 重置10秒超时
        await reset_timeout(bot, event, user_adding_state, user_id, timeout_tasks)

    elif state["waiting_for_values"]:
        # 记录回复内容 - 保持原始message_chain格式
        temp_meschain = []
        for i in event.message_chain:
            if isinstance(i, Image) or isinstance(i,Mface):
                path = f"data/pictures/auto_reply/{uuid.uuid4()}.png"
                await download_img(i.file or i.url, path)
                temp_meschain.append(Image(file=path))
            else:
                temp_meschain.append(i)
        state["values"].append(temp_meschain)

        await bot.send(event, f"已添加回复内容 ({len(state['values'])}条)")

        # 重置10秒超时 - 修复：每次添加值后都要重置超时
        await reset_timeout(bot, event, user_adding_state, user_id, timeout_tasks)


# 修复版的finish_adding函数，增加缓存清理
async def finish_adding(bot, event, user_adding_state, user_id, timeout_tasks, timeout=False):
    """完成添加流程 - 修复1: 添加时清理相关缓存"""
    print(f"开始完成添加流程，用户: {user_id}, 是否超时: {timeout}")

    if user_id not in user_adding_state:
        print(f"用户 {user_id} 不在添加状态中，直接返回")
        return

    # 清理超时任务
    if user_id in timeout_tasks:
        try:
            if not timeout_tasks[user_id].done():
                print(f"取消用户 {user_id} 的超时任务")
                timeout_tasks[user_id].cancel()
                try:
                    await timeout_tasks[user_id]
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            print(f"清理超时任务时发生错误: {e}")
        finally:
            del timeout_tasks[user_id]

    state = user_adding_state[user_id]

    try:
        if state["current_key"] and state["values"]:
            print(f"保存关键词: {state['current_key']}, 回复数量: {len(state['values'])}")
            # 保存到数据库 - 修复1: 传递cache_manager
            success = await keyword_manager.add_keyword(
                keyword=state["current_key"],
                responses=state["values"],
                group_id=state["group_id"],
                cache_manager=cache_manager  # 传递cache_manager以便清理缓存
            )

            if success:
                mode_text = "全局词库" if state["is_global"] else f"群词库"
                timeout_text = " (超时自动结束)" if timeout else ""
                await bot.send(event,
                               f"✅ 成功添加到{mode_text}:\n关键词: {state['current_key']}\n回复数量: {len(state['values'])}条{timeout_text}")
            else:
                await bot.send(event, "❌ 添加失败，请稍后重试")
        else:
            timeout_text = " (超时)" if timeout else ""
            await bot.send(event, f"添加已取消{timeout_text}")
    except Exception as e:
        print(f"完成添加时发生错误: {e}")
        await bot.send(event, "❌ 处理失败，请稍后重试")
    finally:
        # 确保清理状态
        if user_id in user_adding_state:
            print(f"清理用户 {user_id} 的添加状态")
            del user_adding_state[user_id]
        print(f"完成添加流程结束，用户: {user_id}")


async def start_adding_mode(bot, event, user_adding_state, timeout_tasks, is_global):
    """开始添加模式"""
    user_id = event.user_id
    group_id = event.group_id if not is_global else None

    user_adding_state[user_id] = {
        "group_id": group_id,
        "is_global": is_global,
        "waiting_for_key": True,
        "waiting_for_values": False,
        "current_key": None,
        "values": [],
        "last_activity": asyncio.get_event_loop().time()
    }

    mode_text = "全局词库" if is_global else f"群 {group_id} 词库"
    await bot.send(event, f"开始向{mode_text}添加关键词\n请发送要添加的关键词")

    # 启动10秒超时检查
    await reset_timeout(bot, event, user_adding_state, user_id, timeout_tasks)


async def reset_timeout(bot, event, user_adding_state, user_id, timeout_tasks):
    """重置超时任务"""
    # 取消之前的超时任务
    if user_id in timeout_tasks:
        try:
            if not timeout_tasks[user_id].done():
                timeout_tasks[user_id].cancel()
                try:
                    await timeout_tasks[user_id]
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            print(f"取消超时任务时发生错误: {e}")

    # 更新最后活动时间
    if user_id in user_adding_state:
        user_adding_state[user_id]["last_activity"] = asyncio.get_event_loop().time()

    # 创建新的超时任务
    timeout_tasks[user_id] = asyncio.create_task(
        timeout_checker(bot, event, user_adding_state, user_id, timeout_tasks)
    )
    print(f"为用户 {user_id} 创建新的超时任务，任务ID: {id(timeout_tasks[user_id])}")


async def timeout_checker(bot, event, user_adding_state, user_id, timeout_tasks):
    """10秒超时检查"""
    task_id = id(asyncio.current_task())
    print(f"超时检查任务开始，用户: {user_id}, 任务ID: {task_id}")

    try:
        # 等待10秒
        slep_time=config.auto_reply.config["词库添加自动超时"]
        await asyncio.sleep(10)

        print(f"超时时间到，检查用户 {user_id} 状态")

        # 检查用户是否还在添加状态中
        if user_id not in user_adding_state:
            print(f"用户 {user_id} 已不在添加状态，超时任务结束")
            return

        print(f"用户 {user_id} 超时，触发自动结束")
        # 超时处理
        await finish_adding(bot, event, user_adding_state, user_id, timeout_tasks, timeout=True)

    except asyncio.CancelledError:
        print(f"超时任务被取消，用户: {user_id}, 任务ID: {task_id}")
        # 任务被取消，正常情况（用户有新活动）
        raise
    except Exception as e:
        print(f"超时检查错误，用户: {user_id}, 错误: {e}")
    finally:
        print(f"超时检查任务结束，用户: {user_id}, 任务ID: {task_id}")


# 修复3: 更新的删除关键词处理函数
async def handle_delete_keyword(bot, event, keyword, group_id,isglobal=False):
    """处理删除关键词 - 修复3: 提供相似关键词建议"""
    try:
        if not isglobal:
        # 尝试删除群词库中的关键词
            result = await keyword_manager.delete_keyword(keyword, group_id)
    
            if result["success"]:
                # 删除成功 - 清除缓存
                await cache_manager.delete_cache(keyword, group_id)
                await bot.send(event, f"✅ 成功删除群 {group_id} 词库中的关键词: {keyword}")
                return
        else:
            # 如果群词库中没有，尝试删除全局词库
            global_result = await keyword_manager.delete_keyword(keyword, None)
            if global_result["success"]:
                # 清除缓存
                await cache_manager.delete_cache(keyword, None)
                await bot.send(event, f"✅ 成功删除全局词库中的关键词: {keyword}")
                return

        # 删除失败 - 提供相似关键词建议
        error_msg = f"❌ 未找到关键词: {keyword}"

        # 检查群词库的相似关键词
        similar_keywords = result.get("similar", [])
        # 检查全局词库的相似关键词
        global_similar = global_result.get("similar", [])

        # 合并并去重相似关键词
        all_similar = {}
        for item in similar_keywords + global_similar:
            kw = item["keyword"]
            if kw not in all_similar or all_similar[kw]["similarity"] < item["similarity"]:
                all_similar[kw] = item

        # 转换为列表并排序
        similar_list = list(all_similar.values())
        similar_list.sort(key=lambda x: x["similarity"], reverse=True)

        if similar_list:
            suggestions = []
            for item in similar_list[:5]:  # 只显示前5个
                suggestions.append(f"• {item['keyword']} (相似度: {item['similarity']}%)")

            suggestion_text = "\n".join(suggestions)
            error_msg += f"\n\n💡 您是否想删除以下相似的关键词之一：\n{suggestion_text}"
            error_msg += "\n\n请使用确切的关键词名称重试，如：删除关键词 实际关键词"

        await bot.send(event, error_msg)

    except Exception as e:
        print(f"删除关键词错误: {e}")
        await bot.send(event, f"❌ 删除关键词失败: {keyword}")


async def process_keyword_match(bot, event, text, group_id):
    """处理关键字匹配 - 修复1&2: 优化缓存策略确保最新数据"""
    if not text:
        return

    # 非阻塞匹配
    asyncio.create_task(match_and_reply(bot, event, text, group_id))


async def match_and_reply(bot, event, text, group_id):
    """异步匹配和回复 - 修复1&2: 优化缓存和随机选择逻辑"""
    try:
        # 修复1: 优化缓存策略 - 先检查数据库获取最新数据
        # 直接从数据库匹配，确保获取最新的关键词数据
        response = await keyword_manager.match_keyword(text, group_id)

        if response:
            # 还原message_chain格式
            response_chain = restore_message_chain(response)

            # 修复1: 更新缓存为最新的响应结果
            # 注意：由于随机性，我们缓存的是匹配到的关键词信息，而不是具体的响应
            # 这样可以保持随机性同时提供一定的性能优化
            await cache_manager.set(text, group_id, response)

            await bot.send(event, response_chain)
            for mes in response_chain:
                if isinstance(mes, Text):
                    self_message = {"user_name": bot_name, "user_id": 0000000,
                                    "message": [{"text": mes.text}]}
                    await add_to_group(event.group_id, self_message)
            return

        # 如果数据库没有匹配，再检查缓存（用于一些计算密集型的负匹配）
        cached_response = await cache_manager.get(text, group_id)
        if cached_response == "NO_MATCH":  # 缓存标记：此文本无匹配
            return

        # 标记为无匹配并缓存（避免重复计算）
        await cache_manager.set(text, group_id, "NO_MATCH")

    except Exception as e:
        print(f"匹配错误: {e}")


def restore_message_chain(response_data):
    """还原message_chain格式，支持Text和Image混合，处理复杂字段"""
    try:
        # Case 1: response_data is a string
        if isinstance(response_data, str):
            # Try to parse as a serialized Python object (e.g., '[Text(...)]' or '[Image(...)]')
            try:
                parsed_data = ast.literal_eval(response_data)
                if isinstance(parsed_data, list):
                    return [restore_single_component(item) for item in parsed_data]
                elif isinstance(parsed_data, (Text, Image)):
                    return [parsed_data]
                else:
                    return [Text(text=str(response_data))]
            except (ValueError, SyntaxError):
                # Fallback to regex-based parsing
                message_chain = []

                # Extract Text components with optional comp_type
                text_matches = re.findall(
                    r"Text\(comp_type='[^']*', text='([^']*)'\)|Text\(text='([^']*)'\)",
                    response_data
                )
                for match in text_matches:
                    # match[0] is text from complex form, match[1] is text from simple form
                    text = match[0] or match[1]
                    message_chain.append(Text(text=text))

                # Extract Image components with complex fields
                image_matches = re.findall(
                    r"Image\(comp_type='[^']*', file='([^']*)', url='([^']*)', type='[^']*', summary='[^']*'\)",
                    response_data
                )
                for file, url in image_matches:
                    image_kwargs = {}
                    if file:
                        image_kwargs['file'] = file
                    if url:
                        image_kwargs['url'] = url
                    message_chain.append(Image(**image_kwargs))

                # If no matches, treat as plain text
                if not message_chain:
                    return [Text(text=response_data)]
                return message_chain

        # Case 2: response_data is a list (e.g., already deserialized components)
        elif isinstance(response_data, list):
            message_chain = []
            for item in response_data:
                if isinstance(item, dict):
                    # Handle dictionary-based components (e.g., from JSON)
                    if item.get('type') == 'Text' and 'text' in item:
                        message_chain.append(Text(text=item['text']))
                    elif item.get('type') in ['Image', 'Mface']:
                        image_kwargs = {}
                        if item.get('file'):
                            image_kwargs['file'] = item['file']
                        if item.get('url'):
                            image_kwargs['url'] = item['url']
                        message_chain.append(Image(**image_kwargs))
                elif isinstance(item, (Text, Image)):
                    message_chain.append(item)
                else:
                    message_chain.append(Text(text=str(item)))
            return message_chain

        # Case 3: Fallback for other types
        else:
            return [Text(text=str(response_data))]

    except Exception as e:
        print(f"还原message_chain错误: {e}")
        return [Text(text=str(response_data))]


def restore_single_component(item):
    """还原单个组件（Text或Image）"""
    if isinstance(item, dict) and item.get('__class__') == 'Text':
        return Text(text=item.get('text', ''))
    elif isinstance(item, dict) and item.get('__class__') in ['Image', 'Mface']:
        image_kwargs = {}
        if item.get('file'):
            image_kwargs['file'] = item['file']
        if item.get('url'):
            image_kwargs['url'] = item['url']
        return Image(**image_kwargs)
    elif isinstance(item, (Text, Image)):
        return item
    else:
        return Text(text=str(item))
