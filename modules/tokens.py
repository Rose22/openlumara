import core

class Tokens(core.module.Module):
    """Makes the AI token-aware"""
    async def on_end_prompt(self):
        prompt_tokens, max_tokens = await self.channel.context.get_token_usage()
        prompt_length_text = f"{prompt_tokens} out of {max_tokens} used. ONLY notify user of their token use if it's approaching the token limit."
        return prompt_length_text

