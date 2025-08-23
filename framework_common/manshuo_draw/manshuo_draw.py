from concurrent.futures.thread import ThreadPoolExecutor

from framework_common.manshuo_draw.core.deal_img import *
import asyncio


async def manshuo_draw(json_img):
    json_img = json_check(json_img)
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        img_path = await loop.run_in_executor(executor, lambda: asyncio.run(deal_img(json_img)))

    del json_img
    # analyze_objects("1")
    return img_path

if __name__ == '__main__':

    contents=[
        {'type': 'basic_set', 'debug': True},

        {'type': 'backdrop', 'subtype': 'gradient'},

        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],'upshift_extra':25,
         'content':[ f"[name]今日发言排行榜[/name]\n[time]2025年 05月27日 20:32[/time]"] },
        '1234341fdsgsdfvbs',
        {'type': 'img', 'subtype': 'common_with_des_right', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],
         'content': ['这里是manshuo[title]！这部分是测manshuo！[/title]这manshuo！[des]这里是介绍[/des]'],'layer':4, },
        {'type': 'math', 'subtype': 'bar_chart', 'content': [0.2, 0.6, 0.3, 0.8], },
        {'type': 'math', 'subtype': 'bar_chart_vertical','content': [[0.2,0.6,0.3,0.8,0.2,0.6,0.3,0.8,0.2,0.6,0.3,0.8,]], 'x_des':[[1,2,3,4,5,1,2,3,4,5,1,2,3,4,5,]]},
    ]

    contents2=[
        {'type': 'basic_set', 'debug': False,'img_width':1500,'img_height':1000,},

        {'type': 'backdrop', 'subtype': 'img'},

        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],'upshift_extra':25,'layer':1,
         'content':[ f"[name]今日发言排行榜[/name]\n[time]2025年 05月27日 20:32[/time]"] },
        {'type': 'img', 'subtype': 'common_with_des_right', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg',
                                                        f"https://q1.qlogo.cn/g?b=qq&nk=1280433782&s=640",
                                                        f"https://q1.qlogo.cn/g?b=qq&nk=3552663628&s=640",
                                                        f"https://q1.qlogo.cn/g?b=qq&nk=2702495766&s=640",
                                                        f"https://q1.qlogo.cn/g?b=qq&nk=1687148274&s=640",
                                                        f"https://q1.qlogo.cn/g?b=qq&nk=1124901768&s=640",
                                                        f"https://q1.qlogo.cn/g?b=qq&nk=2319804644&s=640"],
         'content': [f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     f"[title]漫朔_manshuo[/title]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！",
                     ], 'number_per_row': 2,
         },
        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg',f"https://q1.qlogo.cn/g?b=qq&nk=1280433782&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=3552663628&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=2702495766&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=1687148274&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=1124901768&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=2319804644&s=640"],
         'content': [f"[name]漫朔_manshuo[/name]\n[time]发言次数：230次[/time]","[name]荔枝[/name]\n[time]发言次数：215次[/time]","[name]test[/name]\n[time]发言次数：205次[/time]","[name]荔枝[/name]\n[time]发言次数：215次[/time]","[name]荔枝[/name]\n[time]发言次数：215次[/time]","[name]荔枝[/name]\n[time]发言次数：215次[/time]","[name]荔枝[/name]\n[time]发言次数：215次[/time]","[name]荔枝[/name]\n[time]发言次数：215次[/time]"],'number_per_row':2,
         'background':['framework_common/manshuo_draw/data/cache/manshuo.jpg',f"https://q1.qlogo.cn/g?b=qq&nk=1280433782&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=3552663628&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=2702495766&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=1687148274&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=1124901768&s=640",f"https://q1.qlogo.cn/g?b=qq&nk=2319804644&s=640"],
         },
    ]

    contentsWithNoTag=[
        {'type': 'basic_set', 'debug': False,'img_width':1000,'img_height':980,'max_num_of_columns':4},
        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],'layer':1,
         'content': [f"[name]漫朔_manshuo[/name]\n[time]2025年 05月27日 20:32[/time]"]},
        '这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]',
        ['framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg',
         'framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg',
         'framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg',],
        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],
         'content': [f"[name]漫朔_manshuo[/name]\n[time]2025年 05月27日 20:32[/time]"]},
        ['framework_common/manshuo_draw/data/cache/manshuo.jpg', 'framework_common/manshuo_draw/data/cache/manshuo.jpg',
         'framework_common/manshuo_draw/data/cache/manshuo.jpg', ],
        '这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]',
        {'type': 'img', 'subtype': 'common_with_des_right','img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],'label':['BiliBili'],'layer':2,
         'content': ['这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]']},
        {'type': 'img', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg','framework_common/manshuo_draw/data/cache/manshuo.jpg'],'layer':3,
         'content': ['葬送的芙莉莲\n5星','败犬女主太多啦\n4.5星',]
         },
        '这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]',
        {'type': 'img', 'subtype': 'common_with_des','img': ['https://gal.manshuo.ink/usr/uploads/2025/02/1709218403.png'], 'label': ['BiliBili'],'layer':5,
         'content': ['这部分是测manshuo！\n这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n[des]这里是介绍[/des]']},
    ]

    games_content=[{'type': 'basic_set', 'debug': False},
        {'type': 'avatar', 'subtype': 'common', 'img': ['https://i0.hdslb.com/bfs/face/035c2c9e95c5487d0a9aca28c36f0cb20b0afc3f.jpg'],
                    'upshift_extra': 20, 'content': ['[name]一颗小兔娘[/name]\n[time]2025年07月20日 19:22[/time]'], 'type_software': 'bilibili'},
                   {'type': 'text', 'content': ['都怪你们不给力，害得爱播赚不了这份钱[emoji]https://i0.hdslb.com/bfs/emote/ca94ad1c7e6dac895eb5b33b7836b634c614d1c0.png[/emoji]'
                                                '[emoji]https://i0.hdslb.com/bfs/emote/ca94ad1c7e6dac895eb5b33b7836b634c614d1c0.png[/emoji]'
                                                '[emoji]https://i0.hdslb.com/bfs/emote/ca94ad1c7e6dac895eb5b33b7836b634c614d1c0.png[/emoji]']},
                   {'type': 'img', 'img': ['http://i0.hdslb.com/bfs/new_dyn/9cd316e9b7f15b48cc12383fc1e446b5498099165.jpg']}]

    text_content=[{'type': 'basic_set', 'debug': False,'img_width':500,'img_height':1000,'auto_line_change':False},
        '这部分是测manshuo！\n'
        '这manshuo！这里是测试！这里是测试！这里是测试！这里是测试！这里是测试！'
        '这里是测试！这里是测试！这里是测试！这里是测试！这里是测试\n'
        '[des]这里是介绍[/des]']


    asyncio.run(manshuo_draw(contents))

