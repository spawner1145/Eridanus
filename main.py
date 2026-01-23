import concurrent.futures
import importlib
import os
import sys
import asyncio
import threading
import traceback
import logging
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from framework_common.utils.system_logger import get_logger
from framework_common.framework_util.PluginAwareExtendBot import PluginManager, PluginLoadConfig, LoadStrategy
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.framework_util.websocket_fix import ExtendBot
from developTools.adapters.websocket_adapter import WebSocketBot
from framework_common.framework_util.DualBotManager import DualBotManager
from framework_common.framework_util.bot_info import bot_info_collect
from developTools.event.events import GroupMessageEvent, PrivateMessageEvent, LifecycleMetaEvent

# 全局插件管理器实例
plugin_manager = None
bot2 = None
dual_manager = None

config = YAMLManager("run")  # 这玩意用来动态加载和修改配置文件
enable_monitoring = config.common_config.basic_config["HandlerMonitor"]["enable"]
handler_timeout_warning=float(config.common_config.basic_config["HandlerMonitor"]["handler_timeout_warning"])
bot1 = ExtendBot(config.common_config.basic_config["adapter"]["ws_client"]["ws_link"], config,
                 blocked_loggers=["DEBUG", "INFO_MSG"],handler_timeout_warning=handler_timeout_warning, enable_monitoring=enable_monitoring)

bot1.logger.info("正在初始化....")

if config.common_config.basic_config["webui"]["enable"]:
    bot2 = WebSocketBot("ws://127.0.0.1:5007/api/ws")
    bot1.logger.server("🔧 WebUI 服务启动中，请在完全启动后，本机浏览器访问 http://localhost:5007")
    bot1.logger.server("🔧 若您部署的远程主机有公网ip或端口转发功能，请访问对应ip的5007端口，或设置的转发端口。")
    bot1.logger.server("🔧 WebUI 初始账号密码均为 eridanus")
    bot1.logger.server("🔧 WebUI 初始账号密码均为 eridanus")
    bot1.logger.server("🔧 WebUI 初始账号密码均为 eridanus")
    webui_dir = os.path.abspath(os.getcwd() + "/web")
    sys.path.append(webui_dir)


    def run_webui():
        """在子线程中运行 WebUI，隔离模块加载路径"""
        try:
            # 确保 WebUI 模块可以从 webui_dir 加载
            bot1.logger.info(f"WebUI 线程：启动 WebUI，模块路径 {webui_dir}")
            from web.server_new import start_webui
            start_webui()
        except Exception as e:
            bot1.logger.error(f"WebUI 线程：启动 WebUI 失败：{e}")
            traceback.print_exc()


    external_cwd = os.getcwd()
    bot1.logger.info(f"主线程：外部程序运行在 {external_cwd}")

    # 在子线程中启动 WebUI
    webui_thread = threading.Thread(target=run_webui, daemon=True)
    webui_thread.start()
    bot1.logger.info("主线程：WebUI 已启动在子线程中")


async def load_plugins(bot, config, bot_name="main"):
    """使用新的插件管理器加载插件"""
    global plugin_manager

    bot.logger.info(f"🔧 正在使用插件管理器加载插件....")

    try:
        load_strategy_dict = {
            "batch_loading": LoadStrategy.BATCH_LOADING,
            "all_at_once": LoadStrategy.ALL_AT_ONCE,
            "memory_aware": LoadStrategy.MEMORY_AWARE
        }

        load_config = PluginLoadConfig(
            batch_size=config.common_config.basic_config["PluginLoadConfig"]["batch_size"],
            batch_delay=config.common_config.basic_config["PluginLoadConfig"]["batch_delay"],
            max_retries=config.common_config.basic_config["PluginLoadConfig"]["max_retries"],
            retry_delay=config.common_config.basic_config["PluginLoadConfig"]["retry_delay"],
            memory_threshold_mb=config.common_config.basic_config["PluginLoadConfig"]["memory_threshold_mb"],
            enable_gc_between_batches=config.common_config.basic_config["PluginLoadConfig"][
                                          "enable_gc_between_batches"] | True,
            load_strategy=load_strategy_dict.get(config.common_config.basic_config["PluginLoadConfig"]["load_strategy"],
                                                 LoadStrategy.BATCH_LOADING),
        )
        plugin_manager = PluginManager(bot, config, plugins_dir="run", load_config=load_config)

        # 手动重试失败的插件
        await plugin_manager.retry_failed_plugins()


        await plugin_manager.start()

        loaded_plugins = plugin_manager.get_loaded_plugins()
        bot.logger.info(f"🔧 插件加载完成，共加载 {len(loaded_plugins)} 个插件：{', '.join(loaded_plugins)}")

        return plugin_manager

    except Exception as e:
        bot.logger.error(f"🔧 插件管理器启动失败：{e}")
        traceback.print_exc()
        return None


async def handler(bot, event: GroupMessageEvent | PrivateMessageEvent):
    """统一的事件处理器"""
    if event.pure_text == "/reload all":
        await reload_all_plugins()
        await bot.send(event, "插件重载完成")
    elif event.pure_text in ["/status",'/info']:
        status = await get_plugin_status()
        from run.basic_plugin.service.self_condition import self_info_core
        await self_info_core(bot, event, status)
    elif event.pure_text == "/test":
        plugin_memory = plugin_manager.get_plugin_memory_usage("插件名")

        memory_report = plugin_manager.get_memory_usage_report()
        print(memory_report)
        # 手动输出内存报告
        r=plugin_manager.log_memory_report()
        await bot.send(event, r)
""""@bot1.on(LifecycleMetaEvent)
async def handle_lifecycle(event: LifecycleMetaEvent):
    while True:
        r = plugin_manager.get_memory_usage_report()
        memory_occupid=int(r['current_memory']['rss'])
        if memory_occupid>=500:
            await bot1.send_friend_message(config.common_config.basic_config["master"]["id"],"内存占用过高，准备重启...")
            bot1.logger.error("内存占用过高，准备重启...")
            os.execv(sys.executable, ['python'] + sys.argv)
        await asyncio.sleep(600)
"""
async def reload_all_plugins():
    """重载所有插件的便捷函数"""
    if plugin_manager:
        bot1.logger.info("重载主Bot插件...")
        await plugin_manager.reload_all_plugins()



async def get_plugin_status():
    """获取插件状态的便捷函数"""
    status = {}

    if plugin_manager:
        status['main_bot'] = await plugin_manager.get_plugin_status()


    return status


def setup_event_handlers():
    """设置事件处理器 - 只在主Bot上注册，因为副Bot的消息会转发到主Bot"""

    @bot1.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        await handler(bot1, event)

    @bot1.on(PrivateMessageEvent)
    async def handle_private_message(event: PrivateMessageEvent):
        await handler(bot1, event)

    @bot1.on(LifecycleMetaEvent)
    async def handle_lifecycle(event: LifecycleMetaEvent):
        from asyncio import sleep
        await sleep(2)
        await bot1.send_friend_message(
            config.common_config.basic_config["master"]["id"],
            "欢迎使用\n\n群内发送 帮助 可查看命令列表\n\n访问webui请在bot所在设备用浏览器访问\nhttp://localhost:5007"
        )


def main_sync():
    """同步主函数，用于处理事件循环"""
    global dual_manager

    async def async_main():
        """异步主函数"""
        try:
            # 1. 加载主Bot插件
            await load_plugins(bot1, config, "main")
            bot1.logger.info("🚀 主Bot插件管理器启动完成")

            # 2. 设置事件处理器
            setup_event_handlers()

            # 3. 创建双Bot管理器（如果有副Bot）
            if bot2:
                bot2.fix_id=config.common_config.basic_config["master"]["id"]
                dual_manager = DualBotManager(bot1, bot2, target_group_id=879886836)
                bot1.logger.info("🔧 双Bot管理器已创建，开始启动双Bot系统...")
                # 启动双Bot系统
                await dual_manager.start_both_bots()
            else:
                bot1.logger.info("🚀 开始运行单Bot模式...")
                # 只运行主Bot
                await bot1._connect_and_run()

        except Exception as e:
            bot1.logger.error(f"运行错误：{e}")
            traceback.print_exc()

    try:
        # 运行异步主函数
        asyncio.run(bot_info_collect(config.common_config.basic_config["bot"]))
        asyncio.run(async_main())

    except KeyboardInterrupt:
        bot1.logger.info("收到停止信号，正在关闭...")
    except Exception as e:
        bot1.logger.error(f"主程序运行错误：{e}")
        traceback.print_exc()
    finally:
        # 清理资源
        async def cleanup():
            if plugin_manager:
                try:
                    await plugin_manager.stop()
                    bot1.logger.info("主Bot插件管理器已停止")
                except Exception as e:
                    bot1.logger.error(f"停止主Bot插件管理器失败：{e}")


        try:
            asyncio.run(cleanup())
        except Exception as e:
            bot1.logger.error(f"清理过程出错：{e}")


if __name__ == "__main__":
    logger = get_logger("Eridanus")
    main_sync()
