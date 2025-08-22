import json
from datetime import datetime
from pathlib import Path
from traceback import format_exc
from typing import Dict, List, Literal, Union

from httpx import AsyncClient
from pytz import timezone
import asyncio



async def query_epic_api() -> List:
    """
    获取所有 Epic Game Store 促销游戏

    参考 RSSHub ``/epicgames`` 路由 https://github.com/DIYgod/RSSHub/blob/master/lib/v2/epicgames/index.js
    """

    async with AsyncClient(proxies={"all://": None}) as client:
        try:
            res = await client.get(
                "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions",
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
                headers={
                    "Referer": "https://www.epicgames.com/store/zh-CN/",
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                        " (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36"
                    ),
                },
                timeout=10.0,
            )
            res_json = res.json()
            return res_json["data"]["Catalog"]["searchStore"]["elements"]
        except Exception as e:
            print(f"请求 Epic Store API 错误 {e.__class__.__name__}\n{format_exc()}")
            return []


async def get_epic_free():
    """
    获取 Epic Game Store 免费游戏信息

    参考 pip 包 epicstore_api 示例 https://github.com/SD4RK/epicstore_api/blob/master/examples/free_games_example.py
    """

    games = await query_epic_api()
    json_return = {'status':False,'msg':'','content':[]}
    if not games:
        json_return['msg'] = 'Epic 可能又抽风啦，请稍后再试（'
        return json_return
    else:
        #print(f"获取到 {len(games)} 个游戏数据：\n{('、'.join(game['title'] for game in games))}")
        game_cnt, msg_list = 0, []
        for game in games:
            game_name = game.get("title", "未知")
            try:
                if not game.get("promotions"):
                    continue
                game_promotions = game["promotions"]["promotionalOffers"]
                upcoming_promotions = game["promotions"]["upcomingPromotionalOffers"]
                original_price = game["price"]["totalPrice"]["fmtPrice"]["originalPrice"]
                discount_price = game["price"]["totalPrice"]["fmtPrice"]["discountPrice"]
                if not game_promotions:
                    if upcoming_promotions:
                        #print(f"跳过即将推出免费游玩的游戏：{game_name}({discount_price})")
                        pass
                    continue  # 仅返回正在推出免费游玩的游戏
                elif game["price"]["totalPrice"]["fmtPrice"]["discountPrice"] != "0":
                    #print(f"跳过促销但不免费的游戏：{game_name}({discount_price})")
                    continue
                # 处理游戏预览图
                image_url = ''
                for image in game["keyImages"]:
                    # 修复部分游戏无法找到图片
                    # https://github.com/HibiKier/zhenxun_bot/commit/92e60ba141313f5b28f89afdfe813b29f13468c1
                    if image.get("url") and image["type"] in [
                        "Thumbnail",
                        "VaultOpened",
                        "DieselStoreFrontWide",
                        "OfferImageWide",
                    ]:
                        image_url=image["url"]
                        break
                # 处理游戏发行信息
                game_dev, game_pub = game["seller"]["name"], game["seller"]["name"]
                for pair in game["customAttributes"]:
                    if pair["key"] == "developerName":
                        game_dev = pair["value"]
                    elif pair["key"] == "publisherName":
                        game_pub = pair["value"]
                dev_com = f"{game_dev} 开发、" if game_dev != game_pub else ""
                companies = (
                    f"由 {dev_com}{game_pub} 发行，"
                    if game_pub != "Epic Dev Test Account"
                    else ""
                )
                # 处理游戏限免结束时间
                date_rfc3339 = game_promotions[0]["promotionalOffers"][0]["endDate"]
                end_date = (
                    datetime.strptime(date_rfc3339, "%Y-%m-%dT%H:%M:%S.%f%z")
                    .astimezone(timezone("Asia/Shanghai"))
                    .strftime("%m {m} %d {d} %H:%M")
                    .format(m="月", d="日")
                )
                # 处理游戏商城链接（API 返回不包含游戏商店 URL，依经验自行拼接
                if game.get("url"):
                    game_url = game["url"]
                else:
                    slugs = (
                        [
                            x["pageSlug"]
                            for x in game.get("offerMappings", [])
                            if x.get("pageType") == "productHome"
                        ]
                        + [
                            x["pageSlug"]
                            for x in game.get("catalogNs", {}).get("mappings", [])
                            if x.get("pageType") == "productHome"
                        ]
                        + [
                            x["value"]
                            for x in game.get("customAttributes", [])
                            if "productSlug" in x.get("key")
                        ]
                    )
                    game_url = "https://store.epicgames.com/zh-CN{}".format(
                        f"/p/{slugs[0]}" if len(slugs) else ""
                    )
                game_cnt += 1
                content = {'game_name':game_name,'original_price':original_price,'description':game["description"],
                           'companies':companies,'end_date':end_date,'game_url':game_url,'img':image_url}
                json_return['content'].append(content)
            except (AttributeError, IndexError, TypeError):
                print(f"处理游戏 {game_name} 时遇到应该忽略的错误\n{format_exc()}")
                pass
            except Exception as e:
                print(f"组织 Epic 订阅消息错误 {e.__class__.__name__}\n{format_exc()}")
        # 返回整理好的消息字符串
        json_return['msg'] = f"Epic {game_cnt} 款游戏现在免费！" if game_cnt else "暂未找到正在促销的游戏..."
        json_return['status'] = True
        return json_return



if __name__ == '__main__':
    asyncio.run(get_epic_free())