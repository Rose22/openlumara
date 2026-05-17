import core

class TokenThreshold(core.module.Module):
    """Will make the AI warn you if you're approaching the token limit"""

    settings = {
        "warning_threshold": {
            "default": 0.8,
            "type": "percentage"
        }
    }

    async def on_end_prompt(self):
        # Check if we have a channel and context to avoid recursion
        if not hasattr(self, 'channel') or not hasattr(self.channel, 'context'):
            return None
            
        # Use prevent_recursion flag to avoid infinite recursion
        token_usage = await self.channel.context.get_token_usage()
        
        # Handle potential errors in token counting
        if not isinstance(token_usage, dict) or 'current' not in token_usage or 'max' not in token_usage:
            return None
            
        current = token_usage['current']
        max_tokens = token_usage['max']
        
        # Avoid division by zero
        if max_tokens <= 0:
            return None
            
        used_percentage = (current / max_tokens) * 100

        warning_threshold_percent = self.config.get("warning_threshold")
        warning_threshold_percent = warning_threshold_percent * 100

        if used_percentage >= warning_threshold_percent:
            remaining_percentage = 100 - used_percentage

            return f"WARNING: Approaching token limit! You have used {used_percentage:.1f}% of the allowed tokens. {remaining_percentage:.1f}% remaining. Warn the user!! The user might want to use `/compress` to summarize the chat so far (the user won't lose chat history, but the AI won't see the messages anymore). Or the user can use `/new` to start a new chat."
        else:
            return None
