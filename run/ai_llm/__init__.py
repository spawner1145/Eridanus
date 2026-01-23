plugin_description = "AI LLM Plugin"

# 动态导入列表
dynamic_imports = {
    "run.ai_llm.service.official_search_tool": ["search_with_official_api"],
}

# 函数声明
function_declarations = [
    {
        "name": "search_with_official_api",
        "description": "使用官方API进行联网搜索或读取URL内容。当用户需要查询实时信息、新闻、天气、或需要访问特定网页内容时使用此功能。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询内容，或对URL内容提出的问题"
                },
                "urls": {
                    "type": "string",
                    "description": "可选，需要读取的URL地址。如果有多个URL，用逗号分隔"
                }
            },
            "required": ["query"]
        }
    }
]
