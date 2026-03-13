import core

class Tokens(core.module.Module):
    """makes an AI token-aware"""
    async def on_end_prompt(self):
        prompt_tokens = await self.channel.context.chat.count_tokens()
        # reserve about 100 tokens for the end prompt, just to be safe
        prompt_tokens += 100

        max_tokens = core.config.get("api").get("max_context", 8192)
        prompt_length_text = f"{prompt_tokens} out of {max_tokens} used. Notify user if they're approaching the token limit!"
        return prompt_length_text

