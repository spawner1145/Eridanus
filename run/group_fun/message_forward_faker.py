from developTools.event.events import GroupMessageEvent, PrivateMessageEvent
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from developTools.message.message_components import Node, Text, Image, At
import re
import aiohttp
import pprint


def main(bot: ExtendBot, config: YAMLManager):
    """插件主函数"""
    # 合并配置
    trigger_prefix = '伪造消息 '
    help_trigger = '伪造帮助'
    error_message = "格式错误，请使用：伪造消息 QQ号 内容 | QQ号 内容 | ..."
    qq_name_api = "http://api.mmp.cc/api/qqname?qq="
    allowed_separators = ["|", "｜"]
    
    # 构建分隔符正则表达式
    separators_pattern = '|'.join(re.escape(sep) for sep in allowed_separators)

    async def get_qq_nickname(qq_number,target_group=None):
        qq_name = ''
        """获取QQ昵称"""
        qq_name = (await bot.get_group_member_info(target_group, qq_number))['data']['nickname']
        if qq_name != '':
            return qq_name
        try:
            url = f"{qq_name_api}{qq_number}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200 and "data" in data and "name" in data["data"]:
                            nickname = data["data"]["name"]
                            if nickname:
                                qq_name = nickname
        except Exception as e:
            qq_name = f"用户{qq_number}"
        return qq_name


    async def parse_message_segments(event):
        """解析消息段，将图片正确分配到对应的消息段"""
        segments = []

        pure_text=''
        for obj in event.message_chain:
            if obj.comp_type == 'text':pure_text+=f"{obj.text}"
            elif obj.comp_type == 'image':pure_text+=f"{obj.url}.png"
            elif obj.comp_type == 'at':pure_text += f"{obj.qq} "

        pure_text = pure_text[len(trigger_prefix):]

        segments_parts = [p for p in re.split(r'[|｜]+', pure_text) if p]
        for part in segments_parts:
            segments_check = {'faker':{}, 'message_chain':[]}
            #提取开头伪造者id
            m = re.match(r'^\s*(\d+)(?=\s|$)', part)
            faker_id = int(m.group(1)) if m else None
            segments_check['faker']['id'] = faker_id
            part = part[len(f'{faker_id}'):]
            if part.startswith(' '):part = part[len(f' '):]
            #构造后续消息链
            if bool(re.search(r'https?://[^\s]+?\.(?:jpg|jpeg|png|gif|bmp)', part, re.IGNORECASE)):
                parts = re.split(r'(https?://[^\s]+?\.(?:jpg|jpeg|png|gif|bmp))', part, flags=re.IGNORECASE)
                for part in parts:
                    if 'http' in part:
                        part = part.replace('.png','')
                        segments_check['message_chain'].append(Image(file=part))
                    else:
                        segments_check['message_chain'].append(Text(text=part))
            else:
                segments_check['message_chain'].append(Text(text=part))
            segments.append(segments_check)
        return segments

    async def create_forward_nodes(segments,event):
        """创建转发消息节点"""
        nodes = []
        friendlist_get = await bot.get_group_member_list(event.group_id)
        friendlist = [friend['user_id'] for friend in friendlist_get["data"]]
        for segment in segments:
            content_list_check = segment['message_chain']
            qq_number = segment['faker']['id']
            # 获取昵称

            qq_name = ''
            """获取QQ昵称"""
            if qq_number in friendlist:
                qq_name = (await bot.get_group_member_info(event.group_id, qq_number))['data']['nickname']
            else:
                try:
                    url = f"{qq_name_api}{qq_number}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=5) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("code") == 200 and "data" in data and "name" in data["data"]:
                                    nickname = data["data"]["name"]
                                    if nickname:
                                        qq_name = nickname
                except Exception as e:
                    qq_name = f"用户{qq_number}"

            #print(content_list_check)
            node = Node(
                user_id=f'{qq_number}',
                nickname=qq_name,
                content=content_list_check
            )
            nodes.append(node)
        return nodes

    async def handle_message(event):
        """处理消息事件"""
        # 检查帮助指令
        if event.pure_text == help_trigger:
            help_text = """📱 伪造转发消息插件使用说明 📱

【基本格式】
伪造消息 QQ号 消息内容 | QQ号 消息内容 | ...

【带图片的格式】
- 在任意消息段中添加图片，图片将只出现在它所在的消息段
- 例如: 伪造消息 123456 看我的照片[图片] | 654321 好漂亮啊
- 在这个例子中，图片只会出现在第一个人的消息中

【注意事项】
- 每个消息段之间用"|"分隔
- 每个消息段的格式必须是"QQ号 消息内容"
- 图片会根据它在消息中的位置分配到对应的消息段
"""
            await bot.send(event, help_text)
            return

        # 检查触发前缀
        pure_text=event.pure_text
        if event.message_chain.has(At) and event.message_chain.has(Text):pure_text =event.message_chain.get(Text)[0].text
        if not pure_text.startswith(trigger_prefix):
            return

        # 解析消息段
        segments = await parse_message_segments(event)
        if not segments:
            await bot.send(event, error_message)
            return
        # 创建转发节点
        nodes = await create_forward_nodes(segments,event)
        if not nodes:
            await bot.send(event, error_message)
            return
        # 发送转发消息
        try:
            await bot.send(event, nodes)
        except Exception as e:
            await bot.send(event, f"发送失败: {str(e)}")

    # 注册群消息事件处理
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        await handle_message(event)

    # 注册私聊消息事件处理
    @bot.on(PrivateMessageEvent)
    async def handle_private_message(event: PrivateMessageEvent):
        await handle_message(event)
    