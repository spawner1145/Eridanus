import httpx
from developTools.utils.logger import get_logger
logger=get_logger()
from pydantic import AnyUrl as Url
import pprint

from .schemas import CRED, ArkSignResult
from .api import SklandAPI, SklandLoginAPI
from .config import RES_DIR
from .exception import LoginException, RequestException, UnauthorizedException
config_default, config_default_rouge='default', 'rogue'

async def get_characters_and_bind(user, userid, db):
    cred = CRED(cred=user['cred'], token=user['cred_token'])
    binding_app_list = await SklandAPI.get_binding(cred)
    for app in binding_app_list:
        for character in app["bindingList"]:
            character_dict = {
                'id':user['id'],
                'uid':character["uid"],
                'nickname':character["nickName"],
                'app_code':app["appCode"],
                'channel_master_id':character["channelMasterId"],
                'isdefault':character["isDefault"],
            }
            #pprint.pprint(character_dict)
            if len(app["bindingList"]) == 1:character_dict['isdefault'] = True
            if character_dict['isdefault'] is True:
                db.write_user(userid, {'skland': {'character_info': character_dict}})
                return character_dict



def refresh_access_token_if_needed(func):
    """装饰器：如果 access_token 失效，刷新后重试"""

    async def wrapper(user, *args, **kwargs):
        try:
            return await func(user, *args, **kwargs)
        except LoginException:
            if not user['access_token']:
                logger.error("cred失效，用户没有绑定token，无法自动刷新cred")

            try:
                grant_code = await SklandLoginAPI.get_grant_code(user['access_token'])
                new_cred = await SklandLoginAPI.get_cred(grant_code)
                user['cred'], user['cred_token'] = new_cred.cred, new_cred.token
                logger.info("access_token 失效，已自动刷新")
                return await func(user, *args, **kwargs)
            except (RequestException, LoginException, UnauthorizedException) as e:
                logger.error(f"接口请求失败,{e.args[0]}")
        except RequestException as e:
            logger.error(f"接口请求失败,{e.args[0]}")

    return wrapper


def refresh_cred_token_if_needed(func):
    """装饰器：如果 cred_token 失效，刷新后重试"""

    async def wrapper(user, *args, **kwargs):
        try:
            return await func(user, *args, **kwargs)
        except UnauthorizedException:
            try:
                new_token = await SklandLoginAPI.refresh_token(user['cred'])
                user['cred_token'] = new_token
                logger.info("cred_token 失效，已自动刷新")
                return await func(user, *args, **kwargs)
            except (RequestException, LoginException, UnauthorizedException) as e:
                logger.error(f"接口请求失败,{e.args[0]}")
        except RequestException as e:
            logger.error(f"接口请求失败,{e.args[0]}")

    return wrapper


def refresh_cred_token_with_error_return(func):
    """装饰器：如果 cred_token 失效，刷新后重试"""

    async def wrapper(user, *args, **kwargs):
        try:
            return await func(user, *args, **kwargs)
        except UnauthorizedException:
            try:
                new_token = await SklandLoginAPI.refresh_token(user['cred'])
                user['cred_token'] = new_token
                logger.info("cred_token 失效，已自动刷新")
                return await func(user, *args, **kwargs)
            except (RequestException, LoginException, UnauthorizedException) as e:
                return f"接口请求失败,{e.args[0]}"
        except RequestException as e:
            return f"接口请求失败,{e.args[0]}"

    return wrapper


def refresh_access_token_with_error_return(func):
    async def wrapper(user, *args, **kwargs):
        try:
            return await func(user, *args, **kwargs)
        except LoginException:
            if not user.access_token:
                logger.error("cred失效，用户没有绑定token，无法自动刷新cred")

            try:
                grant_code = await SklandLoginAPI.get_grant_code(user['access_token'])
                new_cred = await SklandLoginAPI.get_cred(grant_code)
                user['cred'], user['cred_token'] = new_cred.cred, new_cred.token
                logger.info("access_token 失效，已自动刷新")
                return await func(user, *args, **kwargs)
            except (RequestException, LoginException, UnauthorizedException) as e:
                return f"接口请求失败,{e.args[0]}"
        except RequestException as e:
            return f"接口请求失败,{e.args[0]}"

    return wrapper


async def get_lolicon_image() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.lolicon.app/setu/v2?tag=arknights")
    return response.json()["data"][0]["urls"]["original"]


async def get_background_image() -> str | Url:
    default_background = RES_DIR / "images" / "background" / "sklandbg.png"
    #print(default_background)
    match config_default:
        case "default":
            background_image = default_background.as_posix()
        case "Lolicon":
            background_image = await get_lolicon_image()
        case _:
            background_image = default_background.as_posix()
    #print(background_image)
    return background_image


async def get_rogue_background_image(rogue_id: str) -> str | Url:
    default_background = RES_DIR / "images" / "background" / "rogue" / "kv_epoque14.png"
    default_rogue_background_map = {
        "rogue_1": RES_DIR / "images" / "background" / "rogue" / "pic_rogue_1_KV1.png",
        "rogue_2": RES_DIR / "images" / "background" / "rogue" / "pic_rogue_2_50.png",
        "rogue_3": RES_DIR / "images" / "background" / "rogue" / "pic_rogue_3_KV2.png",
        "rogue_4": RES_DIR / "images" / "background" / "rogue" / "pic_rogue_4_47.png",
    }
    match config_default_rouge:
        case "default":
            background_image = default_background.as_posix()
        case "rogue":
            background_image = default_rogue_background_map.get(rogue_id, default_background).as_posix()
        case "Lolicon":
            background_image = await get_lolicon_image()

    return background_image


def format_sign_result(sign_data: dict, sign_time: str, is_text: bool) -> ArkSignResult:
    """格式化签到结果"""
    formatted_results = {}
    success_count = 0
    failed_count = 0
    for nickname, result_data in sign_data.items():
        if isinstance(result_data, dict):
            awards_text = "\n".join(
                f"  {award['resource']['name']} x {award['count']}" for award in result_data["awards"]
            )
            if is_text:
                formatted_results[nickname] = f"✅ 角色：{nickname} 签到成功，获得了:\n📦{awards_text}"
            else:
                formatted_results[nickname] = f"✅ 签到成功，获得了:\n📦{awards_text}"
            success_count += 1
        elif isinstance(result_data, str):
            if "请勿重复签到" in result_data:
                if is_text:
                    formatted_results[nickname] = f"ℹ️ 角色：{nickname} 已签到 (无需重复签到)"
                else:
                    formatted_results[nickname] = "ℹ️ 已签到 (无需重复签到)"
                success_count += 1
            else:
                if is_text:
                    formatted_results[nickname] = f"❌ 角色：{nickname} 签到失败: {result_data}"
                else:
                    formatted_results[nickname] = f"❌ 签到失败: {result_data}"
                failed_count += 1
    return ArkSignResult(
        failed_count=failed_count,
        success_count=success_count,
        results=formatted_results,
        summary=(
            f"--- 签到结果概览 ---\n"
            f"总计签到角色: {len(formatted_results)}个\n"
            f"✅ 成功签到: {success_count}个\n"
            f"❌ 签到失败: {failed_count}个\n"
            f"⏰️ 签到时间: {sign_time}\n"
            f"--------------------"
        ),
    )
