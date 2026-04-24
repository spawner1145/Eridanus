plugin_description = "ai绘画"

dynamic_imports = {
    "run.ai_generated_art.aiDraw": [
        "call_text2img", "call_aiArtModerate"],
    "run.ai_generated_art.function_collection": [
        "image_edit","gptimage2_text2img"
    ]
}
function_declarations=[
    {
    "name": "call_aiArtModerate",
    "description": "检测图片是否为ai生成，只有当用户要求检测时才可触发。",
    "parameters": {
        "type": "object",
        "properties": {
            "img_url": {
                "type": "string",
                "description": "目标图片的url"
            }
        },
        "required": [
            "img_url"
        ]
    }
},
    {
    "name": "call_text2img",
    "description": "stable diffusion 文本转图像，仅支持英文tag，一般绘图使用",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "生成图片的提示词。如果原始提示词中有中文，则需要你把它们替换为对应英文,尽量使用词组，单词来进行描述，并用','来分割。可通过将词语x变为(x:n)的形式改变权重，n为0-1之间的浮点数，默认为1，为1时则无需用(x:1)的形式而是直接用x。例如，如果想要增加“猫”(也就是cat)的权重，则可以把它变成(cat:1.2)或更大的权重，反之则可以把权重变小。你需要关注不同词的重要性并给于权重，正常重要程度的词的权重为1，为1时则无需用(x:1)的形式而是直接用x。例如，想要画一个可爱的女孩则可输出1girl,(cute:1.2),bright eyes,smile,casual dress,detailed face,natural pose,soft lighting;想要更梦幻的感觉则可输出1girl,ethereal,floating hair,magical,sparkles,(dreamy:1.5),soft glow,pastel colors;想要未来风格则可输出1girl,(futuristic:1.3),neon lights,(cyber:1.2),hologram effects,(tech:1.5),clean lines,metallic;同时当输入中含有英文或用户要求保留时，要保留这些词"
            }
        },
        "required": [
            "prompt"
        ]
    }
},
    {
        "name": "image_edit",
        "description": "根据用户的要求，对图片进行编辑",
        "parameters": {
            "type": "object",
            "properties": {
                "img_url": {
                    "type": "string",
                    "description": "需要的图片url"
                },
                "prompt": {
                    "type": "string",
                    "description": "对图片的要求"
                }
            },
            "required": [
                "img_url", "prompt"
            ]
        }
    },
    {
        "name": "gptimage2_text2img",
        "description": "gptimage2 文本转图像，支持中文输入，如果用户用中文作为提示词要求画图，则调用此接口",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "生成图片所需提示词，自然语言描述即可。"
                }
            },
            "required": [
                "prompt"
            ]
        }
    }
]
