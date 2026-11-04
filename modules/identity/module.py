import core

class Identity(core.module.Module):
    """Gives your AI a personality by inserting it as a prompt. The AI can edit its own personality!"""

    category = "core"

    settings = {
        "identity": {
            "type": "long_text",
            "description": "The main identity prompt that defines your AI's identity. You can put anything here - this is basically your freeform system prompt.",
            "default": ""
        },
        "allow_ai_to_change_identity": {
            "description": "Whether to allow the AI to change its own identity",
            "default": True
        }
    }

    async def on_ready(self):
        if not self.config.get("allow_ai_to_change_identity"):
            self.disabled_tools.append("set")
            self.disabled_tools.append("clear")

    async def on_system_prompt(self):
        # dont use identity if the characters module is enabled and a character is currently active
        if self.channel.context.chat.get("metadata").get("character"):
            return None

        identity = self.config.get("identity")
        if not identity:
            return None

        return identity

    @core.module.tool
    async def set(self, content: str):
        """Defines who you are as an AI. When defining your identity, ALWAYS start with "You are". Give yourself a name. Make one up if user doesn't provide it. Don't use words like "i", "i'm" or "i am". Write in 2nd person when using this tool.
        """
        self.config.set("identity", content)
        return self.result(True)

    # command version
    @core.module.command("identity", help={
        "": "show AI's current identity",
        "set <text>": "sets your AI's identity",
        "clear": "clears your AI's identity"
    })
    async def cmd_set(self, args):
        if not args:
            identity = self.config.get("identity")
            return identity if len(identity) > 0 else "You have not yet set up an identity."

        if args[0] == "set":
            text = " ".join(args[1:])
            self.config.set("identity", text)
            return "identity set!"
        elif args[0] == "clear":
            await self.config.set("identity", "")
            return "identity cleared."
        else:
            return "invalid argument"

    @core.module.tool
    async def clear(self):
        """Wipes your identity as an AI so you may start from scratch. USE WITH CAUTION!"""
        self.config.set("identity", "")
        return self.result(True)
