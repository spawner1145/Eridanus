from collections import deque, Counter
from developTools.event.events import GroupMessageEvent
from framework_common.database_util.User import get_user
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager

group_message_queue = {}



def main(bot: ExtendBot, config: YAMLManager):

    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        if not config.groupManager.config["BullshitMsgBlocker"]["enable"]:
            return
        group_id = event.group_id
        user_id = event.user_id

        if group_id not in config.groupManager.config["BullshitMsgBlocker"]["blockList"]:
            return

        # 初始化群消息队列
        if group_id not in group_message_queue:
            group_message_queue[group_id] = deque(maxlen=config.groupManager.config["BullshitMsgBlocker"]["消息缓存池大小"])

        # 记录新消息
        group_message_queue[group_id].append(user_id)

        # 统计最近 6 条消息中每个用户的出现次数
        counter = Counter(group_message_queue[group_id])
        top_user, count = counter.most_common(1)[0]

        # 判断是否刷屏
        if count >= config.groupManager.config["BullshitMsgBlocker"]["每人最大发言数量"]:
            user_info = await get_user(event.user_id)
            if user_info.permission >= config.system_plugin.config["BullshitMsgBlocker"]["白名单所需权限等级"]:
                bot.logger.info(f"BullshitmsgBlocker： 用户{event.user_id} 权限满足白名单条件，不禁言")
                group_message_queue[group_id].clear()
                return
            await bot.mute(group_id, top_user, config.groupManager.config["BullshitMsgBlocker"]["禁言时长"])
            bot.logger.info(f"用户 {top_user} 因短时间内连续发送消息过多，已被禁言。")
            await bot.send(event, config.groupManager.config["BullshitMsgBlocker"]["嘲讽"])
            group_message_queue[group_id].clear()  # 清空队列防止重复触发
