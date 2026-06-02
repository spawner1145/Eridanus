plugin_description="资源搜集(r18)"


dynamic_imports = {
    "run.resource_collector.resource_search": [
        "search_book_info", "call_asmr", "call_download_book","jm_search","jm_download","jm_preview"
    ],
    "run.resource_collector.engine_search": ["search_net", "read_html"],
    "run.resource_collector.func_collection": ["iwara_search", "iwara_tendency"],
}
function_declarations=[
    {
        "name": "jm_search",
        "description": "jmcomic漫画搜索",
        "parameters": {
            "type": "object",
            "properties": {
                "search_topic": {
                    "type": "string",
                    "description": "搜索关键字"
                }
            },
            "required": [
                "search_topic"
            ]
        }
    },
    {
        "name": "jm_download",
        "description": "jmcomic漫画下载",
        "parameters": {
            "type": "object",
            "properties": {
                "comic_id": {
                    "type": "integer",
                    "description": "漫画id。预览和下载时使用"
                },
            },
            "required": [
                "comic_id"
            ]
        }
    },
    {
        "name": "jm_preview",
        "description": "jmcomic漫画预览,“验车”是预览的另一种称呼。验车xxxx必须触发此命令",
        "parameters": {
            "type": "object",
            "properties": {
                "comic_id": {
                    "type": "integer",
                    "description": "漫画id。预览和下载时使用"
                },
            },
            "required": [
                "comic_id"
            ]
        }
    },
    {
                "name": "search_book_info",
                "description": "search book information by book_name or author_name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "info": {
                            "type": "string",
                            "description": "book_name or author_name"
                        }
                    },
                    "required": [
                        "info"
                    ]
                }
            },
    {
        "name": "call_asmr",
        "description": "向用户发送asmr助眠音频。",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string", "enum": ["hotest", "random", "latest"], "description": "热门asmr，随机asmr，最新asmr"
                }
            },
            "required": [
                "mode"
            ]

        }
    },
    {
        "name": "call_download_book",
        "description": "从zlibrary下载书籍，一般是小说。不要用此接口下载jm漫画",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {
                    "type": "string",
                    "description": "书籍的id。"
                },
                "hash": {
                    "type": "string",
                    "description": "书籍的hash。"
                }
            },
            "required": [
                "book_id",
                "hash"
            ]
        }
    },
    {
        "name": "search_net",
        "description": "当用户明确告知上网查或是你无法回答用户问题时，上网查询相关信息并总结(不要管点歌指令或是搜图指令)",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "你认为合适的上网查询的关键词或句子，注意，如果用户想知道当前时间，直接查询‘百度时间’；如果用户告知你要‘深度搜索’某一个内容，在调用此函数后获取到的所有url中选取你觉得合适的url，再调用read_html函数进行网页阅读"
                }
            },
            "required": [
                "query"
            ]
        }
    },
    {
        "name": "read_html",
        "description": "当需要阅读具体网址的内容时，调用此函数",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "需要阅读的url，注意你可以先判断一下这是不是一个合法的url，如果是一个下载链接，你不要阅读"
                }
            },
            "required": [
                "url"
            ]
        }
    },
    {
        "name": "iwara_search",
        "description": "根据关键词/视频id在iwara搜索/下载视频",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string", "enum": ["download", "search"],
                    "description": "操作类型"
                },

                "aim": {
                    "type": "string",
                    "description": "搜索关键字/要下载的视频id"
                }
            },
            "required": [
                "operation",
                "aim"
            ]
        }
    },
    {
        "name": "iwara_tendency",
        "description": "查询iwara的热门视频、当前趋势、最新视频的榜单",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string", "enum": ["hotest", "trending", "latest"], "description": "热门，当前趋势，最新"
                }
            },
            "required": [
                "mode"
            ]

        }
    },
    {
        "name": "telegram_stickers_download",
        "description": "telegram贴纸下载",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "贴纸的链接"
                }
            },
            "required": [
                "url",
            ]
        }
    },
]