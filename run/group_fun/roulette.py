import random
from developTools.event.events import GroupMessageEvent
from framework_common.utils.utils import delay_recall
import asyncio

# 游戏状态
game_state = {
    'bullets': [False] * 5 + [True],
    'shots_fired': 0,
    'current_chamber': -1,
    'max_chambers': 6
}
random.shuffle(game_state['bullets'])

def russian_roulette_narrative(user_name):
    game_state['current_chamber'] += 1
    game_state['shots_fired'] += 1

    if game_state['bullets'][game_state['current_chamber']]:
        death_text = [
            f"咔嗒...砰！ 扳机扣下，一声震耳欲聋的巨响。枪口的火光是你生命中最后的绚烂，那股力量将你狠狠地推向黑暗。{user_name}，你的意识如玻璃般碎裂，在无尽的虚无中沉沦。没有痛苦，只有永恒的寂静。",
            f"扳机，扣下了。砰！ 你的脑海中只剩下这一个词。鲜血与脑浆混杂着飞溅，在墙上留下触目惊心的痕迹。{user_name}，你没能战胜命运，你成为了这场血色游戏的祭品。",
            f"你听到一声巨响，感觉不到任何痛苦，因为你的意识已经消失了。世界在你眼前崩塌，化为无尽的黑洞。{user_name}，你，终究成了这颗子弹的奴隶。",
            f"手指的压力，扳机的回弹，一声巨响... 你的心脏在这一刻停止跳动，你还未来得及后悔，生命便已消逝。{user_name}，你将永远被遗忘在这冰冷的枪声中。"
        ]
        
        reset_game_state()
        
        return random.choice(death_text), True

    else:
        survival_text = [
            f"咔嗒。 第{game_state['shots_fired']}次扣动扳机... 枪声没有响起。你擦了擦额头上的冷汗，{user_name}，你活下来了！每一次的空响，都像是一次重生的机会。",
            f"咔嗒！ 第{game_state['shots_fired']}次扣动扳机... 扳机回弹，没有枪声。你听到的是生命的延续，{user_name}，你还有机会。你感觉心跳在胸腔里剧烈地跳动，仿佛要跳出来一样。",
            f"扳机被扣下，但只有一声清脆的空响。{user_name}，命运似乎还在眷顾着你。你已经抽了{game_state['shots_fired']}次空枪了，每一次都像在刀尖上跳舞。",
            f"咔嗒... 你的指尖在扳机上颤抖，但最终只是发出一声空响。你几乎可以听到死神在你耳边的低语，但它现在离开了。{user_name}，你又活过了一次。"
        ]
        
        if game_state['shots_fired'] == game_state['max_chambers']:
            reset_game_state()
            return f"咔嗒！ 第{game_state['shots_fired']}次扣动扳机... 枪声依然没有响起。你全身的肌肉都因紧张而颤抖，但你活下来了！{user_name}，你熬过了这个死亡的循环。", False

        return random.choice(survival_text), False

def reset_game_state():
    game_state['shots_fired'] = 0
    game_state['current_chamber'] = -1
    game_state['bullets'] = [False] * 5 + [True]
    random.shuffle(game_state['bullets'])

def get_reset_narrative():
    reset_text = [
        "冰冷的左轮手枪被重重地放在桌上，沉甸甸的。弹巢被打开，一枚锃亮的子弹被重新推入其中，它在六个弹孔中随意地滚动，最终停在了你的命运之位。弹巢被合上，然后被轻轻一转。新的一局，开始了。",
        "枪声的余音还在耳边回响，但命运的齿轮再次转动。新的弹巢，新的机会，也可能是新的终结。子弹已就位，只等你的指令。你感觉到那份冰冷的重量，它像一块冰冷的石头压在你的心上。",
        "你闭上眼，深吸一口气，试图忘记刚才的血腥。一把左轮手枪被推到你面前，弹巢里只装了一颗子弹。这就是规则。准备好了吗？游戏从这一刻重新开始。",
        "死亡的阴影刚刚散去，但新的挑战已经到来。弹巢重新上满子弹并转动，发出机械的咔嗒声。这一次，你的运气还会像之前一样好吗？"
    ]
    return random.choice(reset_text)

def get_jammed_narrative(user_name):
    jammed_text = [
        f"咔嗒...砰...？！ 枪声没有响起，只有一个沉闷的“咔嗒”声！你惊愕地发现，子弹卡壳了。{user_name}，你被命运抛弃，又被命运眷顾。这微小的机械故障，竟成了你绝处逢生的契机！",
        f"扳机扣下，但预想中的巨响并未到来，只有一声清脆的空响。你睁开眼，难以置信地看着枪口，子弹竟然卡在了弹膛里！{user_name}，这是奇迹，还是死神最后的玩笑？",
        f"枪械发出不正常的“咯吱”声，你感觉扳机异常沉重，最终只是发出一声无力的“咔”。子弹，没有被击发！{user_name}，你全身脱力地瘫坐在地，在鬼门关前走了一遭。"
    ]
    return random.choice(jammed_text), False

def main(bot, config):

    @bot.on(GroupMessageEvent)
    async def start_game(event: GroupMessageEvent):
        if event.pure_text == "轮盘赌":
            user_name = event.sender.nickname

            # 检查当前是否是即将扣动第6次扳机
            is_sixth_shot = game_state['shots_fired'] == game_state['max_chambers'] - 1
            
            # 彩蛋触发的概率
            JAM_PROBABILITY = 0.01 
            
            if is_sixth_shot:
                is_bullet = game_state['bullets'][game_state['current_chamber'] + 1]

                if is_bullet:
                    death_sentence_text = [
                        f"{user_name}，你已经连续躲过了五次死神的凝视。现在，你面前只剩下一个弹孔，你知道，它早已注定。你的手指颤抖着，慢慢伸向扳机。这是命运的最后一搏，也是最后的谢幕。你，准备好了吗？",
                        f"你看着弹巢，前五发都是空响。此刻，你的心提到了嗓子眼，第六发，是生是死，就在这电光火石之间。你深吸一口气，闭上眼，决定面对这最终的审判。",
                        f"“只剩下一发了。”你听到有人在耳边低语。这是最后的弹孔，也是你生命的终点。你没有退路，只有扣下扳机，去拥抱那未知的结局。",
                        f"你感到一种奇异的平静。五次空响，已经用完了你所有的好运。你直视着冰冷的枪口，那枚致命的子弹就在眼前。你不再犹豫，扣下了扳机。"
                    ]
                    
                    msg_death_sentence = await bot.send(event, random.choice(death_sentence_text))
                    await delay_recall(bot, msg_death_sentence)
                    await asyncio.sleep(3) # 等待几秒钟，增加戏剧性

                    if random.random() < JAM_PROBABILITY:
                        narrative, is_fatal = get_jammed_narrative(user_name)
                        msg_narrative = await bot.send(event, narrative)
                        await delay_recall(bot, msg_narrative)
    
                        await asyncio.sleep(3)
                        reset_narrative = get_reset_narrative()
                        msg_reset = await bot.send(event, reset_narrative)
                        await delay_recall(bot, msg_reset)
                        return
            
            narrative, is_fatal = russian_roulette_narrative(user_name)
            msg_narrative = await bot.send(event, narrative)
            await delay_recall(bot, msg_narrative)
            
            if is_fatal:
                await asyncio.sleep(3) # 等待几秒，让玩家反应
                reset_narrative = get_reset_narrative()
                msg_reset = await bot.send(event, reset_narrative)
                await delay_recall(bot, msg_reset)
