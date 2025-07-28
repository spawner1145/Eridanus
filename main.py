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
from framework_common.framework_util.PluginAwareExtendBot import PluginManager

from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.framework_util.websocket_fix import ExtendBot


# 全局插件管理器实例
plugin_manager1 = None
plugin_manager2 = None
bot2 = None
config = YAMLManager("run")  # 这玩意用来动态加载和修改配置文件
bot1 = ExtendBot(config.common_config.basic_config["adapter"]["ws_client"]["ws_link"], config,
                 blocked_loggers=["DEBUG", "INFO_MSG"])

bot1.logger.info("正在初始化....")
if config.common_config.basic_config["webui"]["enable"]:
    bot2 = ExtendBot("ws://127.0.0.1:5007/api/ws", config, blocked_loggers=["DEBUG", "INFO_MSG", "warning"])
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
    global plugin_manager1, plugin_manager2

    bot.logger.info(f"🔧 正在使用插件管理器加载插件....")

    try:

        plugin_manager = PluginManager(bot, config, plugins_dir="run")

        if bot_name == "main":
            plugin_manager1 = plugin_manager
        else:
            plugin_manager2 = plugin_manager

        await plugin_manager.start()

        loaded_plugins = plugin_manager.get_loaded_plugins()
        bot.logger.info(f"🔧 插件加载完成，共加载 {len(loaded_plugins)} 个插件：{', '.join(loaded_plugins)}")

        return plugin_manager

    except Exception as e:
        bot.logger.error(f"🔧 插件管理器启动失败：{e}")
        traceback.print_exc()
        return None


def webui_bot():
    config_copy = YAMLManager("run")  # 这玩意用来动态加载和修改配置文件

    def config_fix(config_copy):
        config_copy.resource_collector.config["JMComic"]["anti_nsfw"] = "no_censor"
        config_copy.resource_collector.config["asmr"]["gray_layer"] = False
        config_copy.basic_plugin.config["setu"]["gray_layer"] = False
        config_copy.resource_collector.config["iwara"]["iwara_gray_layer"] = False
        config_copy.ai_llm.config["llm"]["读取群聊上下文"] = False
        config_copy.resource_collector.config["iwara"]["zip_file"] = False
        config_copy.common_config.basic_config["master"]["id"] = 111111111

    def run_bot2():
        """在独立线程运行 bot2"""
        try:
            config_fix(config_copy)
            async def setup_bot2():
                await load_plugins(bot2, config_copy, "webui")

            asyncio.run(setup_bot2())

            # 然后运行bot2（bot.run()会创建自己的事件循环）
            bot2.run()

        except Exception as e:
            bot1.logger.error(f"Bot2 线程运行失败：{e}")
            traceback.print_exc()

    bot2_thread = threading.Thread(target=run_bot2, daemon=True)
    bot2_thread.start()


def main_sync():
    """同步主函数，用于处理事件循环"""

    async def async_setup():
        """异步设置函数"""
        try:
            if config.common_config.basic_config["webui"]["enable"]:
                webui_bot()

            await load_plugins(bot1, config, "main")
            bot1.logger.info("🚀 主Bot插件管理器启动完成，开始运行Bot...")

        except Exception as e:
            bot1.logger.error(f"插件加载错误：{e}")
            traceback.print_exc()

    try:
        asyncio.run(async_setup())

        bot1.run()

    except KeyboardInterrupt:
        bot1.logger.info("收到停止信号，正在关闭...")
    except Exception as e:
        bot1.logger.error(f"主程序运行错误：{e}")
        traceback.print_exc()
    finally:
        async def cleanup():
            if plugin_manager1:
                try:
                    await plugin_manager1.stop()
                    bot1.logger.info("主Bot插件管理器已停止")
                except Exception as e:
                    bot1.logger.error(f"停止主Bot插件管理器失败：{e}")

            if plugin_manager2:
                try:
                    await plugin_manager2.stop()
                    bot1.logger.info("WebUI Bot插件管理器已停止")
                except Exception as e:
                    bot1.logger.error(f"停止WebUI Bot插件管理器失败：{e}")

        try:
            asyncio.run(cleanup())
        except Exception as e:
            bot1.logger.error(f"清理过程出错：{e}")

from developTools.event.events import GroupMessageEvent,PrivateMessageEvent
if bot2:
    @bot2.on(GroupMessageEvent)
    async def _(event: GroupMessageEvent):
        await handler(bot2,event)
    @bot2.on(PrivateMessageEvent)
    async def _(event: PrivateMessageEvent):
        await handler(bot2,event)
@bot1.on(GroupMessageEvent)
async def _(event: GroupMessageEvent):
    await handler(bot1,event)
@bot1.on(PrivateMessageEvent)
async def _(event: PrivateMessageEvent):
    await handler(bot1,event)

async def handler(bot,event: GroupMessageEvent | PrivateMessageEvent):
    if event.pure_text=="/reload all":
        await reload_all_plugins()
        await bot.send(event, "插件重载完成")
    elif event.pure_text=="/status":
        status = await get_plugin_status()
        print(status)
    elif event.pure_text=="/test":
        print(config.ai_llm.config["test"])

# 添加一些管理命令（可选）
async def reload_all_plugins():
    """重载所有插件的便捷函数"""
    if plugin_manager1:
        bot1.logger.info("重载主Bot插件...")
        await plugin_manager1.reload_all_plugins()

    if plugin_manager2:
        bot1.logger.info("重载WebUI Bot插件...")
        await plugin_manager2.reload_all_plugins()


async def get_plugin_status():
    """获取插件状态的便捷函数"""
    status = {}

    if plugin_manager1:
        status['main_bot'] = await plugin_manager1.get_plugin_status()

    if plugin_manager2:
        status['webui_bot'] = await plugin_manager2.get_plugin_status()

    return status


if __name__ == "__main__":
    logger=get_logger("Eridanus")
    main_sync()