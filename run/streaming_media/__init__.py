plugin_description="媒体服务"

dynamic_imports ={
    "run.streaming_media.youtube": ["download_video"],
    "run.streaming_media.cloud_music_parsing": ["parse_cloud_music"]
}
function_declarations=[
    {
        "name": "download_video",
        "description": "下载youtube/bilibili的视频或音频。",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string", "enum": ["video", "audio"], "description": "下载类型。asmr100平台只能下载audio"
                },
                "url": {
                    "type": "string",
                    "description": "视频/音频的链接地址"
                },
                "platform": {
                    "type": "string", "enum": ["youtube", "bilibili", "asmr100"],
                    "description": "视频的来源平台。域名为b23.tv的为bilibili"
                }
            },
            "required": [
                "url",
                "platform"
            ]
        }
    },
    {
        "name": "parse_cloud_music",
        "description": "解析并下载网易云音乐单曲",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "音频的链接地址"
                },
            },
            "required": [
                "url"
            ]
        }
    },
]