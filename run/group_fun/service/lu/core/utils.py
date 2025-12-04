import asyncio
import random

lock_message_select = [' 人家上了贞操锁哦', ' 就你还想碰人家，哼！', ' 滚开啊，变态！', ' 杂鱼杂鱼', ' 杂鱼，你抓不到我', ' 来找我呀，笨蛋']
message_select = [' 都tmd炸膛了！', ' 还lu还lu！都炸膛了!', ' 燃尽了喵', ' lu不下去了', ' 精尽人亡.jpg', ]
lu_list = {}
#lu的时间检查
async def lu_cool(userid,day_info,times=1):
    time_check = day_info['time']
    global lu_list
    #True代表允许，False代表不允许
    return_json = {'status':True, 'message':' 贤者时间ing', 'lu_list':lu_list}
    #不在队列里则添加
    if userid not in lu_list:
        lu_list[userid] = {'time':time_check ,'times':times, 'boom':False, 'boom_time':0}
        return return_json
    else:
        #若有炸膛时间则优先判断
        if lu_list[userid]['boom']:
            if time_check - lu_list[userid]['time'] > lu_list[userid]['boom_time']:
                lu_list[userid]['boom'] = False
                return return_json
            return_json['status'] = False
            boom_time_left = lu_list[userid]['boom_time'] - (time_check - lu_list[userid]['time'])
            return_json['message'] = random.choice(message_select) + f"，冷却还剩 {boom_time_left} s"
            return return_json
        #时间小于5s则会直接贤者时间
        if time_check - lu_list[userid]['time'] < 5:
            return_json['status'] = False
            return return_json
        #不是贤者时间则查看是否炸膛（笑
        #炸膛是时间小于1h才会开始计算的
        lu_list[userid]['time'] = time_check
        if time_check - lu_list[userid]['time'] >= 3600:
            lu_list[userid]['times'] = times
            return return_json
        #次数小于5的时候不会炸膛
        lu_list[userid]['times'] += times
        if lu_list[userid]['times'] < 5:
            return return_json
        #炸膛概率随次数逐渐提高
        if lu_list[userid]['times'] < 5: boom_chance = lu_list[userid]['times'] * 10
        elif 5 <= lu_list[userid]['times'] < 10: boom_chance = (lu_list[userid]['times'] - 5) * 5 + 50
        elif 10 <= lu_list[userid]['times'] < 15: boom_chance = (lu_list[userid]['times'] - 10) * 3 + 75
        elif 15 <= lu_list[userid]['times'] < 20: boom_chance = (lu_list[userid]['times'] - 15) * 2 + 90
        else:boom_chance = 300
        if random.randint(0, boom_chance) > 60:
            boom_time = random.randint(0, times*5)
            if boom_time > 600: boom_time = 600
            return_json['status'] = False
            lu_list[userid]['boom'] = True
            return_json['message'] = random.choice(message_select) + f'，冷却 {boom_time} s'
        return return_json