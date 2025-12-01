from developTools.message.message_components import Text, Image, At
from framework_common.manshuo_draw import *

async def help_menu(bot=None,event=None):
    if bot and event:self_id = event.self_id
    else:self_id = 1270858640
    draw_json = [
        {'type': 'basic_set', 'img_name_save': 'mihuyo_club_help.png'},
        {'type': 'avatar', 'subtype': 'common', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk={self_id}&s=640"],
         'upshift_extra': 15,
         'content': [f"[name]米游社帮助菜单[/name]\n[time]米游姬驾到～[/time]"]},
        '[title]指令菜单：[/title]'
        '\n- 绑定米游社账号：mihuyobind, 米游社绑定、米游社登录'
        '\n- 米家游戏签到：崩铁签到、崩三签到、原神签到、绝区零签到、崩2签到、未定签到（部分别名也可'
        '\n- 米游社签到：mihuyosign, 米游社签到\n（此为所有游戏一次性全部签到，耗时较长）\n'
        '\n- 更改默认签到游戏：mysgamechange + 游戏 eg：mysgamechange 原神\n'
        '等待开发，欢迎催更（咕咕咕\n'
        '[des]                                             Function By 漫朔[/des]'
    ]
    img_path = await manshuo_draw(draw_json)
    if bot and event:
        await bot.send(event, Image(file=(img_path)))
    else:
        print(img_path)



