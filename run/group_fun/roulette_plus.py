import random
import asyncio
from typing import List, Dict, Any, Optional
import traceback

from developTools.event.events import GroupMessageEvent
from framework_common.utils.utils import delay_recall
from developTools.message.message_components import Node, Text, Image, At

START_GAME_ANNOUNCEMENTS = [
    "寂静的房间里，左轮手枪被重重地拍在冰冷的铁桌上。一场赌上生死的决斗，由 {nickname} 发起。规则已定，敢来赴死者，请坐到桌前。",
    "空气中弥漫着威士忌和硝烟的味道。赌局已开，这是命运的邀请函，由 {nickname} 亲手递上。想活到最后？那就加入我们，用你的生命做筹码。",
    "心跳声，呼吸声，都在这一刻变得清晰可闻。轮盘赌的号角已经吹响，由 {nickname} 开启。欢迎来到这场狩猎游戏，你是猎人，还是猎物？",
]

JOIN_GAME_MESSAGES = [
    "脚步声响起，{player_nickname} 沉默地在桌前落座。他的眼神像刀锋一样锐利。",
    "又一个名字被写在了名单上，{player_nickname} 已经加入。气氛愈发凝重，没人知道下一个倒下的是谁。",
    "{player_nickname} 推开了门，加入了这场死亡之舞。他的手中，似乎握着不为人知的秘密。",
]

TURN_START_MESSAGES = [
    "{player_nickname}，轮到你了。枪口对准了你，或者你的敌人。选择吧，这是你最后的自由。",
    "那沉甸甸的左轮手枪，此刻正握在 {player_nickname} 的手中。它的重量，是你无法逃避的责任。做出你的决定。",
    "砰，砰……你听到了自己的心跳声吗，{player_nickname}？现在，该你扣动扳机了。是开枪，还是使用工具？",
    "所有人的目光都像针一样扎在你的身上，{player_nickname}。手枪被推到了你面前，请拿起它。你的回合开始了。",
]

MISS_SHOT_MESSAGES = [
    "咔哒……一声空响。枪膛空空如也，命运嘲弄般地放过了这一次。空气中的紧张感瞬间凝固。",
    "扳机被扣动，但只有一声无力的金属撞击声。子弹擦肩而过，你听到了一阵劫后余生的喘息。",
    "枪口没有喷出火焰，子弹并未就位。空枪！你感觉自己像从鬼门关走了一遭。",
    "轮盘转动，但子弹没有落入击发位置。命运的齿轮这次没有碾碎任何人。",
]

LIVE_SHOT_MESSAGES = [
    "轰！枪声震耳欲聋，硝烟弥漫！子弹如脱缰的野马，狠狠地贯穿了 {target_nickname}！",
    "砰！枪口喷出火舌，子弹撕裂了空气，精确地击中了 {target_nickname}！",
    "一声闷响！命运的铁锤落下，子弹无情地击中了 {target_nickname}。",
    "你的手没有丝毫颤抖，扳机被扣下，子弹毫不留情地命中了 {target_nickname}！",
]

SAW_MESSAGES = [
    "你掏出那把满是锈迹的短锯，用它粗暴地切割着枪管。锯齿摩擦的声音令人牙酸，但你下一枪的威胁，也随之倍增！",
    "你拿起短锯，眼神坚定地锯向枪口。这把枪变得更加致命，但代价是它的稳定性。下一枪，伤害加成已就位！",
]

MAGNIFYING_GLASS_MESSAGES = {
    "live": [
        "你举起放大镜，透过它观察着枪膛。你看到了弹巢里的秘密，一枚子弹静静地躺在那里。你已经看清了真相。",
        "放大镜闪烁着微光，你借着它窥探了命运的轮盘。你看到了子弹就在击发位置。这局棋，你已经领先一步。",
    ],
    "miss": [
        "你举起放大镜，透过它观察着枪膛。空无一物... 枪膛是空的，你可以安心地对自己射出这一枪了。",
        "放大镜闪烁着微光，你借着它窥探了命运的轮盘。子弹没有就位，这是一个空弹仓。",
    ]
}

DRINK_MESSAGES = [
    "你拧开一瓶冰冷的饮料，大口灌下。液体顺着喉咙流下，你感觉一股暖流涌入身体，伤痕正在愈合。生命值+1！",
    "你喝下了那瓶来历不明的饮料。一股奇异的力量涌入你的身体，你的生命力恢复了一点。这东西... 值得吗？",
]

GAME_END_MESSAGES = [
    "枪声终于停歇，硝烟渐渐散去。在血与火的洗礼后，只有 {winner_nickname} 站立着，他是最后的幸存者！",
    "尘埃落定。这场以生命为代价的赌局，最终由 {winner_nickname} 赢得了胜利。赌桌空了，只剩下他一人。",
    "恭喜 {winner_nickname}，你活到了最后。这场残酷的狩猎游戏，以你的胜利画上句号。现在，你可以离开了。",
]

RELOAD_MESSAGES = [
    "冰冷的左轮手枪被重重地放在桌上，沉甸甸的。弹巢被打开，一枚锃亮的子弹被重新推入其中，它在六个弹孔中随意地滚动，最终停在了你的命运之位。弹巢被合上，然后被轻轻一转。新的一局，开始了。",
    "枪声的余音还在耳边回响，但命运的齿轮再次转动。新的弹巢，新的机会，也可能是新的终结。子弹已就位，只等你的指令。你感觉到那份冰冷的重量，它像一块冰冷的石头压在你的心上。",
    "你闭上眼，深吸一口气，试图忘记刚才的血腥。一把左轮手枪被推到你面前，弹巢里只装了一颗子弹。这就是规则。准备好了吗？游戏从这一刻重新开始。",
    "死亡的阴影刚刚散去，但新的挑战已经到来。弹巢重新上满子弹并转动，发出机械的咔嗒声。这一次，你的运气还会像之前一样好吗？",
]

REVIVE_MESSAGES = [
    "{player_nickname} 在倒下的一瞬间，猛地灌下了剩下的所有饮料！一股神秘的力量涌入他的体内，伤口以肉眼可见的速度愈合，他重重地喘息着，竟奇迹般地站了起来！他回到了赌局，生命值恢复到 1！",
    "死亡的边缘，{player_nickname} 凭借着手中最后几瓶饮料，硬生生地把自己从鬼门关拉了回来！咕咚咕咚... 饮料见底，他的生命之火重新燃起，虽然只剩 1 点生命值，但他还在！",
    "没有人想到，{player_nickname} 居然还有这种底牌！在致命的打击下，他将所有饮料一饮而尽，生命如同被强行续上了弦！虽然代价是所有的饮料，但他的身影再次出现在赌桌旁，苟延残喘的生命值回到了 1。",
]


game_session: Dict[str, Any] = {
    "is_active": False,
    "admin": None,
    "players": {},
    "current_turn": None,
    "bullet_chamber": [],
    "total_shots_fired": 0,
    "total_chambers": 0,
    "current_round": 0,
    "tools_available": ["短锯", "放大镜", "饮料"],
    "waiting_for_action": False,
    "turn_order": [],
    "current_turn_index": -1,
}

TOOL_EFFECTS = {
    "短锯": "这发子弹伤害+1",
    "放大镜": "查看当前弹仓是否有子弹",
    "饮料": "加1点生命值",
}

def main(bot, config):
    def parse_game_params(text: str) -> Dict[str, int]:
        params = {
            "hp": 1,
            "bullets": 1,
            "chamber_size": 6,
            "tool_count": 0,
        }
        
        parts = text.split(" ")
        for i, part in enumerate(parts):
            if part == "--hp" and i + 1 < len(parts):
                try:
                    params["hp"] = int(parts[i+1])
                except ValueError:
                    bot.logger.warning(f"无效的--hp参数: {parts[i+1]}，使用默认值")
            elif part == "--b" and i + 1 < len(parts):
                try:
                    params["bullets"] = int(parts[i+1])
                except ValueError:
                    bot.logger.warning(f"无效的--b参数: {parts[i+1]}，使用默认值")
            elif part == "--all" and i + 1 < len(parts):
                try:
                    params["chamber_size"] = int(parts[i+1])
                except ValueError:
                    bot.logger.warning(f"无效的--all参数: {parts[i+1]}，使用默认值")
            elif part == "--tool" and i + 1 < len(parts):
                try:
                    params["tool_count"] = int(parts[i+1])
                except ValueError:
                    bot.logger.warning(f"无效的--tool参数: {parts[i+1]}，使用默认值")
        
        if params["bullets"] > params["chamber_size"]:
            raise ValueError("子弹数不能大于弹仓数")
            
        return params

    def init_game(admin_id: int, admin_nickname: str, params: Dict[str, int]):
        reset_game_session()
        game_session["is_active"] = True
        game_session["admin"] = {"id": admin_id, "nickname": admin_nickname}
        
        player_tools = [random.choice(game_session["tools_available"]) for _ in range(min(params["tool_count"], len(game_session["tools_available"]) * 5))]

        game_session["players"][admin_id] = {
            "nickname": admin_nickname,
            "hp": params["hp"],
            "tools": player_tools,
            "is_alive": True,
            "shot_damage_bonus": 0,
        }
        game_session["initial_hp"] = params["hp"]
        game_session["initial_bullets"] = params["bullets"]
        game_session["chamber_size"] = params["chamber_size"]
        game_session["tool_count"] = params["tool_count"]

    def prepare_game(bullets: int, chamber_size: int):
        game_session["bullet_chamber"] = [1] * bullets + [0] * (chamber_size - bullets)
        random.shuffle(game_session["bullet_chamber"])
        game_session["total_chambers"] = chamber_size
        game_session["total_shots_fired"] = 0
        game_session["current_round"] += 1

    def reset_game_session():
        game_session.clear()
        game_session.update({
            "is_active": False,
            "admin": None,
            "players": {},
            "current_turn": None,
            "bullet_chamber": [],
            "total_shots_fired": 0,
            "total_chambers": 0,
            "current_round": 0,
            "tools_available": ["短锯", "放大镜", "饮料"],
            "waiting_for_action": False,
            "turn_order": [],
            "current_turn_index": -1,
            "initial_hp": 0,
            "initial_bullets": 0,
            "tool_count": 0,
        })
        
    def get_player_info(user_id: int) -> Optional[Dict[str, Any]]:
        player_info = game_session["players"].get(user_id)
        if player_info is None:
            bot.logger.warning(f"尝试获取不存在的玩家信息，ID: {user_id}")
        return player_info

    def get_alive_players_ids() -> List[int]:
        alive_players = [uid for uid, info in game_session["players"].items() if info["is_alive"]]
        return alive_players

    def move_to_next_turn(previous_shooter_id: int, target_id: int, is_live_round: bool):
        if "turn_order" not in game_session or not game_session["turn_order"]:
            bot.logger.warning("回合顺序列表不存在或为空，无法切换回合")
            game_session["current_turn"] = None
            return
        
        if previous_shooter_id and previous_shooter_id in game_session["players"]:
            game_session["players"][previous_shooter_id]["shot_damage_bonus"] = 0

        alive_players_in_order = [uid for uid in game_session["turn_order"] if get_player_info(uid) and get_player_info(uid)["is_alive"]]

        if not alive_players_in_order:
            game_session["current_turn"] = None
            bot.logger.info("所有玩家都已死亡，无法切换回合")
            return

        next_player_id = None

        if previous_shooter_id == target_id:
            if not is_live_round:  # 射击自己且是空枪，继续自己回合
                next_player_id = previous_shooter_id
                bot.logger.info(f"玩家 {previous_shooter_id} 对自己空枪，继续其回合。")
            else:  # 射击自己且是实弹，如果还活着，继续自己回合；如果死了，按照加入决斗次序的下一个还活着的人的回合
                shooter_info = get_player_info(previous_shooter_id)
                if shooter_info and shooter_info["is_alive"]:
                    next_player_id = previous_shooter_id
                    bot.logger.info(f"玩家 {previous_shooter_id} 对自己实弹但存活，继续其回合。")
                else:
                    # 查找顺序列表中的下一个存活玩家
                    current_index_in_order = game_session["turn_order"].index(previous_shooter_id)
                    next_index_in_order = (current_index_in_order + 1) % len(game_session["turn_order"])
                    count = 0
                    while count < len(game_session["turn_order"]):
                        player_id_candidate = game_session["turn_order"][next_index_in_order]
                        if get_player_info(player_id_candidate) and get_player_info(player_id_candidate)["is_alive"]:
                            next_player_id = player_id_candidate
                            break
                        next_index_in_order = (next_index_in_order + 1) % len(game_session["turn_order"])
                        count += 1
                    bot.logger.info(f"玩家 {previous_shooter_id} 对自己实弹并死亡，切换到下一个存活玩家 {next_player_id} 的回合。")
        # 射击别人
        else:
            target_player_info = get_player_info(target_id)
            if target_player_info and target_player_info["is_alive"]: # 目标没死，下一个回合是被射击那个人的
                next_player_id = target_id
                bot.logger.info(f"玩家 {previous_shooter_id} 射击玩家 {target_id} 且目标存活，切换到目标 {target_id} 的回合。")
            else: # 目标死了，下一个回合还是射击者
                next_player_id = previous_shooter_id
                bot.logger.info(f"玩家 {previous_shooter_id} 射击玩家 {target_id} 且目标死亡，继续其回合。")
        
        if next_player_id and (not get_player_info(next_player_id) or not get_player_info(next_player_id)["is_alive"]):
            bot.logger.warning(f"计算出的下一回合玩家 {next_player_id} 已经死亡，重新查找下一个存活玩家。")
            current_index_in_order = game_session["turn_order"].index(previous_shooter_id)
            start_index = (current_index_in_order + 1) % len(game_session["turn_order"])
            
            found_next = False
            for _ in range(len(game_session["turn_order"])):
                player_id_candidate = game_session["turn_order"][start_index]
                if get_player_info(player_id_candidate) and get_player_info(player_id_candidate)["is_alive"]:
                    next_player_id = player_id_candidate
                    found_next = True
                    break
                start_index = (start_index + 1) % len(game_session["turn_order"])
            
            if not found_next:
                next_player_id = None
        
        game_session["current_turn"] = next_player_id
        if next_player_id:
            game_session["current_turn_index"] = game_session["turn_order"].index(next_player_id)
        else:
            game_session["current_turn_index"] = -1

    async def send_game_status_message(event: GroupMessageEvent):
        status_text = "决斗状态\n"
        for uid, player in game_session["players"].items():
            status = "存活" if player["is_alive"] else "已淘汰"
            status_text += f"\n◆ 玩家: {player['nickname']} ({status})\n - HP: {player['hp']}\n - 工具: {', '.join(player['tools']) or '无'}"
            if player["shot_damage_bonus"] > 0:
                status_text += f"\n - 状态: 伤害加成 +{player['shot_damage_bonus']}"
        
        status_text += f"\n弹仓信息\n"
        shots_left = game_session['total_chambers'] - game_session['total_shots_fired']
        status_text += f"当前回合: {game_session['current_round']}\n"
        status_text += f"剩余实弹: {game_session['bullet_chamber'][game_session['total_shots_fired']:].count(1)}\n"
        status_text += f"剩余空弹: {shots_left - game_session['bullet_chamber'][game_session['total_shots_fired']:].count(1)}\n"
        status_text += f"剩余弹孔: {shots_left}"
        
        msg = await bot.send(event, [Text(text=status_text)])
        if msg:
            await delay_recall(bot, msg, 30)

    async def send_turn_info(event: GroupMessageEvent):
        current_player_id = game_session["current_turn"]
        if not current_player_id:
            bot.logger.info("没有当前回合玩家，跳过发送回合信息")
            return
            
        current_player_info = get_player_info(current_player_id)
        
        if not current_player_info:
            bot.logger.warning(f"尝试为回合{current_player_id}发送信息，但玩家数据不存在")
            return

        turn_text = random.choice(TURN_START_MESSAGES).format(player_nickname=current_player_info['nickname']) + "\n\n"
        
        turn_text += f"你的生命值: {current_player_info['hp']}\n"
        
        shots_left = game_session['total_chambers'] - game_session['total_shots_fired']
        bullets_left = game_session['bullet_chamber'][game_session['total_shots_fired']:].count(1)
        
        turn_text += f"弹仓状态: {bullets_left} 实弹, {shots_left - bullets_left} 空弹 (剩余{shots_left}发)\n"
        
        if current_player_info["shot_damage_bonus"] > 0:
            turn_text += f"你已使用短锯，下一枪伤害+{current_player_info['shot_damage_bonus']}！\n"

        turn_text += f"你的工具: {', '.join(current_player_info['tools']) or '无'}\n"
        turn_text += "你可以输入 '使用 [工具名]' (例如: '使用 短锯') 或 '射击 @[玩家] / 射击自己'"
        
        msg = await bot.send(event, [At(qq=current_player_id), Text(text=turn_text)])
        if msg:
            await delay_recall(bot, msg, 30)

    async def perform_shot(event: GroupMessageEvent, shooter_id: int, target_id: int, target_nickname: str):
        bot.logger.info(f"执行射击, 射手: {shooter_id}, 目标: {target_id}")
        shooter_info = get_player_info(shooter_id)
        target_info = get_player_info(target_id)
        
        if shooter_info is None or target_info is None:
            bot.logger.error(f"射手 ({shooter_id}) 或目标 ({target_id}) 信息不存在，无法射击")
            return
        
        is_live_round = game_session["bullet_chamber"][game_session["total_shots_fired"]] == 1
        
        shot_damage = 1 + shooter_info["shot_damage_bonus"]
        
        shooter_info["shot_damage_bonus"] = 0 
        game_session["total_shots_fired"] += 1
        
        response_text = ""
        if is_live_round:
            target_info["hp"] -= shot_damage
            response_text = random.choice(LIVE_SHOT_MESSAGES).format(target_nickname=target_nickname)
            
            # 复活：当前饮料数 > 0 时触发
            if target_info["hp"] <= 0:
                drink_count = target_info["tools"].count("饮料")

                if drink_count > 0: 
                    response_text += f"\n{target_nickname} 血量归零！但ta拥有 {drink_count} 瓶饮料！"
                    target_info["hp"] = 1
                    target_info["tools"] = [tool for tool in target_info["tools"] if tool != "饮料"]
                    response_text += "\n" + random.choice(REVIVE_MESSAGES).format(player_nickname=target_nickname)
                    bot.logger.info(f"玩家 {target_id} ({target_nickname}) 濒死时消耗所有饮料复活，HP设为1。")
                else:
                    # 饮料不足以将HP恢复到大于0，玩家死亡
                    target_info["is_alive"] = False
                    response_text += f"\n{target_nickname} 痛苦地倒下了... 他被淘汰了！"
                    bot.logger.info(f"玩家 {target_id} ({target_nickname}) HP归零且饮料不足，被淘汰。")

        else:
            response_text = random.choice(MISS_SHOT_MESSAGES)
            
        msg = await bot.send(event, [Text(text=response_text)])
        if msg:
            await delay_recall(bot, msg, 30)

        # 检查弹仓是否打空或只剩空弹
        if game_session["total_shots_fired"] >= game_session["total_chambers"] or game_session['bullet_chamber'][game_session['total_shots_fired']:].count(1) == 0:
            if len(get_alive_players_ids()) > 1: # 还有多于1个存活玩家，重装弹
                reload_message = random.choice(RELOAD_MESSAGES)
                msg_reload = await bot.send(event, [Text(text=reload_message)])
                if msg_reload:
                    await delay_recall(bot, msg_reload, 30)
                
                # 给每个存活的玩家分发工具
                alive_players_ids = get_alive_players_ids()
                tool_count_per_player = game_session["tool_count"]
                if tool_count_per_player > 0:
                    tool_distribution_message = "新一轮工具已分发给所有幸存者:\n"
                    for player_id in alive_players_ids:
                        player_info = get_player_info(player_id)
                        if player_info and player_info["is_alive"]:
                            new_tools = [random.choice(game_session["tools_available"]) for _ in range(tool_count_per_player)]
                            player_info["tools"].extend(new_tools)
                            tool_distribution_message += f" - {player_info['nickname']} 获得了：{', '.join(new_tools)}\n"
                            bot.logger.info(f"玩家 {player_id} ({player_info['nickname']}) 获得了 {tool_count_per_player} 个工具: {new_tools}")
                    
                    msg_tools = await bot.send(event, [Text(text=tool_distribution_message)])
                    if msg_tools:
                        await delay_recall(bot, msg_tools, 30)

                prepare_game(game_session["initial_bullets"], game_session["chamber_size"])
                bot.logger.info("弹仓打空，重新装弹并开始新一轮")
            else:
                bot.logger.info("弹仓打空，但玩家不足2人，游戏即将结束")

        await check_game_end(event)
        if not game_session["is_active"]: # 游戏已经结束，不再切换回合
            bot.logger.info("游戏已结束，停止回合切换和信息发送")
            return
        
        # 回合切换逻辑
        move_to_next_turn(shooter_id, target_id, is_live_round)
        
        # 延迟发送下一回合信息，确保子弹结果消息已发出
        await asyncio.sleep(1) 
        await send_turn_info(event)


    async def check_game_end(event: GroupMessageEvent):
        alive_players = get_alive_players_ids()
        if len(alive_players) <= 1:
            winner_id = alive_players[0] if alive_players else None
            
            if winner_id:
                winner_nickname = get_player_info(winner_id)["nickname"]
                win_message = random.choice(GAME_END_MESSAGES).format(winner_nickname=winner_nickname)
                msg = await bot.send(event, [Text(text=win_message)])
                if msg:
                    await delay_recall(bot, msg, 30)
            else:
                msg = await bot.send(event, [Text(text="决斗结束，没有赢家")])
                if msg:
                    await delay_recall(bot, msg, 30)
                
            reset_game_session()
            
    @bot.on(GroupMessageEvent)
    async def handle_event(event: GroupMessageEvent):
        user_id = event.sender.user_id
        nickname = event.sender.nickname
        
        pure_text = ""
        if event.processed_message and isinstance(event.processed_message[0], dict) and 'text' in event.processed_message[0]:
            pure_text = event.processed_message[0]['text'].strip()
        
        at_qq = None
        if event.message_chain.has(At):
            try:
                at_qq = event.message_chain.get(At)[0].qq
            except Exception as e:
                bot.logger.error(f"解析@消息时发生错误: {e}")
                traceback.print_exc()

        if pure_text == "决斗开始":
            if not game_session["is_active"]:
                msg = await bot.send(event, [Text(text="当前没有正在进行的决斗，请先创建")])
                if msg: await delay_recall(bot, msg, 30)
                return
            if user_id != game_session["admin"]["id"]:
                msg = await bot.send(event, [Text(text="你不是创建者，无法开始游戏")])
                if msg: await delay_recall(bot, msg, 30)
                return
            
            if len(game_session["players"]) < 2:
                msg = await bot.send(event, [Text(text="玩家数量不足，至少需要2名玩家")])
                if msg: await delay_recall(bot, msg, 30)
                return
            
            prepare_game(game_session["initial_bullets"], game_session["chamber_size"])
            
            all_players_ids = list(game_session["players"].keys())
            
            admin_id = game_session["admin"]["id"]
            other_players_ids = [uid for uid in all_players_ids if uid != admin_id]
            random.shuffle(other_players_ids)
            # 确保发起人是第一个，然后是随机的其他玩家
            game_session["turn_order"] = [admin_id] + other_players_ids
            game_session["current_turn_index"] = 0
            game_session["current_turn"] = game_session["turn_order"][0]
            
            msg = await bot.send(event, [Text(text="赌局正式开始！\n命运的枪声即将响起，请各位玩家各凭本事，活到最后！")])
            if msg: await delay_recall(bot, msg, 30)
            
            await send_game_status_message(event)
            await send_turn_info(event)
            game_session["waiting_for_action"] = True
            return

        elif pure_text == "决斗结束":
            if not game_session["is_active"]:
                msg = await bot.send(event, [Text(text="当前没有正在进行的决斗")])
                if msg: await delay_recall(bot, msg, 30)
                return
            if user_id != game_session["admin"]["id"]:
                msg = await bot.send(event, [Text(text="你不是创建者，无法结束游戏")])
                if msg: await delay_recall(bot, msg, 30)
                return
            
            reset_game_session()
            msg = await bot.send(event, [Text(text="创建者已结束决斗，赌局解散")])
            if msg: await delay_recall(bot, msg, 30)
            return
            
        elif pure_text == "决斗状态":
            bot.logger.info(f"收到指令: '决斗状态'，来自用户: {user_id}")
            if not game_session["is_active"]:
                msg = await bot.send(event, [Text(text="当前没有正在进行的决斗")])
                if msg: await delay_recall(bot, msg, 30)
                return
            
            await send_game_status_message(event)
            return

        elif pure_text == "决斗规则":        
            rules = """
决斗规则：
- 创建者使用"决斗 --hp [初始生命值] --b [每一轮子弹数] --all [每一轮总弹仓数] --tool [道具数]"来创建游戏，这里四个参数都是可选，只发送"决斗"就是标准轮盘赌

- 所有玩家加入完毕后，创建者使用"决斗开始"来开始游戏

- 创建者开始第一个回合，使用"射击自己"或"射击 @[玩家]"来进行射击，在进行射击前可以无限"使用 [工具名]"来使用工具，例如"使用 短锯"来使下一枪的伤害+1

- 射击自己如果没寄下一个回合还是自己，如果自己寄了下一个回合就是根据加入游戏顺序的自己后面一个人

- 射击其他玩家如果目标玩家没寄下一个回合就是目标玩家，如果寄了下一个回合还是射击者

- 每一轮打完(枪膛里没有子弹)但是场上存活玩家大于1人时，会装弹并发放--tool [道具数]这边定义的道具数个新的随机道具给每个活着的玩家

- 如果一个人被打死了，但他还有饮料，则会消耗所有饮料并将hp设为1

- 可以发送"决斗状态"来查看当前游戏状态，包括玩家列表、生命值、工具等信息

- 创建者在任何时候都可以使用"决斗结束"来结束游戏
            """
            
            msg = await bot.send(event, Node(content=[Text(text=rules)]))
            await delay_recall(bot, msg, 60)
            return

        elif pure_text.startswith("决斗"):
            if game_session["is_active"]:
                msg = await bot.send(event, [Text(text="一局游戏正在进行中，请等待其结束")])
                if msg: await delay_recall(bot, msg, 30)
                bot.logger.warning("已有游戏在进行中")
                return

            try:
                params = parse_game_params(pure_text)
                
                init_game(user_id, nickname, params)
                
                announcement = random.choice(START_GAME_ANNOUNCEMENTS).format(nickname=nickname)
                response_text = (
                    f"{announcement}\n"
                    f"创建者: {nickname}\n"
                    f"初始生命值: {params['hp']}\n"
                    f"子弹数: {params['bullets']}\n"
                    f"弹仓数: {params['chamber_size']}\n"
                    f"工具数: {params['tool_count']}"
                    "\n其他玩家可以输入 '加入决斗' 来加入游戏"
                    "\n所有人都加入后，创建者使用 '决斗开始' 来拉开序幕！"
                )
                msg = await bot.send(event, [Text(text=response_text)])
                if msg: await delay_recall(bot, msg, 30)

            except ValueError as e:
                msg = await bot.send(event, [Text(text=str(e))])
                if msg: await delay_recall(bot, msg, 30)
                bot.logger.error(f"创建游戏时参数错误: {e}")

        elif pure_text == "加入决斗":
            if not game_session["is_active"]:
                msg = await bot.send(event, [Text(text="当前没有正在进行的决斗")])
                if msg: await delay_recall(bot, msg, 30)
                bot.logger.warning("游戏未激活，无法加入")
                return
            
            if user_id == game_session["admin"]["id"]:
                msg = await bot.send(event, [Text(text="你就是这场赌局的庄家，无法再加入啦！")])
                if msg: await delay_recall(bot, msg, 30)
                bot.logger.warning(f"用户 {user_id} 是创建者，无法加入")
                return

            if user_id in game_session["players"]:
                msg = await bot.send(event, [Text(text="你已经坐在赌桌前了，请耐心等待创建者开始游戏")])
                if msg: await delay_recall(bot, msg, 30)
                bot.logger.warning(f"用户 {user_id} 已在游戏中")
                return
            
            player_nickname = nickname
            try:
                data = await bot.get_stranger_info(user_id=user_id)
                if data and isinstance(data, dict) and "data" in data and "nickname" in data["data"]:
                    player_nickname = data["data"]["nickname"]
                else:
                    bot.logger.warning(f"获取玩家 {user_id} 昵称信息失败，使用默认昵称: {player_nickname}")
            except Exception as e:
                bot.logger.error(f"获取玩家 {user_id} 昵称时发生错误: {e}")
                traceback.print_exc()

            player_tools = [random.choice(game_session["tools_available"]) for _ in range(game_session["tool_count"])]
            
            game_session["players"][user_id] = {
                "nickname": player_nickname,
                "hp": game_session["initial_hp"],
                "tools": player_tools,
                "is_alive": True,
                "shot_damage_bonus": 0,
            }
            join_message = random.choice(JOIN_GAME_MESSAGES).format(player_nickname=player_nickname)
            msg = await bot.send(event, [Text(text=f"{join_message}\n当前玩家数: {len(game_session['players'])}")])
            if msg: await delay_recall(bot, msg, 30)
            bot.logger.info(f"用户 {user_id} ({player_nickname}) 已加入游戏，工具: {player_tools}")
            
        elif game_session["is_active"] and game_session["current_turn"] == user_id and user_id in game_session["players"]:
            bot.logger.info(f"轮到玩家 {user_id} ({nickname}) 的回合，处理指令: '{pure_text}'")
            if pure_text.startswith("使用 "):
                tool_name = pure_text.replace("使用 ", "")
                player_info = get_player_info(user_id)
                
                if tool_name not in player_info["tools"]:
                    msg = await bot.send(event, [Text(text="你没有这个工具，别想蒙混过关！")])
                    if msg: await delay_recall(bot, msg, 30)
                    bot.logger.warning(f"玩家 {user_id} 试图使用不存在的工具: {tool_name}")
                    return
                
                bot.logger.info(f"玩家 {user_id} 使用工具: {tool_name}")
                
                response_text = ""
                if tool_name == "短锯":
                    player_info["shot_damage_bonus"] += 1
                    response_text = random.choice(SAW_MESSAGES)
                elif tool_name == "放大镜":
                    if game_session["total_shots_fired"] >= game_session["total_chambers"]:
                        msg = await bot.send(event, [Text(text="弹仓已空，无法使用放大镜")])
                        if msg: await delay_recall(bot, msg, 30)
                        bot.logger.warning("弹仓已空，无法使用放大镜")
                        return
                    is_live_round = game_session["bullet_chamber"][game_session["total_shots_fired"]] == 1
                    
                    # 根据是否实弹选择不同的文案
                    if is_live_round:
                        response_text = random.choice(MAGNIFYING_GLASS_MESSAGES["live"]) + "\n你确定要对准别人吗？"
                    else:
                        response_text = random.choice(MAGNIFYING_GLASS_MESSAGES["miss"]) + "\n你可以考虑对自己开一枪..."

                elif tool_name == "饮料":
                    player_info["hp"] += 1
                    response_text = random.choice(DRINK_MESSAGES) + f" 当前生命值: {player_info['hp']}"
                else:
                    response_text = "无效的工具"
                
                try:
                    player_info["tools"].remove(tool_name)
                    bot.logger.info(f"已移除玩家 {user_id} 的一个工具: {tool_name}")
                except ValueError:
                    bot.logger.warning(f"尝试移除玩家 {user_id} 的工具 {tool_name} 时未找到")
                    
                bot.logger.info(f"玩家 {user_id} 的剩余工具: {player_info['tools']}")
                
                msg = await bot.send(event, [Text(text=response_text)])
                if msg: await delay_recall(bot, msg, 30)
                await send_turn_info(event)

            elif pure_text.startswith("射击"):
                bot.logger.info(f"玩家 {user_id} 收到射击指令: '{pure_text}'")
                try:
                    if not game_session["waiting_for_action"]:
                        bot.logger.warning("游戏未进入等待行动状态")
                        return
                    
                    if game_session["total_shots_fired"] >= game_session["total_chambers"]:
                        msg = await bot.send(event, [Text(text="弹仓已空！等待自动重装。")])
                        if msg: await delay_recall(bot, msg, 30)
                        return

                    # 检查是否是射击自己的文本指令
                    is_self_shot_text_command = (pure_text == "射击自己")
                    
                    target_id = None
                    target_nickname = None
                    
                    if at_qq: # 如果消息链中含有@
                        bot.logger.info(f"检测到射击@指令，目标QQ: {at_qq}")
                        if at_qq == user_id: # @自己等同于射击自己
                            target_id = user_id
                            target_nickname = nickname
                            bot.logger.info(f"玩家 {user_id} @了自己，视为射击自己。")
                        elif at_qq in game_session["players"]: # @了其他玩家
                            target_id = at_qq
                            target_info = game_session["players"][target_id]
                            if not target_info["is_alive"]:
                                msg = await bot.send(event, [Text(text="你不能射击一个已经被淘汰的玩家")])
                                if msg: await delay_recall(bot, msg, 30)
                                return
                            target_nickname = target_info["nickname"]
                            bot.logger.info(f"目标玩家 {target_id} 存在于游戏会话中")
                        else: # @了不在游戏中的人
                            msg = await bot.send(event, [Text(text="你射击了一个不在游戏中的玩家")])
                            if msg: await delay_recall(bot, msg, 30)
                            bot.logger.warning(f"玩家 {user_id} 试图射击不在游戏中的玩家 {at_qq}")
                            return
                    elif is_self_shot_text_command: # 纯文本指令“射击自己”
                        target_id = user_id
                        target_nickname = nickname
                        bot.logger.info("玩家选择射击自己 (纯文本指令)。")
                    else: # 既没有@，也不是“射击自己”
                        msg = await bot.send(event, [Text(text="请@一个玩家或输入 '射击自己' 来指定目标")])
                        if msg: await delay_recall(bot, msg, 30)
                        bot.logger.warning(f"玩家 {user_id} 射击指令缺少目标")
                        return

                    if target_id is None:
                        bot.logger.error("无法确定射击目标ID，操作终止")
                        return

                    bot.logger.info(f"射击操作开始射手: {user_id}，目标: {target_id} ({target_nickname})")
                    
                    await perform_shot(event, user_id, target_id, target_nickname)
                    
                except Exception as e:
                    bot.logger.error(f"处理射击事件时发生未知错误: {e}")
                    traceback.print_exc()
                    msg = await bot.send(event, [Text(text="射击时发生未知错误，请联系创建者")])
                    if msg: await delay_recall(bot, msg, 30)
