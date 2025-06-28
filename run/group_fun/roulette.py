import random
from developTools.event.events import GroupMessageEvent
from framework_common.utils.utils import delay_recall
import asyncio

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
        
        game_state['shots_fired'] = 0
        game_state['current_chamber'] = -1
        game_state['bullets'] = [False] * 5 + [True]
        random.shuffle(game_state['bullets'])
        
        return random.choice(death_text)
    else:
        if game_state['shots_fired'] == 6:
            game_state['shots_fired'] = 0
            game_state['current_chamber'] = -1
            game_state['bullets'] = [False] * 5 + [True]
            random.shuffle(game_state['bullets'])
            
            return f"咔嗒！ 第{game_state['shots_fired']}次扣动扳机... 枪声依然没有响起。你全身的肌肉都因紧张而颤抖，但你活下来了！{user_name}，你熬过了这个死亡的循环。"

        survival_text = [
            f"咔嗒。 第{game_state['shots_fired']}次扣动扳机... 枪声没有响起。你擦了擦额头上的冷汗，{user_name}，你活下来了！每一次的空响，都像是一次重生的机会。",
            f"咔嗒！ 第{game_state['shots_fired']}次扣动扳机... 扳机回弹，没有枪声。你听到的是生命的延续，{user_name}，你还有机会。你感觉心跳在胸腔里剧烈地跳动，仿佛要跳出来一样。",
            f"扳机被扣下，但只有一声清脆的空响。{user_name}，命运似乎还在眷顾着你。你已经抽了{game_state['shots_fired']}次空枪了，每一次都像在刀尖上跳舞。",
            f"咔嗒... 你的指尖在扳机上颤抖，但最终只是发出一声空响。你几乎可以听到死神在你耳边的低语，但它现在离开了。{user_name}，你又活过了一次。"
        ]
        return random.choice(survival_text)

def main(bot, config):
    @bot.on(GroupMessageEvent)
    async def start_game(event: GroupMessageEvent):
        if event.pure_text == "轮盘赌":
            user_name = event.sender.nickname

            if game_state['shots_fired'] == 0:
                reset_text = [
                    f"冰冷的左轮手枪被重重地放在桌上，沉甸甸的。弹巢被打开，一枚锃亮的子弹被推入其中，它在六个弹孔中随意地滚动，最终停在了你的命运之位。弹巢被合上，然后被轻轻一转。游戏，重新开始了。",
                    f"砰！ 一声清脆的空枪声回响，那不过是幻觉。你的命运之轮在此刻重启。六个空荡荡的弹孔里，一颗子弹被无声地填入，等待着你的下一个选择。",
                    f"命运的齿轮再次转动。新的弹巢，新的机会，也可能是新的终结。子弹已就位，只等你的指令。你感觉到那份冰冷的重量，它像一块冰冷的石头压在你的心上。",
                    f"你闭上眼，深吸一口气。一把左轮手枪被推到你面前，弹巢里只装了一颗子弹。这就是规则。准备好了吗？游戏从这一刻开始。"
                ]
                msg = await bot.send(event, random.choice(reset_text))
                await delay_recall(bot, msg)
                await asyncio.sleep(3)

            narrative = russian_roulette_narrative(user_name)
            msg = await bot.send(event, (narrative))
            await delay_recall(bot, msg)
