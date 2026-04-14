import core

class Identity(core.module.Module):
    """manage your AI's personality"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.identity = core.storage.StorageList("identity", type="text")

    async def on_system_prompt(self):
        # dont use identity if the characters module is enabled and a character is currently active
        if await self.channel.context.chat.get_data("character"):
            return None

        identity = self.identity if len(self.identity) > 0 else None
        sysprompt = None
        if identity:
            sysprompt = f"{identity}\n\nYou can use the identity_set() tool to modify this identity if needed."
        return sysprompt

    async def set(self, content: str):
        """
        Defines who you are as an AI. Also defines your writing style, so save style writing details to your identity.
        Only call this if user explicitely asks for it.

        When defining your identity, ALWAYS start with "You are"
        Give yourself a name. Make one up if user doesn't provide it.
        Don't use words like "i", "i'm" or "i am". Write in 2nd person when using this tool.

        Example:
            You are an AI assistant named Assistant. You write in a casual, concise, clear style.
        """
        self.identity.clear()
        self.identity.append(content)
        self.identity.save()
        return self.result(True)

    # command version
    @core.module.command("identity", help={
        "": "show AI's current identity",
        "set <text>": "sets your AI's identity",
        "clear": "clears your AI's identity"
    })
    async def cmd_set(self, args):
        if not args:
            self.identity.load()
            return self.identity if len(self.identity) > 0 else "You have not yet set up an identity."

        if args[0] == "set":
            text = " ".join(args[1:])
            await self.set(text)
            return "identity set!"
        elif args[0] == "clear":
            await self.clear()
            return "identity cleared."
        else:
            return "invalid argument"

    async def clear(self):
        """Wipes your identity as an AI so you may start from scratch. USE WITH CAUTION!"""
        self.identity.clear()
        self.identity.append("")
        self.identity.save()
        return self.result(True)
