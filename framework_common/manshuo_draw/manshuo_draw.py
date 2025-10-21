from framework_common.manshuo_draw.core import *
import asyncio


async def manshuo_draw(json_img):
    json_img = json_check(json_img)
    img_path = await asyncio.to_thread(
        lambda: asyncio.run(deal_img(json_img))
    )

    del json_img
    return img_path

async def test():
    draw_json = await menu_maker()

    img_path = await manshuo_draw(draw_json['page1'])
    print(img_path)

if __name__ == '__main__':

    contents=[
        {'type': 'basic_set', 'debug': True},
        {'type': 'backdrop', 'subtype': 'gradient'},
        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],'upshift_extra':25,
         'content':[ f"[name]今日发言排行榜[/name]\n[time]2025年 05月27日 20:32[/time]"] },
        {'type': 'img', 'subtype': 'common_with_des_right', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],
         'content': ['这里是manshuo[title]！这部分是测manshuo！[/title]这manshuo！[des]这里是介绍[/des]'],'layer':4, },
        {'type': 'math', 'subtype': 'bar_chart', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg',],'number_per_row':1,'chart_height':75,
         'content': [0.2, 0.6, 0.3], },
        {'type': 'math', 'subtype': 'bar_chart_vertical','content': [[0.2,0.6,0.3,0.8,0.2,0.6,0.3,0.8,0.2,0.6,0.3,0.8,]], 'x_des':[[1,2,3,4,5,1,2,3,4,5,1,2,3,4,5,]]},
    ]

    contents2=[
        {'type': 'basic_set', 'debug': False,'img_width':1500,'img_height':1000,},
        {'type': 'avatar', 'subtype': 'common', 'img': ['framework_common/manshuo_draw/data/cache/manshuo.jpg'],'upshift_extra':25,'layer':1,
         'content':[ f"[name]今日发言排行榜[/name]\n[time]2025年 05月27日 20:32[/time]"] },
        {'type': 'img', 'subtype': 'common_with_des_right', 'img': [f"https://q1.qlogo.cn/g?b=qq&nk=1280433782&s=640",],
         'content': [f"[title]漫朔_manshuo[/title]这部分是测manshuo！"], 'number_per_row': 2},
    ]





    #asyncio.run(manshuo_draw(contents))
    asyncio.run(test())