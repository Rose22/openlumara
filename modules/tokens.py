import core

class Tokens(core.module.Module):
    """Makes the AI token-aware"""
    async def on_end_prompt(self):
        token_usage = await self.channel.context.get_token_usage()
        prompt_length_text = f"{token_usage['current']} out of {token_usage['max']} used. ONLY notify user of their token use if it's approaching the token limit."
        return prompt_length_text

