import core
import regex

class Replacer(core.module.Module):
    """Replaces any words in your messages with your desired replacements. Useful for censoring, protecting sensitive data, and so on!"""

    settings = {
        "replacements": {
            "type": "object",
            "description": "A table of your desired replacements. Left side is the word to be replaced, right side is the desired replacement.",
            "default": {}
        }
    }

    def _replace_words(self, match):
        word = match.group(0)
        stripped = regex.sub(r'[^\w]', '', word)

        replacements = self.config.get("replacements")
        return replacements.get(stripped, word)

    async def on_user_message(self, message: str):
        result = regex.sub(r'\b[^\W_]+\b', self._replace_words, message)

        return result
