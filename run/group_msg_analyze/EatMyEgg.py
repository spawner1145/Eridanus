from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Forward
from framework_common.framework_util.websocket_fix import ExtendBot
from framework_common.framework_util.yamlLoader import YAMLManager
from framework_common.utils.GeminiKeyManager import GeminiKeyManager
from run.ai_llm.service.aiReplyCore import aiReplyCore
from run.ai_llm.service.aiReplyHandler.gemini import geminiRequest
from run.group_msg_analyze.service.prompt_constructer import gemini_prompt_construct_vGroup


def main(bot: ExtendBot,config: YAMLManager):
    @bot.on(GroupMessageEvent)
    async def handle_group_message(event: GroupMessageEvent):
        return
        if event.user_id==1840094972:
            print("message from admin")
            print(event.message_chain)
            if event.message_chain.has(Forward):
                bot.logger.info("forward message received")
                forward_msg = event.message_chain.get(Forward)[0]
                msg_id=forward_msg.id
                i=0
                while i<3:
                    full_msg = await bot.get_forward_msg(msg_id)
                    if full_msg["status"]=="ok":
                        try:
                            role_set=config.group_msg_analyze.config["role_set"]
                            response_message = await geminiRequest(
                                await gemini_prompt_construct_vGroup(full_msg),
                                config.ai_llm.config["llm"]["gemini"]["base_url"],
                                await GeminiKeyManager.get_gemini_apikey(),
                                config.ai_llm.config["llm"]["gemini"]["model"],
                                config.common_config.basic_config["proxy"]["http_proxy"] if config.ai_llm.config["llm"][
                                    "enable_proxy"] else None,
                                tools=None,
                                system_instruction=role_set,
                                temperature=config.ai_llm.config["llm"]["gemini"]["temperature"],
                                maxOutputTokens=config.ai_llm.config["llm"]["gemini"]["maxOutputTokens"],
                                fallback_models=config.ai_llm.config["llm"]["gemini"]["fallback_models"],
                            )
                            bot.logger.info(response_message)
                            await bot.send(event, response_message['candidates'][0]["content"]["parts"][0]["text"])
                            break
                        except Exception as e:
                            bot.logger.error(e)
                            i+=1

            #await bot.send(event,"Hello World!")