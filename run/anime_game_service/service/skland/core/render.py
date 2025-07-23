from datetime import datetime

from pydantic import AnyUrl as Url
import pprint

from .config import TEMPLATES_DIR, RES_DIR, Building_Dir, career_dir, card_img_dir
from .schemas import ArkCard, RogueData
from .filters import (
    loads_json,
    format_timestamp,
    time_to_next_4am,
    charId_to_avatarUrl,
    format_timestamp_str,
    charId_to_portraitUrl,
    time_to_next_monday_4am,
)
from framework_common.manshuo_draw import *

async def render_ark_card(props ,bg ):
    draw_data ={
            "now_ts": datetime.now().timestamp(),
            "background_image": bg,
            "status": props.status,
            "employed_chars": len(props.chars),
            "skins": len(props.skins),
            "building": props.building,
            "medals": props.medal.total,
            "assist_chars": props.assistChars,
            "recruit_finished": props.recruit_finished,
            "recruit_max": len(props.recruit),
            "recruit_complete_time": props.recruit_complete_time,
            "campaign": props.campaign,
            "routine": props.routine,
            "tower": props.tower,
            "training_char": props.trainee_char,
        }
    #pprint.pprint(draw_data)
    #for char in props.assistChars:print(char.portrait)
    #print(bg)

    img_path=await manshuo_draw(
        [{'type': 'basic_set','img_height':1230,'font_common_color':(255,255,255),'font_title_color':(255,255,255),'font_des_color':(255,255,255),
          'backdrop_color':{'color1':'(80, 80, 80, 255)'},'stroke_layer_color':(130,130,130),'stroke_img_color':(130,130,130)},
         {'type': 'backdrop', 'subtype': 'gradient','left_color': (5,22,29),'right_color': (84,89,88)},
         {'type': 'avatar', 'img': [props.status.avatar.url],'upshift_extra': 20,'background':[bg],
         'content': [f"[name]{props.status.name}[/name] [time]lv:{props.status.level} [/time]\n"
                     f"[time]id:{props.status.uid} 入职日:{props.status.register_time} [/time]"]},
         {'type': 'img', 'subtype': 'common_with_des', 'number_per_row': 5,
         'is_shadow_img': False, 'description_color': (52, 52, 52, 255),
         'img': [(career_dir / 'career_1.png').as_posix(),(career_dir / 'career_2.png').as_posix(),
                 (career_dir / 'career_3.png').as_posix(),(career_dir / 'career_4.png').as_posix(),
                 (career_dir / 'career_5.png').as_posix(),],
         'content': [f'作战进度\n{props.status.mainStageProgress}',f'雇佣干员\n{len(props.chars)}',
                     f'时装数量\n{len(props.skins)}',f'家具保有\n{props.building.furniture.total}',
                     f'蚀刻章\n{props.medal.total}',]},
        '   ',{'type': 'text', 'content': ['[title]助战干员[/title]'],'layer':2},
        {'type':'img','is_crop':False,'img':[char.portrait for char in props.assistChars],'layer':2,
         'is_stroke_img':False, 'is_shadow_img':False, 'is_rounded_corners_img': False, 'number_per_row': 3},
        {'type': 'text', 'content': ['[title]基建信息[/title]'],'layer':2},
        {'type': 'img', 'subtype': 'common_with_des_right', 'number_per_row': 2,'layer': 2,
         'is_shadow_img':False,'magnification_img':8,'padding': 11,
         'description_color': (52, 52, 52, 255),
         'img': [(Building_Dir / 'labor.png').as_posix(),(Building_Dir / 'dorm.png').as_posix(),
                 (Building_Dir / 'trading.png').as_posix(), (Building_Dir / 'manufact.png').as_posix(),
                 (Building_Dir / 'tired.png').as_posix(),(Building_Dir / 'meeting.png').as_posix(),],
         'content':[f'无人机：{props.building.labor.labor_now} / {props.building.labor.maxValue}',
                    f'休息进度:{props.building.rested_chars} / {props.building.dorm_chars}',
                    f'订单进度:{props.building.trading_stock} / {props.building.trading_stock_limit}',
                    f'制造进度:{props.building.manufacture_stoke.current} / {props.building.manufacture_stoke.total}',
                    f'干员疲劳:{len(props.building.tiredChars) }',
                    f'线索交流:{len(props.building.meeting.clue.board) } / 7',]},
         '   ',
         {'type': 'img', 'subtype': 'common_with_des_right', 'number_per_row': 3,
          'is_shadow_img': False, 'description_color': (52, 52, 52, 255),
          'img': [(card_img_dir / 'ap.png').as_posix(), (card_img_dir / 'recruit.png').as_posix(),
                  (card_img_dir / 'hire.png').as_posix(), (card_img_dir / 'jade.png').as_posix(),
                  (card_img_dir / 'daily.png').as_posix(),(card_img_dir / 'weekly.png').as_posix(),
                  (card_img_dir / 'tower.png').as_posix(),(card_img_dir / 'tower.png').as_posix(),
                  (card_img_dir / 'train.png').as_posix(),],
          'content': [f'理智\n{props.status.ap.ap_now} / {props.status.ap.max}',
                      f'公开招募\n{props.recruit_finished} / {len(props.recruit)}',
                      f'公招刷新\n{props.building.hire.refreshCount} / 3',
                      f'剿灭奖励\n{props.campaign.reward.current} / {props.campaign.reward.total}',
                      f'每日任务\n{props.routine.daily.current} / {props.routine.daily.total}',
                      f'每周任务\n{props.routine.weekly.current} / {props.routine.weekly.total}',
                      f'数据增补仪\n{props.tower.reward.higherItem.current} / {props.tower.reward.higherItem.total}',
                      f'数据增补条\n{props.tower.reward.lowerItem.current} / {props.tower.reward.lowerItem.total}',
                      f'训练室\n{props.trainee_char}   {props.building.training.training_state}',
                      ]},
         '[des]                                             Function By 漫朔[/des]'
    ])
    return img_path


async def render_rogue_card(props: RogueData, bg: str | Url) -> bytes:
    draw_data ={
            "background_image": bg,
            "topic_img": props.topic_img,
            "topic": props.topic,
            "now_ts": datetime.now().timestamp(),
            "career": props.career,
            "game_user_info": props.gameUserInfo,
            "history": props.history,
        }
    pprint.pprint(draw_data)

    rogue_favour_info, index=['    ',{'type': 'text', 'content': ['[title]收藏战绩[/title]'], 'layer': 2}], 0
    for record in props.history.favourRecords:
        if record.success:status = '胜利'
        else:status = '失败'
        index += 1
        per_rogue_info=[{'type': 'text', 'content': [f'[title]{record.mode} - {record.modeGrade}            {status}[/title]'
                                                     f'\n得分：{record.score}     {record.lastStage}'], 'layer': 3},
                        {'type': 'img', 'number_per_row': 8, 'layer': 3,'is_shadow_img': False,'img': [ charId_to_avatarUrl(char.id) for char in record.lastChars],},
                        {'type': 'text',
                         'content': [f'id：{index}     {format_timestamp_str(record.endTs)}'], 'layer': 3},
                        ]
        if index == 1:rogue_favour_info = rogue_favour_info + per_rogue_info
        else:rogue_favour_info = rogue_favour_info + [{'type': 'text', 'content': ['  '], 'layer': 2}] + per_rogue_info
    if index == 0:rogue_favour_info += [{'type': 'text', 'content': ['本人好像没有收藏过任何战绩喵～'], 'layer': 2}]

    rogue_history_info, index=['    ',{'type': 'text', 'content': ['[title]最近战绩[/title]'], 'layer': 2}], 0
    for record in props.history.records:
        if record.success:status = '胜利'
        else:status = '失败'
        index += 1
        per_rogue_info=[{'type': 'text', 'content': [f'[title]{record.mode} - {record.modeGrade}            {status}[/title]'
                                                     f'\n得分：{record.score}     {record.lastStage}'], 'layer': 3},
                        {'type': 'img', 'number_per_row': 8, 'layer': 3,'is_shadow_img': False,'img': [ charId_to_avatarUrl(char.id) for char in record.lastChars],},
                        {'type': 'text',
                         'content': [f'id：{index}     {format_timestamp_str(record.endTs)}'], 'layer': 3},
                        ]
        print(per_rogue_info)
        if index == 1:rogue_history_info = rogue_history_info + per_rogue_info
        else:rogue_history_info = rogue_history_info + [{'type': 'text', 'content': ['  '], 'layer': 2}] + per_rogue_info


    draw_json=[
        {'type': 'basic_set','debug':True ,'img_height':2000,'font_common_color':(255,255,255),'font_title_color':(255,255,255),'font_des_color':(255,255,255),
          'backdrop_color':{'color1':'(80, 80, 80, 255)'},'stroke_layer_color':(130,130,130),'stroke_img_color':(130,130,130)},
        {'type': 'backdrop', 'subtype': 'gradient','left_color': (5,22,29),'right_color': (84,89,88)},
        {'type': 'avatar', 'img': [props.gameUserInfo.avatar.url],'upshift_extra': 20,'background':[bg],
         'content': [f"[name]{props.gameUserInfo.name}[/name] \n[time]lv:{props.gameUserInfo.level} [/time]"]},
         f'[title]最高成就：{props.history.mode} - {props.history.modeGrade}（难度）\n等级：Lv.{props.history.bpLevel}\n得分:{props.history.score}[/title]',
        {'type': 'text', 'content': ['[title]常用干员[/title]'], 'layer': 2},
        {'type': 'img', 'is_crop': False, 'img': [charId_to_portraitUrl(char.id) for char in props.history.chars], 'layer': 2,
          'is_stroke_img': False, 'is_shadow_img': False, 'is_rounded_corners_img': False, 'number_per_row': 3},



    ]
    draw_json = draw_json + rogue_favour_info + rogue_history_info

    draw_json+=['[des]                                             Function By 漫朔[/des]']
    img_path=await manshuo_draw(draw_json)
    return img_path


async def render_rogue_info(props: RogueData, bg: str | Url, id: int, is_favored: bool) -> bytes:
    return await template_to_pic(
        template_path=str(TEMPLATES_DIR),
        template_name="rogue_info.html.jinja2",
        templates={
            "id": id,
            "record": props.history.favourRecords[id - 1]
            if is_favored and id - 1 < len(props.history.favourRecords)
            else (props.history.records[id - 1] if id - 1 < len(props.history.records) else None),
            "is_favored": is_favored,
            "background_image": bg,
            "topic_img": props.topic_img,
            "topic": props.topic,
            "now_ts": datetime.now().timestamp(),
            "career": props.career,
            "game_user_info": props.gameUserInfo,
            "history": props.history,
        },
        filters={
            "format_timestamp_str": format_timestamp_str,
            "charId_to_avatarUrl": charId_to_avatarUrl,
            "charId_to_portraitUrl": charId_to_portraitUrl,
            "loads_json": loads_json,
        },
        pages={
            "viewport": {"width": 1100, "height": 1},
            "base_url": f"file://{TEMPLATES_DIR}",
        },
        device_scale_factor=1.5,
    )
