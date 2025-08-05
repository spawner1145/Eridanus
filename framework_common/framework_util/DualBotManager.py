# dual_bot_manager.py
import asyncio
from typing import Union, Optional
from developTools.adapters.websocket_adapter import WebSocketBot

from developTools.event.base import EventBase
from developTools.message.message_components import MessageComponent
from framework_common.framework_util.websocket_fix import ExtendBot


class DualBotManager:
    """双Bot管理器，负责协调两个Bot之间的消息转发"""

    def __init__(self, primary_bot: ExtendBot, secondary_bot: WebSocketBot, target_group_id: int = 879886836):
        self.primary_bot = primary_bot
        self.secondary_bot = secondary_bot
        self.target_group_id = target_group_id

        # 设置消息转发
        self._setup_message_forwarding()
        # 重写主Bot的send方法
        self._override_primary_bot_send()

    def _setup_message_forwarding(self):
        """设置从副Bot到主Bot的消息转发"""
        # 保存副Bot的原始_receive方法
        original_receive = self.secondary_bot._receive

        async def forwarding_receive():
            """重写副Bot的_receive方法，实现消息转发"""
            try:
                async for response in self.secondary_bot.websocket:
                    import json
                    from developTools.event.eventFactory import EventFactory

                    data = json.loads(response)

                    # 处理心跳等非业务消息
                    if 'heartbeat' not in str(data):
                        self.secondary_bot.logger.info_msg(f"副Bot收到服务端响应: {data}")

                    # 处理API响应
                    if "status" in data and "echo" in data:
                        echo = data["echo"]
                        future = self.secondary_bot.response_callbacks.pop(echo, None)
                        if future and not future.done():
                            future.set_result(data)
                    # 处理事件消息
                    elif "post_type" in data:
                        event_obj = EventFactory.create_event(data)

                        # 设置副Bot的ID
                        try:
                            if event_obj.post_type == "meta_event" and event_obj.meta_event_type == "lifecycle":
                                self.secondary_bot.id = int(event_obj.self_id)
                                self.secondary_bot.logger.info(f"副Bot ID: {self.secondary_bot.id}")
                        except:
                            pass

                        if event_obj:
                            # 将副Bot接收到的事件转发给主Bot的事件总线处理
                            asyncio.create_task(self.primary_bot.event_bus.emit(event_obj))
                        else:
                            self.secondary_bot.logger.warning("副Bot无法匹配事件类型，跳过处理。")
                    else:
                        self.secondary_bot.logger.warning("副Bot收到未知消息格式，已忽略。")

            except Exception as e:
                self.secondary_bot.logger.error(f"副Bot接收消息时发生错误: {e}", exc_info=True)
                # 可以在这里添加重连逻辑
                await asyncio.sleep(5)
                await self.secondary_bot._connect_and_run()
            finally:
                # 清理回调
                for future in self.secondary_bot.response_callbacks.values():
                    if not future.done():
                        future.cancel()
                self.secondary_bot.response_callbacks.clear()
                self.secondary_bot.receive_task = None

        # 替换副Bot的_receive方法
        self.secondary_bot._receive = forwarding_receive

    def _override_primary_bot_send(self):
        """重写主Bot的send方法，实现发送路由"""
        # 保存原始的send方法
        original_send = self.primary_bot.send

        async def routed_send(event: EventBase, components: list[Union[MessageComponent, str]], Quote: bool = False):
            """路由发送方法：根据群号决定使用哪个Bot发送"""
            # 检查是否为目标群号
            if hasattr(event, 'group_id') and event.group_id == self.target_group_id:
                # 使用副Bot发送
                self.primary_bot.logger.info_msg(f"消息路由到副Bot发送，群号: {event.group_id}")
                return await self._send_via_secondary_bot(event, components, Quote)
            else:
                # 使用主Bot的原始发送逻辑
                return await original_send(event, components, Quote)

        # 替换主Bot的send方法
        self.primary_bot.send = routed_send

    async def _send_via_secondary_bot(self, event: EventBase, components: list[Union[MessageComponent, str]],
                                      Quote: bool = False):
        """通过副Bot发送消息"""
        try:
            # 直接调用副Bot的send方法（如果副Bot也是ExtendBot类型，需要处理适配器逻辑）
            if isinstance(self.secondary_bot, ExtendBot):
                return await WebSocketBot.send(self.secondary_bot, event, components, Quote)
            else:
                return await self.secondary_bot.send(event, components, Quote)
        except Exception as e:
            self.primary_bot.logger.error(f"通过副Bot发送消息失败: {e}", exc_info=True)
            # 发送失败时可以选择回退到主Bot发送
            self.primary_bot.logger.warning("副Bot发送失败，回退到主Bot发送")
            return await self.primary_bot.__class__.__bases__[0].send(self.primary_bot, event, components, Quote)

    async def start_both_bots(self):
        """启动两个Bot"""
        # 创建两个协程任务
        primary_task = asyncio.create_task(self.primary_bot._connect_and_run())
        secondary_task = asyncio.create_task(self.secondary_bot._connect_and_run())

        # 并发运行两个Bot
        try:
            await asyncio.gather(primary_task, secondary_task)
        except Exception as e:
            print(f"运行Bot时发生错误: {e}")
            # 清理任务
            if not primary_task.done():
                primary_task.cancel()
            if not secondary_task.done():
                secondary_task.cancel()
