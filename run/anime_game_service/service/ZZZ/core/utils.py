import asyncio
import json
import re
import httpx
import qrcode
import uuid
import json
import os
from pathlib import Path
from fuzzywuzzy import fuzz
import platform
import hashlib
import socket
import os
import subprocess

module_path: Path = Path(__file__).parent

finger_global = None

def get_device_fingerprint():
    global finger_global
    if finger_global is not None:
        return finger_global
    info = ""
    info += platform.system()
    info += platform.machine()
    info += platform.version()
    info += platform.node()        # 主机名
    mac = uuid.getnode()
    info += ':'.join(("%012X" % mac)[i:i+2] for i in range(0, 12, 2))              # MAC地址
    serial = ''
    try:
        # 仅Linux示例，读取第一个磁盘的序列号
        result = subprocess.check_output("lsblk -no SERIAL $(lsblk -ndo PKNAME $(lsblk -ndo NAME | head -n1))", shell=True)
        serial = result.decode().strip()
    except Exception:
        pass
    info += serial      # 磁盘序列号（linux）

    # 也可以加CPU info, BIOS info等

    # 对上述信息做哈希
    fingerprint = hashlib.sha256(info.encode('utf-8')).hexdigest()
    finger_global = fingerprint
    return fingerprint

async def create_qr(data,user_id):
    def generate_and_save_qr(data, user_id, module_path):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        folder_path = f"{module_path}/ZZZ_data/cache/qrcode"
        if not os.path.exists(folder_path): os.makedirs(folder_path)
        img_path = f"{module_path}/ZZZ_data/cache/qrcode/{user_id}.png"
        img.save(img_path)

    await asyncio.to_thread(generate_and_save_qr, data, user_id, module_path)

async def get_qr(user_id):
    uuid_d = uuid.uuid4()
    finger_num = get_device_fingerprint()
    headers = {
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
        "x-rpc-app_id":"bll8iq97cem8",
        'x-rpc-device_fp': f'{finger_num}',
        "x-rpc-device_id":f"{uuid_d}"
    }
    creat_qr_url = "https://passport-api.miyoushe.com/account/ma-cn-passport/web/createQRLogin"
    async with httpx.AsyncClient() as client:
        r = await client.post(url=creat_qr_url, headers=headers)
        data = r.json()
        await create_qr(data["data"]['url'], user_id)
        json_return = {'ticket':data["data"]["ticket"],'uuid_d': uuid_d, 'qr_url': f"{module_path}/ZZZ_data/cache/qrcode/{user_id}.png"}
        return json_return

async def check_qr(ticekt,uuid_d):
    finger_num = get_device_fingerprint()
    headers = {
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
        "x-rpc-app_id":"bll8iq97cem8",
        'x-rpc-device_fp': f'{finger_num}',
        "x-rpc-device_id":f"{uuid_d}"
    }
    check_qr_url = "https://passport-api.miyoushe.com/account/ma-cn-passport/web/queryQRLoginStatus"
    async with httpx.AsyncClient() as client:
        r = await client.post(url=check_qr_url, headers=headers,json={"ticket": ticekt})
        data:dict = r.json()
        cookies_json = json.dumps(dict(r.cookies), indent=4)
        record = data["retcode"]
        status_data:dict = data.get("data", {})
        if status_data == None:
            status = None
        else:
            status = status_data.get("status", None)
        return record,status,cookies_json

async def getuid(cookies):
    headers = {
        'Host': 'api-takumi.mihoyo.com',
        'Connection': 'keep-alive',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 9; 23113RKC6C Build/PQ3A.190605.06200901; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Mobile Safari/537.36 miHoYoBBS/2.75.2',
        'Origin': 'https://act.mihoyo.com',
        'X-Requested-With': 'com.mihoyo.hyperion',
        'Sec-Fetch-Site': 'same-site',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://act.mihoyo.com/',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    params = {'game_biz': 'nap_cn',}
    async with httpx.AsyncClient() as client:
        r = await client.get('https://api-takumi.mihoyo.com/binding/api/getUserGameRolesByCookie',params=params,cookies=cookies,headers=headers)
        data = r.json()
        print(data)
        user_info = data['data']['list'][0]
        json_return = {'uid':user_info['game_uid'],'nickname': user_info['nickname'], 'level':user_info['level'],
                       'region_name':user_info['region_name'], 'unmask':user_info['unmask']}
        uid = data['data']['list'][0]['game_uid']
    return json_return

async def get_avatar_id_list(uid, cookies):
    try:
        finger_num = get_device_fingerprint()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; ANP-AN00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Mobile Safari/537.36 miHoYoBBS/2.88.2',
            'x-rpc-device_fp': f'{finger_num}',
        }
        params = {'server': 'prod_gf_cn','role_id': uid,}
        async with httpx.AsyncClient() as client:
            r = await client.get('https://api-takumi-record.mihoyo.com/event/game_record_zzz/api/zzz/avatar/basic', params = params, headers = headers, cookies = cookies)
            res = r.json()
        print(res)
        avatar_id_list = res['data']['avatar_list']
        return avatar_id_list
    except:
        with open("avatar_id_list.json","r",encoding="utf-8") as f:
            avatar_id_list = json.load(f)
        return avatar_id_list

async def get_avater_info(cookies, aid, uid):
    finger_num = get_device_fingerprint()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; ANP-AN00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Mobile Safari/537.36 miHoYoBBS/2.88.2',
        'x-rpc-device_fp': f'{finger_num}'
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(f'https://api-takumi-record.mihoyo.com/event/game_record_zzz/api/zzz/avatar/info?id_list[]={aid}&need_wiki=true&server=prod_gf_cn&role_id={uid}',cookies=cookies,headers=headers)
    json = r.json()
    return json

async def get_avatar_info_list(cookies,list,uid,user_id):
    id_list = {}
    for jso in list:
        key = ''.join(re.findall(r'[\u4e00-\u9fff0-9]+', str(jso['full_name_mi18n'])))
        value = str(jso['id'])
        id_list[key] = value
    info_list = []
    for key, value in id_list.items():
        json = await get_avater_info(cookies, value, uid)
        info_list.append(json)
    await save_list(info_list,user_id)


async def save_cookie(cookies,user_id):
    folder_path = f"{module_path}/ZZZ_data/cookies"
    if not os.path.exists(folder_path):os.makedirs(folder_path)
    with open(f"{module_path}/ZZZ_data/cookies/{user_id}.json","w",encoding="utf-8") as f:
        json.dump(cookies,f,indent=4,ensure_ascii=False)

async def load_cookie(user_id):
    folder_path = f"{module_path}/ZZZ_data/cookies"
    if not os.path.exists(folder_path):os.makedirs(folder_path)
    with open(f"{module_path}/ZZZ_data/cookies/{user_id}.json","r",encoding="utf-8") as f:
        cookies = json.load(f)
    return cookies

async def check_cookie(user_id):
    path = f"{module_path}/ZZZ_data/cookies/{user_id}.json"
    if os.path.exists(path):
        return True
    else:
        return False

async def save_avatar(avatar_id_list,user_id):
    folder_path = f"{module_path}/ZZZ_data/avatar/list"
    if not os.path.exists(folder_path):os.makedirs(folder_path)
    with open(f"{module_path}/ZZZ_data/avatar/list/{user_id}.json","w",encoding="utf-8") as f:
        json.dump(avatar_id_list,f,indent=4,ensure_ascii=False)

async def save_list(info,user_id):
    folder_path = f"{module_path}/ZZZ_data/avatar/info"
    if not os.path.exists(folder_path):os.makedirs(folder_path)
    with open(f"{module_path}/ZZZ_data/avatar/info/{user_id}.json","w",encoding="utf-8") as f:
        json.dump(info,f,indent=4,ensure_ascii=False)

async def check_avatar(user_id,name):
    with open(f"{module_path}/ZZZ_data/avatar/info/{user_id}.json","r",encoding="utf-8") as f:
        data = json.load(f)
    for i, item in enumerate(data):
        avatar = item['data']['avatar_list'][0]
        nm = avatar['name_mi18n']
        if fuzz.ratio(name, nm) > 85:
            return True, i
    return False, None