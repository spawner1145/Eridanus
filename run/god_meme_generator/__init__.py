from .god_meme_generator import register_handlers

plugin_description = "一个表情包生成插件。用户可以通过命令指定QQ号、名称、评论等参数，生成一个带有QQ头像和自定义文本的“神之表情包”。"

def main(bot, conf):
    register_handlers(bot, conf)

entrance_func = main
