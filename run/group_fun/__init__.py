plugin_description="群聊娱乐功能"
"""
各个入口文件
"""
from framework_common.framework_util.main_func_detector import load_main_functions
entrance_func=load_main_functions(__file__)

dynamic_imports ={
    "run.group_fun.func_collection": ["random_ninjutsu","query_ninjutsu"],
}
function_declarations=[
    {
        "name": "query_ninjutsu",
        "description": "查询忍术",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "忍术名称"
                },
            },
            "required": [
                "name"
            ]
        }
    },
    {
        "name": "random_ninjutsu",
        "description": "随机获取忍术",
    }
]