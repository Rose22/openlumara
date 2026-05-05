import core

class TokenThreshold(core.module.Module):
    """Will make the AI warn you if you're approaching the token limit"""

    settings = {
        "warning_threshold_percentage": 80
    }

    async def on_end_prompt(self):
        token_usage = await self.channel.context.get_token_usage()

        used_percentage = (token_usage['current'] / token_usage['max']) * 100

        warning_threshold_percent = self.config.get("warning_threshold_percentage")

        if used_percentage >= warning_threshold_percent:
            remaining_percentage = 100 - used_percentage

            return f"WARNING: Approaching token limit! You have used {used_percentage:.1f}% of the allowed tokens. {remaining_percentage:.1f}% remaining. Warn the user!!"
        else:
            return None
