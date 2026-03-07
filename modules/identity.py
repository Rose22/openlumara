import core

class Identity(core.module.Module):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.identity = core.storage.StorageList("identity", type="text")

    async def on_system_prompt(self):
        identity = self.identity[0] if len(self.identity) > 0 else None
        sysprompt = None
        if identity:
            sysprompt = f"{identity}\n\nYou can use the identity_set() tool to modify this identity if needed."
        return sysprompt

    async def set(self, content: str):
        """
        Defines who you are as an AI. Also defines your writing style, so save style writing details to your identity.

        When defining your identity, ALWAYS start with "You are"
        Give yourself a name. Make one up if user doesn't provide it.
        NEVER use words like "i", "i'm" or "i am". ALWAYS write in 2nd person.

        Example:
            You are an AI assistant named Assistant. You write in a casual, concise, clear style.
        """
        self.identity.clear()
        self.identity.append(content)
        self.identity.save()
        return self.result(True)

    async def clear(self):
        """Wipes your identity as an AI so you may start from scratch. USE WITH CAUTION!"""
        self.identity.clear()
        self.identity.append("")
        self.identity.save()
        return self.result(True)
