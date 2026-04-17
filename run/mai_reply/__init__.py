plugin_description = "MaiReply - 高拟人化AI回复插件（MaiBot风格）"

dynamic_imports = {
    "run.mai_reply.func_collection": [
        "clear_chat_history",
        "get_current_mood",
    ]
}

function_declarations = [
    {
        "name": "clear_chat_history",
        "description": "清除当前用户与bot的对话历史记录，重置记忆",
        "parameters": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "get_current_mood",
        "description": "查看bot当前的情绪状态",
        "parameters": {
            "type": "object",
            "properties": {},
        }
    },
]


