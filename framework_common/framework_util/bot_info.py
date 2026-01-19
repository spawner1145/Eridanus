#这个文件用来启动时异步向漫朔api发送自身数据，用于后续统计分析
import uuid
import httpx
import platform
import pprint

def get_system_info():
    system = platform.system()          # 操作系统名称，如 Windows、Linux、Darwin（macOS）
    release = platform.release()        # 操作系统版本号
    version = platform.version()        # 操作系统详细版本信息
    machine = platform.machine()        # 机器类型，如 x86_64
    processor = platform.processor()    # 处理器信息
    mac_num = hex(uuid.getnode()).replace('0x', '').upper()
    mac = ':'.join(mac_num[i:i + 2] for i in range(0, 11, 2))

    system_info = {
        'device_id': mac,
        "system": system,
        "machine": machine,
        "processor": processor
    }
    return system_info

async def bot_info_collect(botname):
    url = 'http://bangumi.manshuo.ink:8092/bot/info_collection'
    device_info = get_system_info()
    data = {'name': botname, 'device_info': device_info}
    pprint.pprint(data)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data)
    except Exception as e:
        print(f'此处报错可忽略： {e}')
        pass